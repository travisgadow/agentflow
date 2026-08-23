"""FactChecker: append a Verification section that confirms every finding is sourced.

This is the "verifiability" step. It does not trust prose — it checks the
structural invariant (every finding bullet carries a source tag) and records a
PASS/FAIL verdict that the Governor can gate on.
"""
from __future__ import annotations

from ..core.agent import Agent, AgentResult
from ..core.context import Context
from ..core.verifier import has_section


class FactChecker(Agent):
    role = "fact-checker"

    def _findings_bullets(self, ctx: Context):
        # Prefer the Writer's report, fall back to the Researcher's findings.
        for key in ("Writer", "Researcher"):
            text = ctx.get("stage_outputs", {}).get(key, "")
            # Keep only lines that look like findings (contain a [S#] tag).
            found = [l for l in text.splitlines() if "[S" in l and l.strip().startswith("-")]
            if found:
                return found
        return []

    def act(self, task: str, ctx: Context) -> AgentResult:
        bullets = self._findings_bullets(ctx)
        all_sourced = bool(bullets) and all("[S" in b for b in bullets)
        ctx.set("all_sourced", all_sourced)
        status = "PASS" if all_sourced else "FAIL"
        verification = (
            "## Verification\n"
            f"- overall: {status} ({len(bullets)} findings checked)\n"
            f"- sourcing: {'every finding carries a [S#] tag' if all_sourced else 'one or more findings missing a source tag'}\n"
        )
        base = ctx.get("stage_outputs", {}).get("Writer", "")
        output = (base + "\n" + verification).rstrip() + "\n"
        return AgentResult(agent=self.name, output=output, ok=True)

    def checks(self):
        def overall_pass(output: str, ctx: Context):
            ok = bool(ctx.get("all_sourced", False))
            return ok, ("all findings sourced" if ok else "unsourced findings present")
        return [has_section("Verification"), ("overall_pass", overall_pass)]
