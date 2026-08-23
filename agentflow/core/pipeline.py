"""The orchestrator.

Runs a sequence of agents, threading a shared Context, and applies:

* per-agent **verification** (each agent can ship its own rubric),
* a **governor** for budgets + a final publish gate,
* a full **trace** of every decision.

The result exposes the final output, whether it was deemed publishable, any
warnings, the governance decision, and the trace.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .agent import Agent
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
    ) -> None:
        self.agents = agents
        self.governor = governor or Governor()
        self._default_checks = list(default_checks or [])
        self.trace = trace or Trace()

    def run(self, task: str) -> Dict[str, Any]:
        ctx = Context({"task": task, "stage_outputs": {}, "warnings": []})
        self.trace.log(event="pipeline_start", task=task)

        current = task
        final_output: Optional[str] = None
        aborted = None

        for agent in self.agents:
            if not self.governor.begin_call():
                aborted = "budget_exhausted"
                ctx["warnings"].append(f"pipeline aborted: {aborted} before {agent.name}")
                self.trace.log(event="blocked", agent=agent.name, reason=aborted)
                break

            self.trace.log(event="agent_start", agent=agent.name)
            result = agent.act(current, ctx)
            self.governor.note_tokens(result.tokens or max(0, len(result.output)))

            if not result.ok:
                ctx["warnings"].append(f"{agent.name}: {result.error}")
                self.trace.log(event="agent_error", agent=agent.name, error=result.error)
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
                ctx["warnings"].append(f"{agent.name}: {failing}")
            self.trace.log(
                event="agent_done",
                agent=agent.name,
                verified=verdict.verified,
                checks=verdict.checks,
            )

        # Final governance gate (publish veto).
        decision = self.governor.evaluate("publish", ctx)
        self.trace.log(event="governor", action=decision.action, allow=decision.allow, reason=decision.reason)

        publishable = decision.allow and not ctx["warnings"] and aborted is None
        self.trace.log(event="pipeline_end", publishable=publishable)

        return {
            "output": final_output,
            "publishable": bool(publishable),
            "aborted": aborted,
            "warnings": ctx["warnings"],
            "stage_outputs": ctx["stage_outputs"],
            "decision": decision.to_dict(),
            "budget": self.governor.budget(),
            "trace": self.trace.report(),
            "trace_summary": self.trace.summary(),
        }
