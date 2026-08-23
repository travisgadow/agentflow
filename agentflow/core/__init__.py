"""agentflow core: primitives for building governed multi-agent pipelines.

Public API:
    Context, Agent, AgentResult, LLMBackend, MockLLM, OpenAICompatible,
    Governor, Decision, Verifier, Verdict, Trace, Pipeline
"""
from .context import Context
from .agent import Agent, AgentResult
from .llm import LLMBackend, MockLLM, OpenAICompatible, make_backend
from .governor import Governor, Decision
from .verifier import Verifier, Verdict
from .trace import Trace
from .pipeline import Pipeline

__all__ = [
    "Context",
    "Agent",
    "AgentResult",
    "LLMBackend",
    "MockLLM",
    "OpenAICompatible",
    "make_backend",
    "Governor",
    "Decision",
    "Verifier",
    "Verdict",
    "Trace",
    "Pipeline",
]
