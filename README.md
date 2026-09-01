# agentflow

> **Project #1 — AI agentic workflows portfolio.**
> A governed, verifiable, multi-agent pipeline toolkit in pure Python (stdlib only).

`agentflow` is a small, dependency-free library that encodes the patterns
dominating agentic AI in mid-2026:

1. **Multi-agent orchestration** — a `Pipeline` threads a shared `Context`
   through a sequence of agents, each building on the previous output, with
   retryable LLM calls and strict/lenient run modes.
2. **Verifiability-by-design** — every agent can ship its own rubric of checks;
   the pipeline verifies each stage's output against it before moving on.
3. **A Governor (control-plane)** — a policy + budget layer that can veto a
   final `publish` action based on the context, and logs an audit trail.
4. **Memory, parallelism & events (0.3)** — a `MemoryStore` to recall past
   runs, a `FanOut` "swarm" stage for parallel sub-tasks, and a `WebhookNotifier`
   that emits the run on `pipeline_end`.
5. **Interactive web UI (0.4)** — a polished, browser-based single-page app
   for running pipelines, inspecting results, and managing memory. Zero
   dependencies, one `python -m agentflow serve` and you're in.

It mirrors the "control plane for autonomous agents" idea that enterprise
agentic AI is converging on: the layer that decides *what an agent is allowed
to do*, not just who it is.

---

## Quick start

**No install needed** (stdlib only):

```bash
# Fully offline & deterministic (default MockLLM):
python examples/research_report.py "agentic AI governance in 2026"

# Interactive web UI:
python -m agentflow serve --port 8080
# → open http://127.0.0.1:8080 in your browser

# CLI run:
python -m agentflow run "agentic AI governance in 2026"
```

**Install as a package** (optional):

```bash
pip install .
agentflow serve          # web UI
agentflow run "topic"    # CLI
```

---

## Web UI (0.4)

`agentflow serve` starts a **zero-dependency, stdlib-only HTTP server** with an
embedded single-page application:

- **Run Pipeline** — enter a task, pick the LLM backend (mock or any
  OpenAI-compatible endpoint), configure temperature / max-tokens / retries,
  toggle strict/lenient and stop-on-failure. The full result is rendered in
  the browser:
  - ✅/❌ **Publishable** badge + abort reason
  - **Stage-by-stage** verification (pass/fail per check)
  - **Output** report (the final markdown)
  - **Warnings** list
  - **Governor** decision (action + reason)
  - **Budget** (calls used, tokens used)
  - **Trace** timeline (all audit events, scrollable)
- **Memory** — recall recent records (optionally filtered by query) and
  clear the store.
- **About** — version, agents, core modules, architecture diagram.

JSON API endpoints (for scripting / integration):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Status + version |
| GET | `/api/about` | Version, agents, modules |
| POST | `/api/run` | Run a pipeline, get full result JSON |
| GET | `/api/memory/recent?limit=N&query=Q` | List recent memory records |
| POST | `/api/memory/clear` | Clear all memory |

```bash
# Start the server:
python -m agentflow serve --port 8080

# Or programmatically:
from agentflow import WebUIServer
server = WebUIServer(host="0.0.0.0", port=8080, memory_path="my_mem.json")
server.serve_forever()
```

---

## Why this design

The most useful insight from 2026's agentic-AI trend reports (Firecrawl,
Anthropic, Google ATLAS, etc.) is **Karpathy's verifiability principle**:
*AI automates fastest in domains where the output can be verified.* `agentflow`
is built around that — rather than trusting a model's prose, each agent declares
**how to verify its own output**, and a `Governor` enforces it before anything
is published.

- **CLI/terminal agents** are the dominant 2026 workflow: fast, composable,
  atomic feedback loops. `agentflow` is a CLI-first library you can pipe,
  test, and deploy — now with an interactive web UI on top.
- **MCP resurgence** matters for integration, but `agentflow` deliberately keeps
  a tiny surface (a `complete()` method) so it can wrap *any* backend —
  OpenAI, Ollama, vLLM, or an offline mock.

---

## Architecture

