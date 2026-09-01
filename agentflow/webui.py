"""Interactive web UI for agentflow.

A zero-dependency, stdlib-only HTTP server providing a polished single-page
application for running agentflow pipelines, inspecting results, managing
memory, and browsing the audit trail.

Start with:
    python -m agentflow serve [--port 8080]

Or programmatically:
    from agentflow.webui import WebUIServer
    server = WebUIServer(host="127.0.0.1", port=8080)
    server.serve_forever()
"""
from __future__ import annotations

import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional

from . import __version__
from .core import (
    Agent, AgentResult, Context, Governor, LLMError, MockLLM,
    OpenAICompatible, make_backend, Pipeline, MemoryStore,
)
from .agents import Researcher, Writer, FactChecker

# ── HTML template (embedded) ───────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>agentflow — AI Agentic Workflows</title>
<style>
:root {
  --bg: #0a0e1a;
  --surface: #111827;
  --surface2: #1e293b;
  --border: #293548;
  --text: #e5e7eb;
  --muted: #9ca3af;
  --dim: #6b7280;
  --accent: #3b82f6;
  --accent2: #06b6d4;
  --ok: #10b981;
  --err: #ef4444;
  --warn: #f59e0b;
  --radius: 10px;
  --mono: "SF Mono","Fira Code","Cascadia Code",Consolas,monospace;
  --sans: -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.6;min-height:100vh}
a{color:var(--accent);text-decoration:none}
.app{display:grid;grid-template-columns:240px 1fr;grid-template-rows:56px 1fr;height:100vh}
header{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;padding:0 24px;background:var(--surface);border-bottom:1px solid var(--border);z-index:10}
.logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px}
.logo .dot{width:10px;height:10px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok)}
.logo .ver{font-size:12px;color:var(--dim);font-weight:400;margin-left:4px}
nav{display:flex;flex-direction:column;gap:2px;padding:20px 12px;background:var(--surface);border-right:1px solid var(--border)}
nav button{background:none;border:none;color:var(--muted);padding:10px 14px;border-radius:var(--radius);cursor:pointer;font-size:14px;text-align:left;font-family:var(--sans);display:flex;align-items:center;gap:10px;transition:all .15s}
nav button:hover{color:var(--text);background:var(--surface2)}
nav button.active{color:var(--accent);background:var(--surface2);font-weight:600}
main{overflow-y:auto;padding:28px 32px}
.panel{display:none}
.panel.active{display:block}
h2{font-size:20px;font-weight:700;margin-bottom:20px;display:flex;align-items:center;gap:10px}
h3{font-size:15px;font-weight:600;margin:20px 0 10px;color:var(--muted)}
.form-group{margin-bottom:18px}
label{display:block;font-size:13px;font-weight:600;color:var(--muted);margin-bottom:6px}
input[type=text],input[type=number],input[type=url],textarea,select{
  width:100%;padding:10px 14px;background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--radius);color:var(--text);font-size:14px;font-family:var(--sans);
  transition:border-color .15s;outline:none
}
input:focus,textarea:focus,select:focus{border-color:var(--accent)}
textarea{min-height:80px;resize:vertical}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:18px}
.toggle-row{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:18px}
.toggle{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted);cursor:pointer}
.toggle input{width:18px;height:18px;accent-color:var(--accent)}
.btn{display:inline-flex;align-items:center;gap:8px;padding:11px 24px;border:none;border-radius:var(--radius);
  font-size:14px;font-weight:600;cursor:pointer;font-family:var(--sans);transition:all .15s}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:#2563eb}
.btn-primary:disabled{opacity:.5;cursor:not-allowed}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
.btn-ghost:hover{color:var(--text);border-color:var(--dim)}
.btn-sm{padding:7px 14px;font-size:12px}
.result-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:18px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}
.badge-ok{background:rgba(16,185,129,.15);color:var(--ok)}
.badge-err{background:rgba(239,68,68,.15);color:var(--err)}
.badge-warn{background:rgba(245,158,11,.15);color:var(--warn)}
.result-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px}
.budget-bar{display:flex;gap:16px;font-size:12px;color:var(--dim)}
.output-box{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px;font-size:14px;line-height:1.7;white-space:pre-wrap;word-break:break-word;
  max-height:400px;overflow-y:auto;font-family:var(--sans)}
