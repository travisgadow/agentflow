"""Verification layer.

Encodes the "verifiability-by-design" principle: every piece of agent output
can be checked against an explicit rubric of small, composable checks. A check
is a function ``fn(output, ctx) -> (passed: bool, detail: str)``.

``Verifier`` is stateless: it just runs a list of checks and returns a
:class:`Verdict`. The reusable check factories below cover the common cases.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Tuple

from .context import Context


@dataclass
class Verdict:
    verified: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"verified": self.verified, "checks": self.checks}


# --- reusable check factories ---------------------------------------------

def has_section(title: str):
    """Pass if the output contains a markdown heading matching ``title``."""
    def check(output: str, ctx: Context):
        want = title.strip().lower()
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                if stripped.lstrip("#").strip().lower() == want:
                    return True, f"section '{title}' present"
        return False, f"missing section '{title}'"
    return f"has_section:{title}", check


def min_length(n: int):
    def check(output: str, ctx: Context):
        return len(output) >= n, f"len={len(output)} (need >= {n})"
    return f"min_length:{n}", check


def max_length(n: int):
    """Pass if the output is at most ``n`` characters (useful for tight slots)."""
    def check(output: str, ctx: Context):
        return len(output) <= n, f"len={len(output)} (need <= {n})"
    return f"max_length:{n}", check


def matches(pattern: str, flags: int = 0):
    """Pass if the output matches ``pattern`` (regex, case-insensitive by default)."""
    rx = re.compile(pattern, flags or re.IGNORECASE)
    def check(output: str, ctx: Context):
        m = rx.search(output or "")
        return bool(m), ("match: " + (m.group(0)[:60] if m else "no match"))
    return f"matches:{pattern}", check


def no_match(pattern: str, flags: int = 0):
    """Pass if the output does NOT match ``pattern`` (regex, case-insensitive by default).

    Typical use: ``no_match(r"\\$\\d+.*\\b(week|day)s\\b")`` to veto hard price+date
    commitments in outbound copy.
    """
    rx = re.compile(pattern, flags or re.IGNORECASE)
    def check(output: str, ctx: Context):
        m = rx.search(output or "")
        return not m, ("clean" if not m else "banned pattern found: " + (m.group(0)[:60] if m else ""))
    return f"no_match:{pattern}", check


def all_bullets_sourced(tag: str = "[S"):
    """Pass if every top-level bullet line carries the given source tag."""
    def check(output: str, ctx: Context):
        bullets = [l for l in output.splitlines() if l.strip().startswith("-")]
        if not bullets:
            return False, "no bullet lines found"
        missing = [l for l in bullets if tag not in l]
        return (not missing), f"{len(bullets) - len(missing)}/{len(bullets)} bullets sourced"
    return "all_bullets_sourced", check


class Verifier:
    """Runs a list of checks against an output and returns a :class:`Verdict`."""

    @staticmethod
    def verify(output: str, ctx: Context, checks: List[Tuple[str, Callable]]) -> Verdict:
        results: List[Dict[str, Any]] = []
        ok = True
        for name, fn in checks:
            try:
                passed, detail = fn(output, ctx)
            except Exception as exc:  # noqa: BLE001 - a broken check is a failed check
                passed, detail = False, f"check raised: {exc}"
            passed = bool(passed)
            results.append({"check": name, "passed": passed, "detail": detail})
            ok = ok and passed
        return Verdict(verified=ok, checks=results)
