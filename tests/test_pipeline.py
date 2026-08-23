"""Tests for the agentflow core + example workflow. All offline/deterministic."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentflow.core import Context, Governor, MockLLM, Pipeline, Verifier
from agentflow.core.verifier import has_section, min_length
from agentflow.agents import Researcher, Writer, FactChecker


def _pipeline():
    llm = MockLLM()
    gov = Governor(policies=[], max_agent_calls=10)
    return Pipeline([
        Researcher(name="Researcher", llm=llm),
        Writer(name="Writer", llm=llm),
        FactChecker(name="FactChecker", llm=llm),
    ], governor=gov)


def test_researcher_output_is_sourced_and_verified():
    p = _pipeline()
    res = p.run("agentic AI")
    researcher_out = res["stage_outputs"]["Researcher"]
    assert "## Findings" in researcher_out
    assert "[S1]" in researcher_out
    researcher_verdict = res["stage_outputs"]["Researcher_verdict"]
    assert researcher_verdict["verified"] is True


def test_full_report_has_sections():
    p = _pipeline()
    res = p.run("multi-agent orchestration")
    out = res["output"]
    # The final (FactChecker) output folds Summary, Key Findings, Sources, Verification.
    for section in ("## Summary", "## Key Findings", "## Sources", "## Verification"):
        assert section in out, f"missing {section}"
    assert "overall: PASS" in out
    # Findings is produced by the Researcher stage.
    assert "## Findings" in res["stage_outputs"]["Researcher"]


def test_pipeline_publishable_when_clean():
    p = _pipeline()
    res = p.run("verifiability")
    assert res["publishable"] is True
    assert res["decision"]["allow"] is True
    assert res["warnings"] == []


def test_governor_budget_blocks():
    llm = MockLLM()
    gov = Governor(max_agent_calls=1)  # allow exactly one call
    p = Pipeline([
        Researcher(name="R1", llm=llm),
        Writer(name="W1", llm=llm),
        FactChecker(name="F1", llm=llm),
    ], governor=gov)
    res = p.run("budget")
    assert res["aborted"] == "budget_exhausted"
    assert res["publishable"] is False


def test_governor_veto_on_warnings():
    from agentflow.core.governor import Governor as G

    def veto(action, ctx):
        if action == "publish" and ctx.get("warnings"):
            return False, "warnings present"
        return True, "ok"

    llm = MockLLM()
    gov = G(policies=[("veto", veto)])
    # Force a warning by making Researcher fail
    class Broken(Researcher):
        def act(self, task, ctx):
            from agentflow.core.agent import AgentResult
            return AgentResult(agent=self.name, output="", ok=False, error="boom")

    p = Pipeline([Broken(name="B", llm=llm), Writer(name="W", llm=llm)], governor=gov)
    res = p.run("veto test")
    assert res["publishable"] is False
    assert any("B" in w for w in res["warnings"])


def test_verifier_reusable_checks():
    ctx = Context()
    ok = Verifier.verify("# Title\n\n## Summary\nbody", ctx, [has_section("Summary"), min_length(10)])
    assert ok.verified is True
    bad = Verifier.verify("no sections", ctx, [has_section("Summary")])
    assert bad.verified is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
