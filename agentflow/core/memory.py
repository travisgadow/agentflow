"""Persistent memory for agents.

A tiny, dependency-free store (JSON file on disk) that agents — or the demo, or
your own code — can `remember` a record against and later `recall`. This is the
"memory" pattern from agentflow's roadmap: recall past runs and refine.

Design goals
------------
* Zero dependencies (stdlib only); safe to run offline / in CI.
* `remember` appends a record; pass `key=` to upsert / dedupe.
* `recall(query)` is a lightweight substring/keyword search over a record's
  `text` / `topic` / `title` / `task` fields — no embeddings, no ML.
* Thread-safe (the parallel fan-out pipeline may touch it from worker threads).
* Human-readable on disk (pretty-printed JSON) and small by design.

Example:
    from agentflow import MemoryStore
    mem = MemoryStore("agentflow_memory.json")
    mem.remember("agentic AI governance", topic="agentic AI", publishable=True)
    hits = mem.recall("agentic AI", limit=3)
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _text_of(record: Dict[str, Any]) -> str:
    """Best-effort string form of a record, lowercased, for substring search."""
    parts: List[str] = []
    for field in ("text", "topic", "title", "task"):
        v = record.get(field)
        if isinstance(v, str):
            parts.append(v)
    if not parts:
        try:
            parts.append(json.dumps(record, sort_keys=True, default=str))
        except Exception:  # noqa: BLE001
            parts.append(str(record))
    return " \n".join(parts).lower()


class MemoryStore:
    """A small persistent memory a pipeline can `remember`/`recall` against.

    Records are plain dicts (plus a generated `id` and `ts`). Use `key` for
    stable, upsert-able entries; omit it for append-only logs.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._records: List[Dict[str, Any]] = []  # oldest -> newest
        if path:
            self._load()

    # --- persistence -------------------------------------------------------
    def _load(self) -> None:
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            recs = data.get("records", [])
        elif isinstance(data, list):
            recs = data
        else:
            recs = []
        self._records = [r for r in recs if isinstance(r, dict)]

    def _save(self) -> None:
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(
                {"version": 1, "records": self._records},
                fh, indent=2, sort_keys=True, default=str,
            )
        os.replace(tmp, self.path)

    # --- mutations ---------------------------------------------------------
    def remember(
        self,
        record: Any = None,
        *,
        key: Optional[str] = None,
        **fields: Any,
    ) -> Dict[str, Any]:
        """Store a record and return it.

        Accepts a `str` (stored as ``text``), a `dict`, or `None` plus keyword
        ``fields``. With a `key`, an existing record sharing that key is updated
        in place (upsert) and moved to the most-recent slot; without one, a new
        record is appended.
        """
        base: Dict[str, Any] = {}
        if isinstance(record, str):
            base = {"text": record}
        elif isinstance(record, dict):
            base = dict(record)
        elif record is not None:
            base = {"text": str(record)}
        base.update(fields)

        with self._lock:
            if key is not None:
                base["key"] = key
                for i, existing in enumerate(self._records):
                    if existing.get("key") == key:
                        merged = {**existing, **base}
                        merged["id"] = existing.get("id", _new_id())
                        merged["ts"] = round(time.time(), 3)
                        self._records.pop(i)
                        self._records.append(merged)
                        self._save()
                        return merged
                base.setdefault("id", _new_id())
            else:
                base.setdefault("id", _new_id())
            base["ts"] = round(time.time(), 3)
            self._records.append(base)
            self._save()
            return base

    def forget(self, key: str) -> bool:
        """Remove all records with the given `key`. Returns True if anything changed."""
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.get("key") != key]
            changed = len(self._records) != before
            if changed:
                self._save()
            return changed

    def clear(self) -> None:
        with self._lock:
            self._records = []
            self._save()

    # --- queries -----------------------------------------------------------
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            hits = [r for r in self._records if r.get("key") == key]
        return hits[-1] if hits else None

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Most recent records first."""
        with self._lock:
            return list(reversed(self._records[-max(0, int(limit)):]))

    def recall(self, query: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Newest-first records. If `query` is given, only those whose text matches.

        Matching is substring OR all-tokens-present (case-insensitive) — a
        deliberately simple, dependency-free search.
        """
        with self._lock:
            records = list(self._records)
        if query is None or str(query).strip() == "":
            out = records
        else:
            q = " ".join(str(query).lower().split())
            tokens = q.split()

            def _match(rec: Dict[str, Any]) -> bool:
                t = _text_of(rec)
                return (q in t) or bool(tokens) and all(tok in t for tok in tokens)

            out = [r for r in records if _match(r)]
        out = list(reversed(out))
        return out[: max(0, int(limit))]

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def __len__(self) -> int:
        return self.count()
