"""Parallel fan-out stage ("swarm").

Runs a set of agents *concurrently* (stdlib :mod:`concurrent.futures`) and
merges their outputs into a single stage result, so a :class:`Pipeline` can use
a :class:`FanOut` exactly like any other stage. This is the "parallel stages /
swarm" pattern from agentflow's roadmap — useful when independent sub-tasks
(e.g. researching several angles at once) can be done in parallel and combined.

A :class:`FanOut` is duck-typed like an :class:`Agent` (it exposes `.name`,
`.act(task, ctx)` and `.checks()`), so :class:`Pipeline` needs no special-casing.

Budget note
-----------
A :class:`FanOut` counts as **one** governed stage call (its sub-agents' LLM
calls are not individually budgeted). Set the Governor's ``max_agent_calls``
accordingly if you fan out widely.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .agent import AgentResult
from .context import Context

MergeFn = Callable[[str, Context, List[AgentResult]], str]


def _safe_act(agent: Any, task: str, ctx: Context) -> AgentResult:
    """Run one sub-agent, converting any exception into an ``ok=False`` result."""
    try:
        result = agent.act(task, ctx)
        if isinstance(result, AgentResult):
            return result
        return AgentResult(agent=getattr(agent, "name", "agent"), output=str(result), ok=True)
    except Exception as exc:  # noqa: BLE001 - a crashing sub-agent is a failure, not a crash
        return AgentResult(
            agent=getattr(agent, "name", "agent"),
            output="", ok=False, error=f"{type(exc).__name__}: {exc}",
        )


def default_merge(task: str, ctx: Context, results: List[AgentResult]) -> str:
    """Combine sub-agent outputs into a single sectioned document.

    Failed sub-agents are noted (not silently dropped) so a downstream
    verifier or reader can see what happened.
    """
    parts: List[str] = []
    for r in results:
        if r.ok and (r.output or "").strip():
            parts.append(f"### {r.agent}\n{r.output.strip()}")
    doc = "\n\n".join(parts) if parts else "(no sub-agent produced output)"
    failed = [r for r in results if not r.ok]
    if failed:
        names = ", ".join(r.agent for r in failed)
        doc += f"\n\n> note: {len(failed)} sub-agent(s) did not complete: {names}"
    return doc


class FanOut:
    """Run multiple agents in parallel and merge their outputs into one result."""

    def __init__(
        self,
        name: str,
        agents: List[Any],
        merge: Optional[MergeFn] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        self.name = name
        if not agents:
            raise ValueError("FanOut needs at least one agent")
        self.agents = list(agents)
        self.merge = merge or default_merge
        self.max_workers = max_workers or max(1, min(8, len(self.agents)))

    def checks(self):
        """No default rubric; add one via your own :class:`Pipeline` default checks."""
        return []

    def act(self, task: str, ctx: Context) -> AgentResult:
        started = time.time()
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            # pool.map preserves input order, so the merge is deterministic.
            results = list(pool.map(lambda a: _safe_act(a, task, ctx), self.agents))
        elapsed = round(time.time() - started, 3)

        merged = self.merge(task, ctx, results)
        ok = any(r.ok for r in results)
        tokens = sum(max(0, r.tokens) for r in results)
        attempts = max((r.attempts for r in results), default=1)
        errors = [f"{r.agent}: {r.error}" for r in results if not r.ok]

        meta: Dict[str, Any] = {
            "fanout": len(results),
            "succeeded": sum(1 for r in results if r.ok),
            "failed": len(errors),
            "errors": errors,
            "elapsed": elapsed,
        }
        # Surface each sub-agent's output on the context for downstream stages/tests.
        stage_outputs = ctx.get("stage_outputs")
        if stage_outputs is None:
            stage_outputs = {}
            ctx.set("stage_outputs", stage_outputs)
        for r in results:
            if r.ok and (r.output or "").strip():
                stage_outputs[f"fanout.{self.name}.{r.agent}"] = r.output

        return AgentResult(
            agent=self.name,
            output=merged,
            ok=ok,
            tokens=tokens,
            attempts=attempts,
            meta=meta,
            error=errors[0] if (errors and not ok) else None,
        )
