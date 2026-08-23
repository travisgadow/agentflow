"""Append-only audit trail.

Every pipeline event (stage start/done, verification verdicts, governance
decisions) is recorded as a structured event. In-memory always; optionally
mirrored to a JSONL file for post-hoc inspection.
"""
from __future__ import annotations

import json
import time
from typing import Any, List, Optional


class Trace:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self.events: List[dict] = []

    def log(self, **kwargs: Any) -> None:
        event = dict(kwargs)
        event["ts"] = round(time.time(), 3)
        self.events.append(event)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")

    def report(self) -> List[dict]:
        return list(self.events)

    def summary(self) -> dict:
        return self.summary_of(self.events)

    @staticmethod
    def summary_of(events: List[dict]) -> dict:
        by_type: dict[str, int] = {}
        for e in events:
            key = e.get("event", "?")
            by_type[key] = by_type.get(key, 0) + 1
        return {"total_events": len(events), "by_type": by_type}
