"""Base agent.

An agent receives a ``task`` string plus the shared :class:`Context`, does
something with its LLM backend, and returns an :class:`AgentResult`.

Agents may also define a ``checks()`` method returning a list of verification
rubrics ``[(name, fn)]`` (see :mod:`agentflow.core.verifier`). When present,
the pipeline verifies that agent's output against its own rubric — this is the
"verifiability-by-design" hook that makes each agent self-documenting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .context import Context
from .llm import LLMBackend, MockLLM


@dataclass
class AgentResult:
    agent: str
    output: str
    ok: bool = True
    error: str | None = None
    tokens: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


class Agent:
    """Minimal agent base class. Subclasses typically override :meth:`act`."""

    role: str = "agent"

    def __init__(self, name: str, llm: LLMBackend | None = None) -> None:
        self.name = name
        self.llm = llm or MockLLM()

    def system(self) -> str:
        return f"You are a {self.role} named {self.name}. Be concise and factual."

    def checks(self) -> List[Tuple[str, Any]]:
        """Optional verification rubric for this agent's output.

        Returns a list of ``(name, fn)`` where ``fn(output, ctx) -> (passed, detail)``.
        The default is no checks.
        """
        return []

    def act(self, task: str, ctx: Context) -> AgentResult:
        """Default behavior: one LLM call, wrapped in an AgentResult."""
        try:
            out = self.llm.complete(self.system(), task)
            return AgentResult(agent=self.name, output=out, ok=True)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the pipeline
            return AgentResult(agent=self.name, output="", ok=False, error=str(exc))
