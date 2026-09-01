"""Tests for the agentflow web UI server."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import urllib.request
import urllib.error

from agentflow import __version__
from agentflow.webui import WebUIServer

PORT = 18923
BASE = f"http://127.0.0.1:{PORT}"


def _start_server() -> WebUIServer:
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.write(b'{"version": 1, "records": []}')
    tmp.close()
    server = WebUIServer(host="127.0.0.1", port=PORT, memory_path=tmp.name)
    from http.server import ThreadingHTTPServer
    from agentflow.webui import _Handler
    server._httpd = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    server._httpd.memory_path = tmp.name
    t = threading.Thread(target=server._httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.2)
    return server


def _stop(server: WebUIServer) -> None:
    if server._httpd:
        server._httpd.shutdown()
        server._httpd.server_close()


def _get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def test_health():
    server = _start_server()
    try:
        d = _get("/api/health")
        assert d["status"] == "ok"
        assert d["version"] == __version__
    finally:
        _stop(server)


def test_about():
    server = _start_server()
    try:
        d = _get("/api/about")
        assert d["version"] == __version__
        assert "Researcher" in d["agents"]
        assert "Pipeline" in d["core_modules"]
    finally:
        _stop(server)


def test_run_mock():
    server = _start_server()
    try:
        d = _post("/api/run", {"task": "agentic AI governance", "strict": True})
        assert d["publishable"] is True
        assert d["output"] is not None
        assert len(d["stages"]) == 3
        assert d["budget"]["calls_used"] == 3
        assert d["trace"]
    finally:
        _stop(server)


def test_run_lenient():
    server = _start_server()
    try:
        d = _post("/api/run", {"task": "test topic", "strict": False})
        assert "publishable" in d
        assert "stages" in d
    finally:
        _stop(server)


def test_run_requires_task():
    server = _start_server()
    try:
        try:
            _post("/api/run", {})
            assert False, "should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        _stop(server)


def test_memory_recent_empty():
    server = _start_server()
    try:
        d = _get("/api/memory/recent?limit=5")
        assert isinstance(d, list)
        assert len(d) == 0
    finally:
        _stop(server)


def test_html_served():
    server = _start_server()
    try:
        with urllib.request.urlopen(BASE + "/", timeout=5) as resp:
            html = resp.read().decode()
        assert "<!DOCTYPE html>" in html
        assert "agentflow" in html
        assert "Run Pipeline" in html
    finally:
        _stop(server)
