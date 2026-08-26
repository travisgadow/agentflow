# agentflow

> **Project #1 — AI agentic workflows portfolio.**
> A governed, verifiable, multi-agent pipeline toolkit in pure Python (stdlib only).

`agentflow` is a small, dependency-free library that encodes the three patterns
dominating agentic AI in mid-2026 and demonstrates them with a working
research → draft → fact-check workflow:

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

It mirrors the "control plane for autonomous agents" idea that enterprise
agentic AI is converging on: the layer that decides *what an agent is allowed
to do*, not just who it is.

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
  test, and deploy.
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

---

## Quick start

**No install needed** (stdlib only) — just run the example:

```bash
# Fully offline & deterministic (default MockLLM):
python examples/research_report.py "agentic AI governance in 2026"
```

**Real LLM** (any OpenAI-compatible endpoint, incl. Ollama/vLLM):

```bash
# OpenAI
AGENTFLOW_API_KEY=sk-... AGENTFLOW_MODEL=gpt-4o-mini \
  python examples/research_report.py --llm openai "your topic"

# Ollama (local)
AGENTFLOW_BASE_URL=http://localhost:11434/v1 AGENTFLOW_API_KEY=ollama \
AGENTFLOW_MODEL=llama3.1 \
  python examples/research_report.py --llm openai "your topic"
```

**Run the tests** (pure-python runner, no pytest required):

```bash
python - <<'PY'
import sys, pathlib, importlib
root = pathlib.Path(".").resolve(); sys.path.insert(0, str(root))
for path in sorted((root / "tests").glob("test_*.py")):
    mod = importlib.import_module(f"tests.{path.stem}")
    for f in [x for x in dir(mod) if x.startswith("test_")]:
        getattr(mod, f)(); print("PASS", f)
PY
```

**Run modes** (strict is the default; see the `--help` for the full list):

```bash
# lenient: record verification failures as warnings, let the Governor decide
python examples/research_report.py --lenient "your topic"

# abort immediately if an agent errors (e.g. LLM outage)
python examples/research_report.py --stop-on-failure "your topic"

# sampling controls for real backends
python examples/research_report.py --llm openai --temperature 0.7 --max-tokens 512 "your topic"
```

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
        # This rubric is what the Pipeline verifies against after act() runs.
        return [has_section("Analysis")]
```

**Memory, parallelism & webhooks (0.3):**

```python
from agentflow import MockLLM, Pipeline, Governor, MemoryStore, FanOut, WebhookNotifier

llm = MockLLM()

# 1) Memory — recall past runs and remember this one.
mem = MemoryStore("agentflow_memory.json")
mem.remember("agentic AI governance", topic="agentic AI", publishable=True)
prior = mem.recall("agentic AI", limit=3)

# 2) Parallel fan-out (swarm) — run independent sub-tasks concurrently, then merge.
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

# 3) Webhook — emit the run on pipeline_end (never crashes the run).
webhook = WebhookNotifier("https://hooks.example.com/agentflow", retries=1, backoff=0.2)

pipeline = Pipeline(
    agents=[fanout, Writer(name="Writer", llm=llm), FactChecker(name="FactChecker", llm=llm)],
    governor=Governor(max_agent_calls=10),
    webhook=webhook,
)
result = pipeline.run("agentic AI governance in 2026")
print(result["webhook"])          # {"ok": True, "status": 200, ...}
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

`Pipeline` takes two run-mode flags that shape what happens when a stage goes
wrong:

```python
Pipeline(agents, governor=gov, strict=True, stop_on_failure=False)
```

- **`strict` (default)** — a *verification failure* stops the pipeline and blocks
  publish. This is the safe default.
- **`strict=False` (lenient)** — verification failures are recorded as warnings
  in the audit trail but do *not* stop the pipeline. Publish is then decided
  solely by your Governor policies (handy for an "operator override" policy).
- **`stop_on_failure=True`** — abort immediately when an agent errors (e.g. LLM
  outage). Default is to skip that stage and continue.

LLM calls are **retryable** end-to-end:

```python
from agentflow import MockLLM, OpenAICompatible
llm = OpenAICompatible(retries=2, backoff=0.5, temperature=0.7, max_tokens=512)
```

Transient failures (network, 5xx) are retried with exponential backoff; a 4xx
(auth, bad request) surfaces immediately as an `LLMError` with the HTTP status
and detail body. `MockLLM(flaky=N)` raises for the first `N` calls — used by the
test-suite to exercise the retry path deterministically.

Banned-content gating is a first-class check:

```python
from agentflow.core.verifier import no_match
no_match(r"\\$\\d+.*\\b(week|day)s\\b")   # veto hard price+date commitments
```

**Emit the run (0.3):** a `Pipeline` can POST a compact run summary to a webhook
on `pipeline_end` — a webhook failure is recorded, never raised:

```python
from agentflow import WebhookNotifier
pipeline = Pipeline(agents, governor=gov,
                    webhook=WebhookNotifier("https://hooks.example.com/hook"))
```

**Parallel sub-tasks (0.3):** wrap independent agents in a `FanOut` "swarm" stage
to run them concurrently and merge their outputs (a `FanOut` is one governed
call):

```python
from agentflow import FanOut
stage = FanOut("Researcher", agents=[a1, a2, a3], max_workers=3)
pipeline = Pipeline([stage, Writer(...), FactChecker(...)], governor=gov)
```

---

## Roadmap (ideas for future agentic-workflow projects)

**Shipped in 0.3:**
- ~~**Memory**~~ — a `MemoryStore` that lets agents recall past runs and refine. ✅
- ~~**Parallel stages**~~ — `FanOut` runs a "swarm" of agents concurrently and merges. ✅
- ~~**Webhooks**~~ — `WebhookNotifier` emits the run on `pipeline_end`. ✅

**Still open:**
- **MCP bridge**: an `OpenAICompatible`-like wrapper that speaks MCP over HTTP
  for cross-agent tool use.
- **Streaming fan-out**: incremental `merge` as sub-agents complete (back-pressure,
  early-stop once enough sub-tasks have succeeded).
- **Token-budgeted fan-out**: count each sub-agent call against the Governor
  budget independently (a `FanOut` is currently one governed stage call).

---

## Repo layout

```
agentflow/
├── agentflow/
│   ├── __init__.py
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
│   └── test_v03.py
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
