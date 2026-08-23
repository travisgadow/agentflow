"""LLM backends.

The pipeline is backend-agnostic: any object with a ``complete(system, user)``
method and a ``name`` attribute works. Two are provided out of the box:

* ``MockLLM``            - deterministic, offline, zero-cost. Great for tests,
                           CI, and demos where the *workflow* (orchestration,
                           governance, verification) is the point, not the prose.
* ``OpenAICompatible``   - any OpenAI Chat Completions endpoint (OpenAI,
                           Azure, vLLM, Ollama, LM Studio, ...). Stdlib only.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Dict, Optional


class LLMBackend:
    """Duck-typed interface every backend must satisfy."""

    name: str = "abstract"

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class MockLLM(LLMBackend):
    """Deterministic offline backend.

    It produces stable, non-network output derived from the prompt so runs are
    reproducible. If you provide a ``profile`` dict keyed by role name, the
    matching canned text is returned for that role.
    """

    name = "mock"

    def __init__(self, profile: Optional[Dict[str, str]] = None) -> None:
        self._profile = {k.lower(): v for k, v in (profile or {}).items()}

    def complete(self, system: str, user: str) -> str:
        # Deterministic: return role-specific canned text when available.
        for role, text in self._profile.items():
            if role in system.lower():
                return text
        # Otherwise derive a stable one-line response from the request.
        topic = next((line for line in user.strip().splitlines() if line.strip()), "the task")
        return f"(mock) Deterministic response about: {topic}"


class OpenAICompatible(LLMBackend):
    """Stdlib client for any OpenAI Chat Completions compatible endpoint.

    Configuration via constructor args or environment:
      AGENTFLOW_API_KEY / OPENAI_API_KEY
      AGENTFLOW_BASE_URL / OPENAI_BASE_URL  (default https://api.openai.com/v1)
      AGENTFLOW_MODEL  / OPENAI_MODEL       (default gpt-4o-mini)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key or os.getenv("AGENTFLOW_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = (base_url or os.getenv("AGENTFLOW_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("AGENTFLOW_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.timeout = timeout
        self.name = f"openai-compat:{self.model}"

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError(
                "No API key set. Provide AGENTFLOW_API_KEY/OPENAI_API_KEY, "
                "or use MockLLM for a fully offline run."
            )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def make_backend(name: str = "mock", **kwargs) -> LLMBackend:
    """Factory so examples/tests can switch backends by name."""
    key = name.lower()
    if key in ("mock", "offline"):
        return MockLLM(**kwargs)
    if key in ("openai", "openai-compat", "ollama", "vllm", "remote"):
        return OpenAICompatible(**kwargs)
    raise ValueError(f"Unknown backend: {name!r}. Use 'mock' or 'openai'.")