.stage-list{display:flex;flex-direction:column;gap:8px}
.stage{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--surface2);border-radius:var(--radius);font-size:13px}
.stage .icon{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0}
.stage .icon.ok{background:rgba(16,185,129,.2);color:var(--ok)}
.stage .icon.fail{background:rgba(239,68,68,.2);color:var(--err)}
.stage .name{font-weight:600;min-width:100px}
.stage .checks{color:var(--dim);font-size:11px;margin-left:auto}
.warning-list{list-style:none;padding:0}
.warning-list li{padding:8px 12px;margin-bottom:6px;background:rgba(245,158,11,.08);border-left:3px solid var(--warn);border-radius:4px;font-size:13px}
.trace-list{max-height:300px;overflow-y:auto;font-family:var(--mono);font-size:12px}
.trace-item{display:flex;gap:10px;padding:4px 8px;border-bottom:1px solid var(--border);align-items:baseline}
.trace-item:last-child{border-bottom:none}
.trace-item .t{color:var(--dim);min-width:70px;font-size:11px}
.trace-item .ev{color:var(--accent2);min-width:120px;font-weight:600}
.trace-item .det{color:var(--muted);word-break:break-all}
.mem-item{padding:12px 14px;background:var(--surface2);border-radius:var(--radius);margin-bottom:8px;font-size:13px}
.mem-item .meta{font-size:11px;color:var(--dim);margin-top:4px}
.about-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-top:12px}
.about-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px}
.about-card .label{font-size:12px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
.about-card .val{font-size:18px;font-weight:700}
.spinner{width:20px;height:20px;border:3px solid var(--border);border-top-color:var(--accent);
  border-radius:50%;animation:spin .6s linear infinite;display:inline-block}
@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:768px){
  .app{grid-template-columns:1fr;grid-template-rows:56px auto 1fr}
  nav{flex-direction:row;padding:8px;border-right:none;border-bottom:1px solid var(--border);overflow-x:auto}
  nav button{white-space:nowrap;padding:8px 12px}
  main{padding:18px 16px}
}
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="logo"><span class="dot"></span>agentflow<span class="ver" id="ver">v0.4.0</span></div>
    <div id="status" style="font-size:12px;color:var(--dim)">idle</div>
  </header>
  <nav>
    <button class="active" data-tab="run">&#9654; Run Pipeline</button>
    <button data-tab="memory">&#128203; Memory</button>
    <button data-tab="about">&#9432; About</button>
  </nav>
  <main>
    <div class="panel active" id="panel-run">
      <h2>&#9654; Run Pipeline</h2>
      <div class="form-group">
        <label>Task / Topic</label>
        <textarea id="task" placeholder="e.g. agentic AI governance in 2026">agentic AI governance in 2026</textarea>
      </div>
      <div class="row">
        <div class="form-group"><label>LLM Backend</label>
          <select id="backend">
            <option value="mock" selected>Mock (offline)</option>
            <option value="openai">OpenAI-compatible</option>
          </select>
        </div>
        <div class="form-group"><label>Model</label><input type="text" id="model" placeholder="gpt-4o-mini" value=""></div>
      </div>
      <div class="row">
        <div class="form-group"><label>Temperature</label><input type="number" id="temperature" value="0.7" step="0.1" min="0" max="2"></div>
        <div class="form-group"><label>Max Tokens</label><input type="number" id="max_tokens" value="2048" step="128" min="1" max="128000"></div>
        <div class="form-group"><label>Retries</label><input type="number" id="retries" value="2" min="0" max="10"></div>
      </div>
      <div class="toggle-row">
        <label class="toggle"><input type="checkbox" id="strict" checked> Strict mode</label>
        <label class="toggle"><input type="checkbox" id="stop_on_failure"> Stop on failure</label>
      </div>
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:28px">
        <button class="btn btn-primary" id="btn-run" onclick="runPipeline()"><span id="run-label">&#9654; Run Pipeline</span></button>
        <span id="run-status" style="font-size:13px;color:var(--dim)"></span>
      </div>
      <div id="results"></div>
    </div>
    <div class="panel" id="panel-memory">
      <h2>&#128203; Memory</h2>
      <div class="form-group"><label>Search query (blank = all)</label><input type="text" id="mem-query" placeholder="e.g. agentic AI"></div>
      <div style="margin-bottom:18px;display:flex;gap:10px">
        <button class="btn btn-ghost btn-sm" onclick="recallMem()">&#128269; Recall</button>
        <button class="btn btn-ghost btn-sm" onclick="clearMem()">&#10006; Clear All</button>
      </div>
      <div id="mem-results"></div>
    </div>
    <div class="panel" id="panel-about">
      <h2>&#9432; About agentflow</h2>
      <p style="color:var(--muted);font-size:14px;max-width:640px;margin-bottom:24px">
        A governed, verifiable, multi-agent pipeline toolkit in pure Python (stdlib only).
        Built around <strong>verifiability-by-design</strong>: each agent ships its own rubric,
        a Governor enforces budgets and publish gates, and every decision is audit-logged.
      </p>
      <div class="about-grid" id="about-grid"></div>
      <h3 style="margin-top:28px">Architecture</h3>
      <pre style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px;font-family:var(--mono);font-size:12px;overflow-x:auto;color:var(--muted)">
  task ──►  PIPELINE (orchestrator)
              Governor ──► budget?  policy?  audit
                 │
        [ Researcher ] ─► [ Writer ] ─► [ FactChecker ] ─► publish?
             │              │              │
             └──────────────┴──────────────┘
                    shared Context (blackboard)
                    + per-stage Verifier
                    + Trace (audit log, JSONL)</pre>
    </div>
  </main>
