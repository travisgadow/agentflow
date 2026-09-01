"""agentflow — a governed, verifiable, multi-agent pipeline toolkit.

Project #1 in the AI agentic workflows portfolio. Encodes the patterns
dominating agentic AI in mid-2026:

* multi-agent orchestration (coordinated stages),
* verifiability-by-design (each agent ships its own rubric),
* a governor / control-plane (budgets + publish gate + audit trail),
* memory (recall past runs), parallel fan-out (swarm stages),
* webhook emission on pipeline end,
* and (0.4) an interactive web-based UI for running & inspecting pipelines.

Zero runtime dependencies (Python stdlib only). Swap the LLM backend via env.
"""
__version__ = "0.4.0"

from .core import (  # noqa: F401
    Agent, AgentResult, Context, Governor, Decision, LLMBackend, LLMError,
    MockLLM, OpenAICompatible, make_backend, Pipeline, Trace, Verdict, Verifier,
    MemoryStore, FanOut, WebhookNotifier,
)
from .agents import Researcher, Writer, FactChecker  # noqa: F401
from .webui import WebUIServer  # noqa: F401

__all__ = [
    "__version__",
    # core
    "Agent", "AgentResult", "Context", "Governor", "Decision",
    "LLMBackend", "LLMError", "MockLLM", "OpenAICompatible", "make_backend",
    "Pipeline", "Trace", "Verdict", "Verifier",
    "MemoryStore", "FanOut", "WebhookNotifier",
    # example agents
    "Researcher", "Writer", "FactChecker",
    # web ui
    "WebUIServer",
]
