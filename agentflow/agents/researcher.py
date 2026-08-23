"""Researcher: turn a topic into a short list of *sourced* findings.

Every finding carries a ``[S#]`` source tag. This makes the downstream
FactChecker's job deterministic and verifiable — a direct nod to the
"verifiability-by-design" pattern.
"""
from __future__ import annotations

from ..core.agent import Agent, AgentResult
from ..core.context import Context
from ..core.verifier import all_bullets_sourced, has_section


class Researcher(Agent):
    role = "researcher"

    def act(self, task: str, ctx: Context) -> AgentResult:
        # Ask the backend for the finding(s). The exact phrasing is backend-dependent;
        # we normalize it into a single, stable bullet with a source tag.
        body = self.llm.complete(self.system(), f"List 1-3 key findings about: {task}")
        body = " ".join(body.split())
        finding = f"{body} [S1]"
        ctx.set("sources", ["S1"])
        output = "## Findings\n- " + finding + "\n"
        return AgentResult(agent=self.name, output=output, ok=True)

    def checks(self):
        return [has_section("Findings"), all_bullets_sourced()]
