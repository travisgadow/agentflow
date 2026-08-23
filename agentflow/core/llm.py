"""LLM backends.

The pipeline is backend-agnostic: any object with a ``complete(system, user)``
method and a ``name`` attribute works. Two are provided out of the box:

* ``MockLLM``            - deterministic, offline, zero-cost. Great for tests,
                           CI, and demos where the *workflow* (orchestration,
                           governance, verification) is the point, not the prose.
* ``OpenAICompatible``   - any OpenAI Chat Completions endpoint (OpenAI,
                           Azure, vLLM, Ollama, LM Studio, ...). Stdlib only,
                           with retry/backoff and optional sampling controls.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional


class LLMError(RuntimeError):
    """Raised when the backend cannot complete a call (auth, 4xx, retries exhausted)."""


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

    For tests you can give it a ``flaky`` count: the first ``flaky`` calls
    raise ``LLMError`` before succeeding — handy for exercising retry paths.
    """

    name = "mock"

    def __init__(self, profile: Optional[Dict[str, str]] = None, flaky: int = 0) -> None:
        self._profile = {k.lower(): v for k, v in (profile or {}).items()}
        self._flaky = max(0, int(flaky))

    def complete(self, system: str, user: str) -> str:
        if self._flaky > 0:
            self._flaky -= 1
            raise LLMError("(mock) simulated transient failure")
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

    Controls:
      retries            extra attempts after the first failure (default 2)
      backoff            seconds to wait before retry #1; doubles each time
      temperature        sampling temperature (0.0-2.0); only sent when set
      max_tokens         cap on completion tokens; only sent when set
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
        retries: int = 2,
        backoff: float = 0.5,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("AGENTFLOW_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = (base_url or os.getenv("AGENTFLOW_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("AGENTFLOW_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.backoff = max(0.0, float(backoff))
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.name = f"openai-compat:{self.model}"

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise LLMError(
                "No API key set. Provide AGENTFLOW_API_KEY/OPENAI_API_KEY, "
                "or use MockLLM for a fully offline run."
            )
        payload: Dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        data: Optional[dict] = None
        last_err: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read().decode("utf-8", "replace")[:300]
                except Exception:  # noqa: BLE001
                    detail = ""
                last_err = LLMError(f"HTTP {e.code} from {self.base_url}: {detail}")
                # 4xx is not going to heal by retrying (auth, bad request, ...).
                if 400 <= e.code < 500:
                    raise last_err
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = LLMError(f"request to {self.base_url} failed: {e}")
            if attempt < self.retries:
                time.sleep(self.backoff * (2 ** attempt))
        if data is None:
            raise last_err or LLMError("LLM request failed after retries")
        return data["choices"][0]["message"]["content"]


def make_backend(name: str = "mock", **kwargs) -> LLMBackend:
    """Factory so examples/tests can switch backends by name.

    Extra kwargs that a given backend doesn't accept (e.g. ``temperature``
    passed to ``MockLLM``) are silently dropped, so a single call site can
    configure all backends uniformly.
    """
    key = name.lower()
    if key in ("mock", "offline"):
        accepted = {"profile", "flaky"}
        return MockLLM(**{k: v for k, v in kwargs.items() if k in accepted})
    if key in ("openai", "openai-compat", "ollama", "vllm", "remote"):
        return OpenAICompatible(**kwargs)
    raise ValueError(f"Unknown backend: {name!r}. Use 'mock' or 'openai'.")
