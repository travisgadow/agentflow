"""Writer: turn findings into a short structured report with a Summary and Sources.

The Writer *composes* a report from the Researcher's sourced findings so the
output is coherent on any backend (including the offline MockLLM). If the
backend returns real prose, it's folded into the Summary as the "analysis".
"""
from __future__ import annotations

from ..core.agent import Agent, AgentResult
from ..core.context import Context
from ..core.verifier import has_section, min_length


class Writer(Agent):
    role = "writer"

    def _upstream(self) -> str:
        return "Researcher"

    def act(self, task: str, ctx: Context) -> AgentResult:
        findings = ctx.get("stage_outputs", {}).get(self._upstream(), "").strip()
        bullets = [l.strip() for l in findings.splitlines() if l.strip().startswith("-")]
        title = ctx.get("task", "Report")

        # Real prose analysis when the backend produces meaningful text.
        # Route through call_llm so this stage inherits the agent's retry control.
        analysis, attempts = self.call_llm(f"Summarize these findings:\n{findings}")
        analysis = " ".join(analysis.split()).strip()
        if not analysis:
            analysis = "See the sourced findings below."

        finding_lines = "\n".join(bullets) if bullets else "- (no findings)"
        sources = ctx.get("sources", []) or []
        sources_block = "\n".join(f"- {s}" for s in sources) if sources else "- (none)"

        output = (
            f"# {title}\n\n"
            f"## Summary\n{analysis}\n\n"
            f"## Key Findings\n{finding_lines}\n\n"
            f"## Sources\n{sources_block}\n"
        )
        return AgentResult(agent=self.name, output=output, ok=True, attempts=attempts)

    def checks(self):
        return [has_section("Summary"), has_section("Key Findings"), has_section("Sources"), min_length(60)]
