"""Emit pipeline events to a webhook.

A minimal, stdlib-only HTTP POSTer. A :class:`Pipeline` optionally takes a
`webhook` (any object with ``.emit(payload: dict) -> dict``) and calls it once
on ``pipeline_end`` with a compact, JSON-serialisable summary of the run.

A webhook must never crash the run: :class:`WebhookNotifier.emit` swallows
transport/HTTP errors and returns a status dict describing the outcome.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class WebhookNotifier:
    """POST a JSON payload to ``url`` (stdlib only) with optional retries.

    Configuration:
      headers   extra HTTP headers (defaults set ``Content-Type: application/json``)
      timeout   per-request timeout in seconds
      retries   extra attempts after the first failure
      backoff   seconds before retry #1; doubles each attempt
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
        retries: int = 0,
        backoff: float = 0.2,
        name: str = "webhook",
    ) -> None:
        self.url = url
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.timeout = int(timeout)
        self.retries = max(0, int(retries))
        self.backoff = max(0.0, float(backoff))
        self.name = name
        self.last: Optional[Dict[str, Any]] = None
        self.errors: List[str] = []

    def emit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST ``payload`` as JSON. Returns a status dict; never raises."""
        body = json.dumps(payload, default=str).encode("utf-8")
        last_err: Optional[str] = None
        status: Optional[int] = None
        ok = False

        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                self.url, data=body, headers=self.headers, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.getcode()
                ok = 200 <= status < 300
                if ok:
                    last_err = None
                    break
                last_err = f"HTTP {status}"
            except urllib.error.HTTPError as e:
                status = e.code
                last_err = f"HTTP {e.code}"
            except Exception as exc:  # noqa: BLE001 - a webhook must not break the run
                last_err = f"{type(exc).__name__}: {exc}"
            if attempt < self.retries:
                time.sleep(self.backoff * (2 ** attempt))

        self.last = {"ok": ok, "status": status, "url": self.url, "error": last_err}
        if last_err:
            self.errors.append(last_err)
        return self.last
