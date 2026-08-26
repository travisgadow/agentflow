"""The orchestrator.

Runs a sequence of agents, threading a shared Context, and applies:

* per-agent **verification** (each agent can ship its own rubric),
* a **governor** for budgets + a final publish gate,
* a full **trace** of every decision.

Run modes
---------
``strict`` (default)
    If a stage's verification fails, the pipeline stops immediately and the
    run is not publishable. Any warnings also block publish.

``lenient`` (``strict=False``)
    Verification failures and agent errors are recorded as warnings in the
    audit trail but do not stop the pipeline or block publish on their own —
    publishing is then decided purely by your Governor policies.

``stop_on_failure``
    When an agent returns ``ok=False`` (e.g. LLM error), abort the pipeline
    instead of skipping that stage. Default False (skip and continue).

The result exposes the final output, whether it was deemed publishable, any
warnings, the governance decision, and the per-run trace.

A ``webhook`` (any object with ``.emit(payload: dict)``) may be supplied; the
pipeline fires it once on ``pipeline_end`` with a compact run summary. A webhook
failure is recorded in the result (``result["webhook"]``) and never crashes the
run.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .agent import Agent, AgentResult
from .context import Context
from .governor import Governor
from .trace import Trace
from .verifier import Verifier


class Pipeline:
    def __init__(
        self,
        agents: List[Agent],
        governor: Optional[Governor] = None,
        default_checks: Optional[List] = None,
        trace: Optional[Trace] = None,
        strict: bool = True,
        stop_on_failure: bool = False,
        webhook: Optional[Any] = None,
    ) -> None:
        self.agents = agents
        self.governor = governor or Governor()
        self._default_checks = list(default_checks or [])
        self.trace = trace or Trace()
        self.strict = strict
        self.stop_on_failure = stop_on_failure
        # Any object with `.emit(payload: dict) -> dict`; fired on pipeline_end.
        self.webhook = webhook

    def run(self, task: str) -> Dict[str, Any]:
        # Each run gets a clean budget/audit slate and a scoped trace slice,
        # so a single Pipeline instance can be re-used across many runs.
        self.governor.reset()
        run_start = len(self.trace.events)

        ctx = Context({"task": task, "stage_outputs": {}, "warnings": []})
        self.trace.log(event="pipeline_start", task=task, strict=self.strict, stop_on_failure=self.stop_on_failure)

        current = task
        final_output: Optional[str] = None
        aborted: Optional[str] = None

        for agent in self.agents:
            if not self.governor.begin_call(agent.name):
                aborted = "budget_exhausted"
                ctx["warnings"].append(f"pipeline aborted: {aborted} before stage '{agent.name}'")
                self.trace.log(event="blocked", agent=agent.name, reason=aborted)
                break

            self.trace.log(event="agent_start", agent=agent.name)
            try:
                result = agent.act(current, ctx)
            except Exception as exc:  # noqa: BLE001 - no agent may crash the run
                result = AgentResult(agent=agent.name, output="", ok=False, error=f"agent raised: {exc}")
            self.governor.note_tokens(result.tokens or max(0, len(result.output)))

            if not result.ok:
                ctx["warnings"].append(f"{agent.name}: {result.error}")
                self.trace.log(event="agent_error", agent=agent.name, error=result.error, attempts=result.attempts)
                if self.stop_on_failure:
                    aborted = f"agent_failed:{agent.name}"
                    self.trace.log(event="blocked", agent=agent.name, reason=aborted)
                    break
                continue

            ctx["stage_outputs"][agent.name] = result.output
            current = result.output
            final_output = result.output

            # Per-agent verification: agent's own rubric first, else defaults.
            checks = agent.checks() or self._default_checks
            verdict = Verifier.verify(result.output, ctx, checks)
            ctx["stage_outputs"][f"{agent.name}_verdict"] = verdict.to_dict()
            if not verdict.verified:
                failing = [c for c in verdict.checks if not c["passed"]]
                ctx["warnings"].append(f"{agent.name}: verification failed: {failing}")
                self.trace.log(
                    event="agent_done",
                    agent=agent.name,
                    verified=False,
                    checks=verdict.checks,
                )
                if self.strict:
                    aborted = f"verification_failed:{agent.name}"
                    self.trace.log(event="blocked", agent=agent.name, reason=aborted)
                    break
            else:
                self.trace.log(
                    event="agent_done",
                    agent=agent.name,
                    verified=True,
                    checks=verdict.checks,
                )

        # Final governance gate (publish veto).
        decision = self.governor.evaluate("publish", ctx)
        self.trace.log(event="governor", action=decision.action, allow=decision.allow, reason=decision.reason)

        # In strict mode any warning blocks publish; in lenient mode the
        # decision is left entirely to the Governor's policies.
        warnings_block = self.strict and bool(ctx["warnings"])
        publishable = decision.allow and not warnings_block and aborted is None
        self.trace.log(event="pipeline_end", publishable=publishable, aborted=aborted)

        run_trace = self.trace.report()[run_start:]
        result: Dict[str, Any] = {
            "output": final_output,
            "publishable": bool(publishable),
            "aborted": aborted,
            "warnings": ctx["warnings"],
            "stage_outputs": ctx["stage_outputs"],
            "decision": decision.to_dict(),
            "budget": self.governor.budget(),
            "trace": run_trace,
            "trace_summary": Trace.summary_of(run_trace),
        }

        # Optional webhook: fire once on pipeline_end. A webhook must never
        # crash the run, so failures are captured in the status, not raised.
        if self.webhook is not None:
            payload = {
                "source": "agentflow",
                "task": task,
                "publishable": result["publishable"],
                "aborted": aborted,
                "decision": decision.to_dict(),
                "budget": self.governor.budget(),
                "warnings": ctx["warnings"],
                "trace_summary": Trace.summary_of(run_trace),
            }
            status: Any = None
            try:
                status = self.webhook.emit(payload)
            except Exception as exc:  # noqa: BLE001
                status = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            s = status if isinstance(status, dict) else {"ok": False, "error": str(status)}
            self.trace.log(
                event="webhook",
                ok=bool(s.get("ok")),
                status=s.get("status"),
                url=s.get("url"),
                error=s.get("error"),
            )
            result["webhook"] = status
        else:
            result["webhook"] = None

        return result