```
                +----------------------------------------------+
  task  ─────►  │  PIPELINE  (orchestrator)                    │
                │                                              │
                │   Governor ──► budget?  policy?  audit       │
                │      │                                        │
                ▼      ▼                                        ▼
        [ Researcher ] ─► [ Writer ] ─► [ FactChecker ] ─► publish?
             │              │              │
             └──────────────┴──────────────┘
                        shared Context (blackboard)
                        + per-stage Verifier
                        + Trace (audit log, JSONL)
```

### Core primitives (`agentflow/core`)

| Module       | What it does |
|--------------|--------------|
| `context.py` | `Context` — a shared blackboard threaded through every stage. |
| `llm.py`     | `LLMBackend` interface + `MockLLM` (offline) + `OpenAICompatible` (any OpenAI-style endpoint, stdlib). |
| `agent.py`   | `Agent` base + `AgentResult`. Subclass `act()` for custom behavior. |
| `verifier.py`| `Verifier` + reusable check factories (`has_section`, `min_length`, `max_length`, `matches`, `no_match`, `all_bullets_sourced`). |
| `governor.py`| `Governor` — budgets (`max_agent_calls`, `max_total_tokens`) + `publish` policy gates + audit. |
| `trace.py`   | `Trace` — append-only event log, in-memory + optional JSONL. |
| `pipeline.py`| `Pipeline` — runs agents, applies verification + governance, returns a full report. |
| `memory.py`  | `MemoryStore` — persistent remember/recall memory for agents. |
| `fanout.py`  | `FanOut` — run a set of agents concurrently and merge (a "swarm" stage). |
| `webhook.py` | `WebhookNotifier` — POST the run to a webhook (stdlib, never crashes the run). |

### Example agents (`agentflow/agents`)

- **`Researcher`** — topic → sourced findings (each carries a `[S#]` tag).
- **`Writer`** — findings → a structured report (Summary / Key Findings / Sources).
- **`FactChecker`** — verifies *every finding is sourced* and appends a `Verification` section.

### Web UI (`agentflow/webui.py`)

- **`WebUIServer`** — a `ThreadingHTTPServer` serving an embedded single-page
  app (dark theme, no external CSS/JS). Endpoints for running pipelines,
  managing memory, and health checks.

---

## Using it as a library

```python
from agentflow import (
    MockLLM, Governor, Pipeline,
    Researcher, Writer, FactChecker,
)

llm = MockLLM()  # or make_backend("openai")

def only_verified(action, ctx):
    if action == "publish" and not ctx.get("all_sourced", False):
        return False, "unsourced findings"
    return True, "ok"

pipeline = Pipeline(
    agents=[
        Researcher(name="Researcher", llm=llm),
        Writer(name="Writer", llm=llm),
        FactChecker(name="FactChecker", llm=llm),
    ],
    governor=Governor(policies=[("verified", only_verified)], max_agent_calls=10),
)

result = pipeline.run("agentic AI governance in 2026")
print(result["output"])          # final markdown report
print(result["publishable"])     # True/False after governance
print(result["decision"])        # {"action": "publish", "allow": ..., "reason": ...}
print(result["trace_summary"])   # event counts for the audit trail
```

**Writing your own agent:**

```python
from agentflow.core import Agent, AgentResult
from agentflow.core.verifier import has_section

class MyAgent(Agent):
    role = "analyzer"

    def act(self, task, ctx):
        text = self.llm.complete(self.system(), task)
        ctx.set("analyzed_by", self.name)
        return AgentResult(agent=self.name, output=text, ok=True)

    def checks(self):
        return [has_section("Analysis")]
```

**Memory, parallelism & webhooks (0.3):**

