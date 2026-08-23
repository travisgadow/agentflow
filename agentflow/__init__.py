"""agentflow — a governed, verifiable, multi-agent pipeline toolkit.

Project #1 in the AI agentic workflows portfolio. Encodes the three patterns
dominating agentic AI in mid-2026:

* multi-agent orchestration (coordinated stages),
* verifiability-by-design (each agent ships its own rubric),
* a governor / control-plane (budgets + publish gate + audit trail).

Zero runtime dependencies (Python stdlib only). Swap the LLM backend via env.
"""
__version__ = "0.2.0"

from .core import (  # noqa: F401
    Agent, AgentResult, Context, Governor, Decision, LLMBackend, LLMError,
    MockLLM, OpenAICompatible, make_backend, Pipeline, Trace, Verdict, Verifier,
)
from .agents import Researcher, Writer, FactChecker  # noqa: F401

__all__ = [
    "__version__",
    # core
    "Agent", "AgentResult", "Context", "Governor", "Decision",
    "LLMBackend", "LLMError", "MockLLM", "OpenAICompatible", "make_backend",
    "Pipeline", "Trace", "Verdict", "Verifier",
    # example agents
    "Researcher", "Writer", "FactChecker",
]
