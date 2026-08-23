"""Base agent.

An agent receives a ``task`` string plus the shared :class:`Context`, does
something with its LLM backend, and returns an :class:`AgentResult`.

Agents may also define a ``checks()`` method returning a list of verification
rubrics ``[(name, fn)]`` (see :mod:`agentflow.core.verifier`). When present,
the pipeline verifies that agent's output against its own rubric — this is the
"verifiability-by-design" hook that makes each agent self-documenting.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .context import Context
from .llm import LLMBackend, MockLLM


@dataclass
class AgentResult:
    agent: str
    output: str
    ok: bool = True
    error: str | None = None
    tokens: int = 0
    attempts: int = 1
    meta: Dict[str, Any] = field(default_factory=dict)


class Agent:
    """Minimal agent base class. Subclasses typically override :meth:`act`.

    Controls (constructor):
      retries  extra attempts when an LLM call fails (default 1). Subclasses
               that override ``act`` should use :meth:`call_llm` so they
               inherit the same retry behavior.
      delay    seconds between retry attempts (default 0.0, so offline runs
               stay instant; raise it for real remote backends).
    """

    role: str = "agent"

    def __init__(
        self,
        name: str,
        llm: LLMBackend | None = None,
        retries: int = 1,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self.llm = llm or MockLLM()
        self.retries = max(0, int(retries))
        self.delay = max(0.0, float(delay))

    def system(self) -> str:
        return f"You are a {self.role} named {self.name}. Be concise and factual."

    def checks(self) -> List[Tuple[str, Any]]:
        """Optional verification rubric for this agent's output.

        Returns a list of ``(name, fn)`` where ``fn(output, ctx) -> (passed, detail)``.
        The default is no checks.
        """
        return []

    def call_llm(self, user: str, system: Optional[str] = None) -> Tuple[str, int]:
        """Invoke the backend, retrying transient failures.

        Returns ``(output, attempts)``. Subclasses overriding :meth:`act`
        should route their LLM calls through this method to inherit retries.
        Raises the last error if every attempt fails — callers decide whether
        to surface that as ``AgentResult(ok=False)``.
        """
        sys_prompt = self.system() if system is None else system
        last_err: Optional[Exception] = None
        attempts = 0
        for _ in range(self.retries + 1):
            attempts += 1
            try:
                return self.llm.complete(sys_prompt, user), attempts
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempts <= self.retries and self.delay:
                    time.sleep(self.delay)
        assert last_err is not None
        raise last_err

    def act(self, task: str, ctx: Context) -> AgentResult:
        """Default behavior: one LLM call (with retries), wrapped in an AgentResult."""
        try:
            out, attempts = self.call_llm(task)
            return AgentResult(agent=self.name, output=out, ok=True, attempts=attempts)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the pipeline
            return AgentResult(agent=self.name, output="", ok=False, error=str(exc), attempts=self.retries + 1)