```python
from agentflow import MockLLM, Pipeline, Governor, MemoryStore, FanOut, WebhookNotifier

llm = MockLLM()

mem = MemoryStore("agentflow_memory.json")
mem.remember("agentic AI governance", topic="agentic AI", publishable=True)
prior = mem.recall("agentic AI", limit=3)

from agentflow.core import Agent, AgentResult
class AngleAgent(Agent):
    def __init__(self, name, angle):
        super().__init__(name)
        self.angle = angle
    def act(self, task, ctx):
        out, _ = self.call_llm(f"List findings on {self.angle} of: {task}")
        return AgentResult(agent=self.name, output=f"- {out} [S1]", ok=True)

fanout = FanOut(
    "Researcher",
    agents=[AngleAgent(f"R{i}", a) for i, a in enumerate(["risk", "adoption", "governance"])],
    max_workers=3,
)

webhook = WebhookNotifier("https://hooks.example.com/agentflow", retries=1, backoff=0.2)

pipeline = Pipeline(
    agents=[fanout, Writer(name="Writer", llm=llm), FactChecker(name="FactChecker", llm=llm)],
    governor=Governor(max_agent_calls=10),
    webhook=webhook,
)
result = pipeline.run("agentic AI governance in 2026")
```

**Web UI (0.4):**

```python
from agentflow import WebUIServer

server = WebUIServer(host="127.0.0.1", port=8080, memory_path="agentflow_memory.json")
server.serve_forever()  # blocks; open http://127.0.0.1:8080
```

---

## Design notes

- **Zero runtime dependencies.** Everything is Python stdlib. The only
  optional dependency is `pytest` for the test-suite convenience.
- **Deterministic by default.** `MockLLM` makes the *workflow* (orchestration,
  verification, governance, audit) fully reproducible in CI and demos — the
  actual LLM is swappable via env vars.
- **Verification is explicit, not implicit.** An agent that can't be checked is
  one that should be gated. The `Verifier` makes that check first-class.
- **Audit-first.** Every decision is logged to a `Trace`, so you can reconstruct
  *why* a run was published or blocked.

---

## Run modes & controls

```python
Pipeline(agents, governor=gov, strict=True, stop_on_failure=False)
```

- **`strict` (default)** — a *verification failure* stops the pipeline and blocks
  publish.
- **`strict=False` (lenient)** — verification failures are recorded as warnings
  in the audit trail but do *not* stop the pipeline.
- **`stop_on_failure=True`** — abort immediately when an agent errors.

LLM calls are **retryable** end-to-end:

```python
from agentflow import OpenAICompatible
llm = OpenAICompatible(retries=2, backoff=0.5, temperature=0.7, max_tokens=512)
```

---

## Roadmap

**Shipped:**
- ~~**Memory**~~ — `MemoryStore` for recall/remember. ✅ (0.3)
- ~~**Parallel stages**~~ — `FanOut` swarm stage. ✅ (0.3)
- ~~**Webhooks**~~ — `WebhookNotifier` on `pipeline_end`. ✅ (0.3)
- ~~**Interactive web UI**~~ — `WebUIServer` single-page app. ✅ (0.4)

**Still open:**
- **MCP bridge**: an `OpenAICompatible`-like wrapper that speaks MCP over HTTP
  for cross-agent tool use.
- **Streaming fan-out**: incremental `merge` as sub-agents complete.
- **Token-budgeted fan-out**: count each sub-agent call against the Governor
  budget independently.
- **WebSocket trace streaming**: live trace events in the web UI as the pipeline
  runs (currently the full result is returned on completion).

---

## Repo layout

```
agentflow/
├── agentflow/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point (serve / run)
│   ├── webui.py             # Interactive web UI server (0.4)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── researcher.py
│   │   ├── writer.py
│   │   └── factchecker.py
│   └── core/
│       ├── __init__.py
│       ├── agent.py
│       ├── context.py
│       ├── governor.py
│       ├── llm.py
│       ├── memory.py
│       ├── fanout.py
│       ├── webhook.py
│       ├── pipeline.py
│       ├── trace.py
│       └── verifier.py
├── examples/
│   ├── research_report.py
│   └── swarm_research.py
├── tests/
│   ├── test_pipeline.py
│   ├── test_v03.py
│   └── test_webui.py        # Web UI tests (0.4)
├── CHANGELOG.md
├── LICENSE
├── README.md
├── pyproject.toml
├── requirements.txt
└── .gitignore
```

---

## License

MIT — see [LICENSE](LICENSE).
