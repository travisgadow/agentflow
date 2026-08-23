"""Shared blackboard passed between agents in a pipeline.

A lightweight, dependency-free key/value store with a few conveniences so
agents can read prior stage output, stash metadata, and accumulate warnings.
"""
from __future__ import annotations

from typing import Any, Dict


class Context:
    """A mutable shared context object threaded through every agent stage."""

    __slots__ = ("_data",)

    def __init__(self, initial: Dict[str, Any] | None = None) -> None:
        self._data: Dict[str, Any] = dict(initial or {})

    # dict-like
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, mapping: Dict[str, Any]) -> None:
        self._data.update(mapping)

    def keys(self):
        return self._data.keys()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)
