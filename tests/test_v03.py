"""Tests for agentflow 0.3: memory, parallel fan-out (swarm), and webhooks.

All offline/deterministic. Webhook tests use a tiny in-process HTTP server (no
external network). The parallel test uses short sleeps to prove concurrency.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentflow import (  # noqa: E402
    Agent, AgentResult, Context, FanOut, MemoryStore, MockLLM, Pipeline,
    WebhookNotifier,
)


def _tmpfile(suffix=".json") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    os.remove(path)  # start absent
    return path


def _start_server(handler):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, server.server_address[1]


# --- MemoryStore -----------------------------------------------------------

def test_memorystore_persistence():
    path = _tmpfile()
    try:
        mem = MemoryStore(path)
        mem.remember("hello world", topic="t1")
        mem.remember({"text": "second record"})
        reloaded = MemoryStore(path)  # reload from disk
        assert reloaded.count() == 2
        assert reloaded.recall("hello", limit=5)[0]["text"] == "hello world"
        assert any(r.get("text") == "second record" for r in reloaded.recall(limit=10))
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_memorystore_recall_query_and_limit():
    mem = MemoryStore()  # in-memory only
    mem.remember("alpha beta gamma")
    mem.remember("beta delta")
    mem.remember("completely different")
    hits = mem.recall("beta", limit=10)
    assert len(hits) == 2
    assert hits[0]["text"] == "beta delta"  # newest first
    assert mem.recall("alpha beta", limit=5)[0]["text"] == "alpha beta gamma"
    assert len(mem.recall("beta", limit=1)) == 1


def test_memorystore_upsert_forget_clear():
    mem = MemoryStore()
    mem.remember("v1", key="k")
    mem.remember("v2", key="k")  # upsert
    assert mem.get("k")["text"] == "v2"
    assert mem.count() == 1
    mem.remember("other", key="z")
    assert mem.count() == 2
    assert mem.forget("k") is True
    assert mem.get("k") is None
    assert mem.count() == 1
    mem.clear()
    assert mem.count() == 0


# --- FanOut (parallel swarm) ------------------------------------------------

class _SlowAgent(Agent):
    def __init__(self, name, delay: float = 0.0) -> None:
        super().__init__(name)
        self.delay = delay

    def act(self, task: str, ctx: Context) -> AgentResult:
        if self.delay:
            time.sleep(self.delay)
        return AgentResult(agent=self.name, output=f"- done by {self.name} [S1]", ok=True)


def test_fanout_runs_in_parallel_and_merges():
    agents = [_SlowAgent(f"A{i}", delay=0.3) for i in range(3)]
    fo = FanOut("Swarm", agents, max_workers=3)
    started = time.time()
    res = fo.act("task", Context())
    elapsed = time.time() - started
    assert res.ok is True
    assert "A0" in res.output and "A2" in res.output
    assert res.meta["succeeded"] == 3 and res.meta["failed"] == 0
    # 3 x 0.3s sequential ~= 0.9s; parallel must be well under that.
    assert elapsed < 0.8, f"fan-out did not run in parallel (elapsed={elapsed:.2f}s)"


def test_fanout_partial_failure_is_recorded():
    class Broken(Agent):
        def act(self, task, ctx):
            return AgentResult(agent=self.name, output="", ok=False, error="boom")

    agents = [_SlowAgent("ok"), Broken("bad")]
    res = FanOut("Swarm", agents, max_workers=2).act("t", Context())
    assert res.ok is True  # at least one succeeded
    assert res.meta["succeeded"] == 1 and res.meta["failed"] == 1
    assert "did not complete" in res.output
    assert "bad" in res.output


def test_fanout_all_fail_is_reported():
    class Broken(Agent):
        def act(self, task, ctx):
            return AgentResult(agent=self.name, output="", ok=False, error="boom")

    res = FanOut("Swarm", [Broken("b1"), Broken("b2")]).act("t", Context())
    assert res.ok is False
    assert res.meta["failed"] == 2


def test_fanout_in_pipeline_publishable():
    from agentflow import FactChecker, Governor, Writer

    class Sourced(Agent):
        def __init__(self, name, note):
            super().__init__(name)
            self.note = note

        def act(self, task, ctx):
            return AgentResult(agent=self.name, output=f"- finding about {self.note} [S1]", ok=True)

    def merge(task, ctx, results):
        bullets = [l.strip() for r in results if r.ok
                   for l in r.output.splitlines() if l.strip().startswith("-")]
        return "## Findings\n" + "\n".join(bullets) + "\n"

    fo = FanOut("Researcher", [Sourced(f"R{i}", f"angle{i}") for i in range(3)], merge=merge)
    gov = Governor(policies=[], max_agent_calls=10)
    p = Pipeline([fo, Writer(name="Writer", llm=MockLLM()), FactChecker(name="FactChecker", llm=MockLLM())], governor=gov)
    res = p.run("swarm topic")
    assert res["publishable"] is True
    assert res["stage_outputs"]["Researcher"].count("- ") >= 3


# --- Webhooks --------------------------------------------------------------

def test_webhook_notifier_posts_payload():
    from http.server import BaseHTTPRequestHandler

    captured: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            captured["body"] = json.loads(self.rfile.read(n))
            captured["content_type"] = self.headers.get("Content-Type")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *a):
            pass

    server, port = _start_server(Handler)
    try:
        nh = WebhookNotifier(f"http://127.0.0.1:{port}/hook")
        status = nh.emit({"task": "hello", "publishable": True})
        assert status["ok"] is True
        assert status["status"] == 200
        assert captured["content_type"] == "application/json"
        assert captured["body"]["task"] == "hello"
        assert nh.last is not None
    finally:
        server.shutdown()


def test_webhook_failure_does_not_raise():
    # Point at a closed port: emit must return ok=False, not raise.
    nh = WebhookNotifier("http://127.0.0.1:1/hook", timeout=2, retries=0)
    status = nh.emit({"x": 1})
    assert status["ok"] is False
    assert nh.last["ok"] is False
    assert len(nh.errors) == 1


def test_pipeline_webhook_integration():
    from http.server import BaseHTTPRequestHandler
    from agentflow import FactChecker, Governor, Researcher, Writer

    captured: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            captured["body"] = json.loads(self.rfile.read(n))
            self.send_response(202)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    server, port = _start_server(Handler)
    try:
        gov = Governor(policies=[], max_agent_calls=10)
        nh = WebhookNotifier(f"http://127.0.0.1:{port}/hook")
        p = Pipeline([
            Researcher(name="R", llm=MockLLM()),
            Writer(name="W", llm=MockLLM()),
            FactChecker(name="FC", llm=MockLLM()),
        ], governor=gov, webhook=nh)
        res = p.run("webhook topic")
        assert res["webhook"]["ok"] is True
        assert captured["body"]["task"] == "webhook topic"
        assert "publishable" in captured["body"]
    finally:
        server.shutdown()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