</div>
<script>
document.querySelectorAll("nav button").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".panel").forEach(p=>p.classList.remove("active"));
    document.getElementById("panel-"+btn.dataset.tab).classList.add("active");
    if(btn.dataset.tab==="about") loadAbout();
  });
});
function $(id){return document.getElementById(id)}
function esc(s){const d=document.createElement("div");d.textContent=s;return d.innerHTML}
async function api(path,opts={}){
  const r=await fetch(path,{headers:{"Content-Type":"application/json"},...opts});
  if(!r.ok)throw new Error((await r.json()).error||r.statusText);
  return r.json();
}
async function runPipeline(){
  const task=$("task").value.trim();
  if(!task){$("run-status").textContent="Enter a task first";return}
  const body={task,strict:$("strict").checked,stop_on_failure:$("stop_on_failure").checked};
  if($("backend").value==="openai"){
    Object.assign(body,{backend:"openai",model:$("model").value.trim()||"gpt-4o-mini",
      temperature:parseFloat($("temperature").value)||0.7,
      max_tokens:parseInt($("max_tokens").value)||2048,
      retries:parseInt($("retries").value)||2});
  }
  const btn=$("btn-run"),label=$("run-label"),status=$("run-status");
  btn.disabled=true;label.innerHTML='<span class="spinner"></span> Running…';status.textContent="";
  $("results").innerHTML="";
  const t0=performance.now();
  try{
    const data=await api("/api/run",{method:"POST",body:JSON.stringify(body)});
    status.textContent="Completed in "+((performance.now()-t0)/1000).toFixed(2)+"s";
    renderResults(data);
  }catch(e){status.textContent="Error: "+e.message;status.style.color="var(--err)"}
  finally{btn.disabled=false;label.innerHTML="&#9654; Run Pipeline"}
}
function renderResults(d){
  const el=$("results");
  const badge=d.publishable
    ?'<span class="badge badge-ok">&#10003; Publishable</span>'
    :'<span class="badge badge-err">&#10007; Blocked</span>';
  const b=d.budget||{};
  let html=`<div class="result-card"><div class="result-header">${badge}${d.aborted?`<span class="badge badge-warn">${esc(d.aborted)}</span>`:""}
    <div class="budget-bar"><span>${b.calls_used||0}/${b.max_agent_calls||"∞"} calls</span><span>${b.tokens_used||0}/${b.max_total_tokens||"∞"} tokens</span></div></div>`;
  if(d.stages&&d.stages.length){
    html+=`<h3>Stages</h3><div class="stage-list">`;
    d.stages.forEach(s=>{
      const icon=s.verified?'<span class="icon ok">&#10003;</span>':'<span class="icon fail">&#10007;</span>';
      const checks=(s.checks||[]).map(c=>c.name+(c.passed?" ✓":" ✗")).join("  ");
      html+=`<div class="stage">${icon}<span class="name">${esc(s.name)}</span><span class="checks">${checks}</span></div>`;
    });
    html+=`</div>`;
  }
  if(d.output){html+=`<h3>Output</h3><div class="output-box">${esc(d.output)}</div>`}
  if(d.warnings&&d.warnings.length){
    html+=`<h3>Warnings</h3><ul class="warning-list">`;
    d.warnings.forEach(w=>html+=`<li>${esc(w)}</li>`);
    html+=`</ul>`;
  }
  if(d.decision){
    const cls=d.decision.allow?"badge-ok":"badge-err";
    html+=`<h3>Governor</h3><div style="display:flex;align-items:center;gap:10px">
      <span class="badge ${cls}">${esc(d.decision.action)}</span>
      <span style="font-size:13px;color:var(--muted)">${esc(d.decision.reason)}</span></div>`;
  }
  if(d.trace&&d.trace.length){
    html+=`<h3>Trace <span style="font-size:12px;color:var(--dim);font-weight:400">(${d.trace.length} events)</span></h3><div class="trace-list">`;
    d.trace.forEach(t=>{
      const det=Object.entries(t).filter(([k])=>k!=="event"&&k!=="ts").map(([k,v])=>k+"="+JSON.stringify(v)).join(" ");
      html+=`<div class="trace-item"><span class="t">${t.ts?t.ts.toFixed(2)+"s":""}</span><span class="ev">${esc(t.event||"")}</span><span class="det">${esc(det)}</span></div>`;
    });
    html+=`</div>`;
  }
  html+=`</div>`;
  el.innerHTML=html;
}
async function recallMem(){
  const q=$("mem-query").value.trim();
  const el=$("mem-results");
  el.innerHTML='<div class="spinner" style="margin:12px 0"></div>';
  try{
    const data=await api("/api/memory/recent?limit=50"+(q?"&query="+encodeURIComponent(q):""));
    if(!data.length){el.innerHTML='<p style="color:var(--dim);margin:12px 0">No records found.</p>';return}
    el.innerHTML=data.map(r=>{
      const text=r.text||r.topic||r.title||r.task||JSON.stringify(r);
      const ts=r.ts?new Date(r.ts*1000).toLocaleString():"";
      return `<div class="mem-item"><div>${esc(text)}</div><div class="meta">${ts}</div></div>`;
    }).join("");
  }catch(e){el.innerHTML=`<p style="color:var(--err)">${esc(e.message)}</p>`}
}
async function clearMem(){
  if(!confirm("Clear all memory records?"))return;
  try{await api("/api/memory/clear",{method:"POST"});recallMem()}
  catch(e){alert(e.message)}
}
async function loadAbout(){
  try{
    const d=await api("/api/about");
    const items=[["Version",d.version],["Agents",d.agents.join(", ")],
      ["Core Modules",d.core_modules.join(", ")],["Runtime Deps","None (stdlib only)"],
      ["Python",">= 3.10"],["License","MIT"]];
    $("about-grid").innerHTML=items.map(([l,v])=>
      `<div class="about-card"><div class="label">${l}</div><div class="val">${esc(String(v))}</div></div>`).join("");
  }catch(e){}
}
</script>
</body></html>"""


# ── Handler ──────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    """Serves the embedded HTML + JSON API for the agentflow web UI."""

    server: "WebUIServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self) -> None:
        body = _HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in ("/", "/index.html"):
            self._send_html()
            return
        if path == "/api/health":
            self._send_json({"status": "ok", "version": __version__})
            return
        if path == "/api/about":
            self._send_json({
                "version": __version__,
                "agents": ["Researcher", "Writer", "FactChecker"],
                "core_modules": ["Pipeline", "Governor", "Verifier", "Context",
                                 "Agent", "MemoryStore", "FanOut", "WebhookNotifier"],
            })
            return
        if path == "/api/memory/recent":
            self._handle_memory_recent()
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/api/run":
            self._handle_run()
            return
        if path == "/api/memory/clear":
            self._handle_memory_clear()
            return
        self._send_json({"error": "not found"}, 404)

    def _handle_run(self) -> None:
        try:
            body = self._read_json()
            task = body.get("task", "").strip()
            if not task:
                self._send_json({"error": "task is required"}, 400)
                return
            strict = body.get("strict", True)
            stop_on_failure = body.get("stop_on_failure", False)
            backend = body.get("backend", "mock")

            llm_kwargs: Dict[str, Any] = {}
            if backend in ("openai", "openai-compat", "ollama", "vllm", "remote"):
                llm_kwargs["retries"] = body.get("retries", 2)
                if body.get("model"):
                    llm_kwargs["model"] = body["model"]
                if body.get("temperature") is not None:
                    llm_kwargs["temperature"] = body["temperature"]
                if body.get("max_tokens") is not None:
                    llm_kwargs["max_tokens"] = body["max_tokens"]
                llm = make_backend("openai", **llm_kwargs)
            else:
                llm = MockLLM()

            governor = Governor(max_agent_calls=10)
            agents = [
                Researcher(name="Researcher", llm=llm),
                Writer(name="Writer", llm=llm),
                FactChecker(name="FactChecker", llm=llm),
            ]
            pipeline = Pipeline(
                agents=agents, governor=governor,
                strict=strict, stop_on_failure=stop_on_failure,
            )
            import time
            t0 = time.time()
            result = pipeline.run(task)
            elapsed = round(time.time() - t0, 3)

            stages = []
            for name in ("Researcher", "Writer", "FactChecker"):
                v = result.get("stage_outputs", {}).get(f"{name}_verdict", {})
                stages.append({
                    "name": name,
                    "verified": v.get("verified", False) if v else None,
                    "checks": v.get("checks", []) if v else [],
                })

            self._send_json({
                "output": result.get("output"),
                "publishable": result.get("publishable"),
                "aborted": result.get("aborted"),
                "warnings": result.get("warnings", []),
                "decision": result.get("decision"),
                "budget": result.get("budget"),
                "trace": result.get("trace", []),
                "trace_summary": result.get("trace_summary"),
                "stages": stages,
                "elapsed": elapsed,
            })
        except LLMError as e:
            self._send_json({"error": f"LLM error: {e}"}, 502)
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _handle_memory_recent(self) -> None:
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        params: Dict[str, str] = {}
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
        limit = min(int(params.get("limit", "50")), 200)
        query = params.get("query", "").strip() or None
        mem = MemoryStore(self.server.memory_path)
        self._send_json(mem.recall(query, limit=limit))

    def _handle_memory_clear(self) -> None:
        MemoryStore(self.server.memory_path).clear()
        self._send_json({"ok": True, "cleared": True})


# ── Server ───────────────────────────────────────────────────────────────
class WebUIServer:
    """Threading HTTP server for the agentflow web UI.

    Args:
        host: bind address (default 127.0.0.1).
        port: port (default 8080).
        memory_path: path to the MemoryStore JSON file.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        memory_path: str = "agentflow_memory.json",
    ) -> None:
        self.host = host
        self.port = port
        self.memory_path = memory_path
        self._httpd: Optional[HTTPServer] = None

    def serve_forever(self) -> None:
        from http.server import ThreadingHTTPServer
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._httpd.memory_path = self.memory_path
        url = f"http://{self.host}:{self.port}"
        print(f"\n  \033[36magentflow\033[0m v{__version__} — interactive web UI")
        print(f"  \033[2m→ {url}\033[0m")
        print(f"  \033[2mPress Ctrl+C to stop.\033[0m\n")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Shutting down.")
            self._httpd.server_close()

    def serve_once(self, timeout: float = 5.0) -> None:
        from http.server import ThreadingHTTPServer
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._httpd.memory_path = self.memory_path
        self._httpd.timeout = timeout
        self._httpd.handle_request()
        self._httpd.server_close()


__all__ = ["WebUIServer"]
