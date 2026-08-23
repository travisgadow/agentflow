"""Governor (agent control-plane).

A thin policy + budget layer that sits around the pipeline and can:

* enforce budgets (max agent calls, max total "tokens"), and
* gate actions (e.g. ``publish``) with pluggable policies that can *veto*
  based on context.

This mirrors the "control plane for autonomous agents" pattern that is
dominating enterprise agentic AI: the layer that decides *what an agent is
allowed to do*, not just who it is.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from .context import Context


@dataclass
class Decision:
    action: str
    allow: bool
    reason: str

    def to_dict(self) -> dict:
        return {"action": self.action, "allow": self.allow, "reason": self.reason}


# A policy is a function ``policy(action, ctx) -> (allow: bool, reason: str)``.
Policy = Callable[[str, Context], Tuple[bool, str]]


class Governor:
    """Budgets + policy gates for a pipeline run."""

    def __init__(
        self,
        policies: Optional[List[Tuple[str, Policy]]] = None,
        max_agent_calls: Optional[int] = None,
        max_total_tokens: Optional[int] = None,
    ) -> None:
        self.policies: List[Tuple[str, Policy]] = list(policies or [])
        self.max_agent_calls = max_agent_calls
        self.max_total_tokens = max_total_tokens
        self._calls = 0
        self._tokens = 0
        self.audit: List[Decision] = []

    # --- budgets -----------------------------------------------------------
    def begin_call(self) -> bool:
        """Reserve one agent call. Returns False if the budget is exhausted."""
        if self.max_agent_calls is not None and self._calls >= self.max_agent_calls:
            return False
        if self.max_total_tokens is not None and self._tokens >= self.max_total_tokens:
            return False
        self._calls += 1
        return True

    def note_tokens(self, n: int) -> None:
        self._tokens += max(0, n)

    def budget(self) -> dict:
        return {
            "max_agent_calls": self.max_agent_calls,
            "max_total_tokens": self.max_total_tokens,
            "calls_used": self._calls,
            "tokens_used": self._tokens,
        }

    # --- policy gates ------------------------------------------------------
    def evaluate(self, action: str, ctx: Context) -> Decision:
        """Run all policies for ``action``; the first failing policy vetoes."""
        for name, policy in self.policies:
            try:
                allow, reason = policy(action, ctx)
            except Exception as exc:  # noqa: BLE001 - a broken policy blocks by default
                decision = Decision(action, False, f"policy:{name} raised: {exc}")
                self.audit.append(decision)
                return decision
            if not allow:
                decision = Decision(action, False, f"policy:{name}: {reason}")
                self.audit.append(decision)
                return decision
        decision = Decision(action, True, "all policies passed")
        self.audit.append(decision)
        return decision
