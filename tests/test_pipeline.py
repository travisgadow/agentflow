"""Tests for the agentflow core + example workflow. All offline/deterministic."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentflow import (
    Agent, AgentResult, Context, FactChecker, Governor, LLMError, MockLLM, Pipeline,
    Researcher, Verifier, Writer,
)
from agentflow.core.llm import OpenAICompatible
from agentflow.core.verifier import has_section, max_length, matches, min_length, no_match


def _pipeline(strict: bool = True, stop_on_failure: bool = False, max_calls: int | None = 10):
    llm = MockLLM()
    gov = Governor(policies=[], max_agent_calls=max_calls)
    return Pipeline([
        Researcher(name="Researcher", llm=llm),
        Writer(name="Writer", llm=llm),
        FactChecker(name="FactChecker", llm=llm),
    ], governor=gov, strict=strict, stop_on_failure=stop_on_failure)


# --- 0.1.x behavior (regression) ------------------------------------------

def test_researcher_output_is_sourced_and_verified():
    res = _pipeline().run("agentic AI")
    researcher_out = res["stage_outputs"]["Researcher"]
    assert "## Findings" in researcher_out
    assert "[S1]" in researcher_out
    assert res["stage_outputs"]["Researcher_verdict"]["verified"] is True


def test_full_report_has_sections():
    res = _pipeline().run("multi-agent orchestration")
    out = res["output"]
    for section in ("## Summary", "## Key Findings", "## Sources", "## Verification"):
        assert section in out, f"missing {section}"
    assert "overall: PASS" in out
    assert "## Findings" in res["stage_outputs"]["Researcher"]


def test_pipeline_publishable_when_clean():
    res = _pipeline().run("verifiability")
    assert res["publishable"] is True
    assert res["decision"]["allow"] is True
    assert res["warnings"] == []


def test_governor_budget_blocks():
    res = _pipeline(max_calls=1).run("budget")
    assert res["aborted"] == "budget_exhausted"
    assert res["publishable"] is False
    # Only the first stage ran.
    assert "Researcher" in res["stage_outputs"]
    assert "Writer" not in res["stage_outputs"]


def test_governor_veto_on_warnings():
    from agentflow.core.governor import Governor as G

    def veto(action, ctx):
        if action == "publish" and ctx.get("warnings"):
            return False, "warnings present"
        return True, "ok"

    class Broken(Researcher):
        def act(self, task, ctx):
            return AgentResult(agent=self.name, output="", ok=False, error="boom")

    gov = G(policies=[("veto", veto)])
    p = Pipeline([Broken(name="B", llm=MockLLM()), Writer(name="W", llm=MockLLM())], governor=gov)
    res = p.run("veto test")
    assert res["publishable"] is False
    assert any("B" in w for w in res["warnings"])


def test_verifier_reusable_checks():
    ctx = Context()
    ok = Verifier.verify("# Title\n\n## Summary\nbody", ctx, [has_section("Summary"), min_length(10)])
    assert ok.verified is True
    bad = Verifier.verify("no sections", ctx, [has_section("Summary")])
    assert bad.verified is False


# --- new in 0.2: verifier checks -------------------------------------------

def test_matches_and_no_match_checks():
    ctx = Context()
    good = Verifier.verify("Total: 42 words", ctx, [matches(r"total:\s*\d+")])
    assert good.verified is True
    bad = Verifier.verify("no digits here", ctx, [matches(r"total:\s*\d+")])
    assert bad.verified is False
    clean = Verifier.verify("no price promise", ctx, [no_match(r"\$\d+.*\b(week|day)s\b")])
    assert clean.verified is True
    over = Verifier.verify("we'll do it for $199 within 5 days", ctx, [no_match(r"\$\d+.*\b(week|day)s\b")])
    assert over.verified is False


def test_max_length_check():
    ctx = Context()
    assert Verifier.verify("short", ctx, [max_length(20)]).verified is True
    assert Verifier.verify("x" * 100, ctx, [max_length(20)]).verified is False


# --- new in 0.2: run modes ---------------------------------------------------

def test_strict_mode_stops_on_verification_failure():
    llm = MockLLM()

    class Unchecked(Writer):
        def act(self, task, ctx):
            # Bypass the LLM entirely so this test never touches the network.
            out = ("## Nonexistent-Only\nbody\n")
            return AgentResult(agent=self.name, output=out, ok=True)

        def checks(self):
            return [has_section("Findings")]  # will fail against act()'s output

    p = Pipeline([Researcher(name="R", llm=llm), Unchecked(name="W", llm=llm)], strict=True)
    res = p.run("strict")
    assert res["aborted"] == "verification_failed:W"
    assert res["publishable"] is False
    assert any("verification failed" in w for w in res["warnings"])


def test_lenient_mode_records_but_publishes_if_policy_allows():
    llm = MockLLM()

    class Unchecked(Writer):
        def act(self, task, ctx):
            out = ("## Nonexistent-Only\nbody\n")
            return AgentResult(agent=self.name, output=out, ok=True)

        def checks(self):
            return [has_section("Findings")]  # will fail against act()'s output

    def allow_all(action, ctx):
        return True, "operator override"

    gov = Governor(policies=[("override", allow_all)])
    p = Pipeline([Researcher(name="R", llm=llm), Unchecked(name="W", llm=llm)], governor=gov, strict=False)
    res = p.run("lenient")
    assert res["aborted"] is None
    assert res["publishable"] is True
    assert any("verification failed" in w for w in res["warnings"])
    assert res["decision"]["allow"] is True


def test_stop_on_failure_aborts_on_agent_error():
    class Broken(Researcher):
        def act(self, task, ctx):
            return AgentResult(agent=self.name, output="", ok=False, error="boom")

    p = Pipeline([Broken(name="B", llm=MockLLM()), Writer(name="W", llm=MockLLM())], stop_on_failure=True)
    res = p.run("stop")
    assert res["aborted"] == "agent_failed:B"
    assert res["publishable"] is False
    assert res["output"] is None

    # Without stop_on_failure the same broken agent is skipped and the run continues.
    p2 = Pipeline([Broken(name="B", llm=MockLLM())], stop_on_failure=False)
    res2 = p2.run("stop")
    assert res2["aborted"] is None  # skipped, not aborted

    # And in lenient mode an *agent error* is recorded but does not abort either.
    p3 = Pipeline([Broken(name="B", llm=MockLLM())], strict=False, stop_on_failure=False)
    res3 = p3.run("stop")
    assert res3["aborted"] is None
    assert any("B" in w for w in res3["warnings"])


# --- new in 0.2: reusable pipeline (per-run budget/trace) ---------------------

def test_pipeline_is_reusable_across_runs():
    p = _pipeline(max_calls=10)
    r1 = p.run("first run")
    assert r1["publishable"] is True
    assert r1["budget"]["calls_used"] == 3
    r2 = p.run("second run")
    # Budget must have reset between runs (it did not in 0.1.0 — bug fix).
    assert r2["publishable"] is True
    assert r2["budget"]["calls_used"] == 3
    # And each run's trace contains only its own events.
    assert all("pipeline_start" in e.get("event", "") for e in r2["trace"] if e.get("event") == "pipeline_start")
    assert r2["trace"][0]["event"] == "pipeline_start"
    assert len([e for e in r2["trace"] if e.get("event") == "pipeline_start"]) == 1


# --- new in 0.2: retries + LLMError -------------------------------------------

def test_agent_retries_transient_llm_failure():
    llm = MockLLM(flaky=2)  # first two calls raise, third succeeds
    agent = Researcher(name="R", llm=llm, retries=2)
    res = agent.act("task", Context())
    assert res.ok is True
    assert res.attempts == 3


def test_agent_reports_failure_after_retries():
    llm = MockLLM(flaky=99)
    # Base Agent surfaces exhaustion as ok=False (retries+1 attempts recorded).
    from agentflow.core import Agent as BaseAgent
    a = BaseAgent(name="R", llm=llm, retries=1)
    res = a.act("task", Context())
    assert res.ok is False
    assert res.attempts == 2
    assert "simulated transient failure" in (res.error or "")

    # A custom agent that lets call_llm raise is also handled safely by the
    # pipeline (reported, not a crash).
    class Raising(Agent):
        def act(self, task, ctx):
            self.call_llm(task)  # let it raise

    p = Pipeline([Raising(name="R", llm=MockLLM(flaky=99), retries=1)])
    res = p.run("crash-safe")
    assert res["publishable"] is False
    assert any("R" in w for w in res["warnings"])
    assert res["aborted"] is None  # default: skip and continue


def test_openai_compat_4xx_raises_without_retrying():
    # A 4xx from the API must surface immediately as LLMError, not burn retries.
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "invalid api key"}}')

        def log_message(self, *args):  # keep test output clean
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        llm = OpenAICompatible(api_key="bogus", base_url=f"http://127.0.0.1:{port}/v1", model="gpt", retries=2)
        try:
            llm.complete("system", "user")
            raised: Exception | None = None
        except Exception as e:  # noqa: BLE001
            raised = e
    finally:
        server.shutdown()

    assert raised is not None
    assert isinstance(raised, LLMError), f"expected LLMError, got {type(raised)}"
    assert "401" in str(raised)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
