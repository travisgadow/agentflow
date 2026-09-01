# Changelog

All notable changes to `agentflow` are documented here.

## [0.4.1] — 2026-08-31

**Web UI revamp** — full visual redesign of the embedded single-page app
(glass/aurora dark theme, left-rail nav, animated
Researcher → Writer → FactChecker → Governor pipeline visualization with
per-stage verified/failed states, verdict banner, budget stat cards, safe
mini-markdown output rendering, semantic trace timeline, toasts,
⌘/Ctrl+Enter to run, responsive + reduced-motion support). Zero dependencies
preserved (system fonts, no CDN). JSON API unchanged.

### Fixed

- Stage checks now render the real `check` name and `detail`
  (the old UI read a nonexistent `name` field and showed `undefined`).
- Trace timeline shows relative offsets (`+0.03s`) instead of raw
  unix seconds; governor/pipeline-end events colored by decision
  (publish = cyan, veto/blocked = red).
- `tests/test_webui.py` wording assertion relaxed to case-insensitive.

### Housekeeping

- `server.log` added to `.gitignore`.

## [0.4.0] — 2026-08-31

**Interactive web UI** — a zero-dependency, stdlib-only single-page application
for running agentflow pipelines, inspecting results, and managing memory
from the browser.

### New

- **`WebUIServer`** (`agentflow/webui.py`) — a `ThreadingHTTPServer` that
  serves an embedded single-page app with a modern dark theme. No external
  CSS/JS/frameworks — everything is inline in one HTML string.
  - **Run Pipeline** — enter a task, pick LLM backend (mock or any
    OpenAI-compatible endpoint), set temperature / max-tokens / retries,
    toggle strict/lenient and stop-on-failure. The full result is rendered:
    publishable badge, stage-by-stage verification, output report, warnings,
    governor decision, budget, and a scrollable trace timeline.
  - **Memory** — recall recent records (optionally filtered by query) and
    clear the store, all from the browser.
  - **About** — version, agents, core modules, and the architecture diagram.
  - JSON API endpoints: `GET /api/health`, `GET /api/about`,
    `POST /api/run`, `GET /api/memory/recent`, `POST /api/memory/clear`.
- **`python -m agentflow serve`** — start the web UI from the CLI.
  Options: `--port`, `--host`, `--memory`.
- **`python -m agentflow run "topic"`** — run a pipeline from the CLI
  with `--llm`, `--lenient`, `--stop-on-failure`, `--model`,
  `--temperature`, `--max-tokens`.
- **`agentflow` console script** (via `[project.scripts]` in pyproject.toml)
  maps to the same CLI, so `pip install . && agentflow serve` works.
- **`WebUIServer`** added to the public API (`from agentflow import WebUIServer`).

### Packaging

- Version bumped to **0.4.0**.
- `pyproject.toml` gains the `[project.scripts]` entry point.
- `agentflow/__init__.py` exports `WebUIServer`.

### Tests

- **`tests/test_webui.py`** — 7 new tests: health endpoint, about endpoint,
  mock pipeline run (publishable + 3 stages + budget), lenient run,
  missing-task validation (400), empty memory listing, and HTML page serving.

## [0.3.0] — 2026-08-25

Three new capabilities, all stdlib-only and offline-testable, drawn from the
roadmap: **memory**, **parallel fan-out (swarm)**, and **webhooks**.

### Memory

- **New `MemoryStore`** (`agentflow/core/memory.py`) — a small, persistent
  (JSON-file) memory so agents / your code can `remember` a record and later
  `recall` it.
  - `remember(record|str|dict, key=..., **fields)` — append, or upsert when `key` is given.
  - `recall(query=None, limit=10)` — newest-first; optional substring/token search over a record's `text`/`topic`/`title`/`task` fields (no embeddings, no ML).
  - `get(key)`, `recent(limit)`, `forget(key)`, `clear()`, `count()`, `len()`.
  - Thread-safe, human-readable on disk, zero dependencies.
- `examples/research_report.py` gains `--memory PATH`: recalls a prior run for the topic, then remembers this one.

### Parallel fan-out (swarm)

- **New `FanOut`** (`agentflow/core/fanout.py`) — run a set of agents
  **concurrently** (stdlib `concurrent.futures`) and merge their outputs into a
  single stage result. Duck-typed like an `Agent` (`.name`, `.act`, `.checks()`),
  so a `Pipeline` uses it exactly like any other stage.
  - `merge(task, ctx, results)` — pluggable combiner; `default_merge` sections each sub-output and notes any that failed.
  - `max_workers` to cap concurrency (defaults to `min(8, len(agents))`).
  - Per-sub-agent success/failure is captured in `result.meta` (`succeeded`,
    `failed`, `errors`, `elapsed`); partial failure is transparent, not silent.
  - Budget note: a `FanOut` counts as **one** governed stage call.
- **New `examples/swarm_research.py`** — research a topic across N parallel
  researchers, merge their sourced findings, then draft + fact-check.

### Webhooks

- **New `WebhookNotifier`** (`agentflow/core/webhook.py`) — a stdlib HTTP
  POSTer (JSON) with optional retries/backoff. `emit(payload) -> dict` returns a
  status dict and **never raises** (a webhook must not break a run).
- **`Pipeline(..., webhook=...)`** — the pipeline fires the webhook once on
  `pipeline_end` with a compact run summary (`task`, `publishable`, `decision`,
  `budget`, `warnings`, `trace_summary`). The outcome is exposed as
  `result["webhook"]` and logged to the `Trace` (`event="webhook"`). A webhook
  failure is recorded, never raised.

### Packaging / CI

- Exports added to the public API: `MemoryStore`, `FanOut`, `WebhookNotifier`.
- `examples/research_report.py` gains `--webhook URL` (fires on `pipeline_end`).
- CI now auto-discovers **all** `tests/test_*.py` modules and runs the new
  offline demos (`research_report.py` and `swarm_research.py`).
- Tests: 16 → **25** (memory persistence/recall/upsert; fan-out parallelism +
  partial/total failure + full pipeline; webhook POST + failure + pipeline
  integration).

## [0.2.0] — 2026-08-23

### Bug fixes

- **`Pipeline` is now safe to re-use.** `Governor.reset()` is called at the start of
  every `Pipeline.run()`, so the per-run budget counters (`calls_used`, `tokens_used`)
  and the `audit` log no longer leak between runs. The trace returned in each result
  is scoped to that run only.
- **`OpenAICompatible` now retries transient failures** (network errors, 5xx) with
  exponential backoff and stops immediately on 4xx (auth, bad request). Previously a
  single transient blip would abort the whole pipeline with no error detail.
- **New `LLMError` exception** wraps all backend failures with a clear message
  (HTTP status, detail body, endpoint), so downstream error handling is uniform.
- **`Agent.call_llm()`** is the single retry-aware entry point for LLM calls.
  `Agent.act()` and the bundled agents (`Researcher`, `Writer`) now route through
  it, so a transient failure in *any* stage is retried before being reported.
- **`Pipeline` catches exceptions from `Agent.act()`** and converts them to
  `AgentResult(ok=False)` — a crashing agent no longer takes down the whole run.
- **`MockLLM(flaky=N)`** helper lets tests exercise the retry path deterministically.
- **Dead code removed** from `FactChecker._findings_bullets()` (an unused `bullets`
  list that was computed but never used).
- **`make_backend()`** silently drops kwargs that a given backend doesn't accept
  (e.g. `temperature` passed to `MockLLM`), so one call site can configure all
  backends uniformly without `TypeError`.

### New controls

- **`Pipeline(strict=..., stop_on_failure=...)`** — two new run modes:
  - `strict` (default, `True`): a verification failure stops the pipeline and blocks
    publish. This matches 0.1.x behavior.
  - `strict=False` (**lenient**): verification failures are recorded as warnings in
    the audit trail but do not stop the pipeline. Publish is decided solely by your
    Governor policies. Useful when you want a "best-effort" run with an operator
    override.
  - `stop_on_failure=True`: abort the pipeline immediately when an agent returns
    `ok=False` (e.g. LLM outage). Default `False` (skip that stage and continue).

- **`OpenAICompatible(temperature=..., max_tokens=..., retries=..., backoff=...)`** —
  sampling controls forwarded to the API, plus explicit retry/backoff configuration.
  `temperature` and `max_tokens` are only sent when set, so Ollama/vLLM endpoints
  that don't support them are unaffected.

- **`Agent(retries=..., delay=...)`** — per-agent retry count and inter-attempt delay.
  Subclasses overriding `act()` should call `self.call_llm(...)` to inherit retries.

- **`Governor.reset()`** — public method to clear per-run state. Called automatically
  by `Pipeline.run()`; exposed for tests and custom orchestrators.

- **New verifier checks** (`agentflow.core.verifier`):
  - `matches(pattern)` — pass if the output matches a regex (case-insensitive by default).
  - `no_match(pattern)` — pass if the output does **not** match a regex. Useful for
    vetoing banned content (e.g. hard price+date commitments in outbound copy).
  - `max_length(n)` — pass if the output is at most `n` characters.

- **`Trace.summary_of(events)`** — static helper to summarize any event list, used
  internally to produce per-run trace summaries.

### Example CLI

`examples/research_report.py` now exposes:

```
--lenient               Don't stop on verification failure; let the Governor decide.
--stop-on-failure       Abort immediately if an agent errors.
--temperature 0.7       Sampling temperature (OpenAI-compatible backends).
--max-tokens 512        Completion token cap (OpenAI-compatible backends).
--retries 2             Extra attempts after a failed LLM call.
```

### Tests

Grew from 6 to **15** tests. New coverage:

- strict vs. lenient mode behavior (abort vs. publish-with-warning)
- `stop_on_failure` abort vs. skip-and-continue
- retry: transient failure then success (attempts == 3)
- retry: failure after all retries (ok=False, error recorded)
- `4xx` from the API raises `LLMError` immediately (no retry burn)
- `Pipeline` re-use: budget resets between runs, trace is scoped per run
- `matches` / `no_match` / `max_length` checks
- a crashing agent (raises from `act`) is reported safely by the pipeline

## [0.1.0] — 2026-08-22

Initial release: governed, verifiable, multi-agent pipeline toolkit.

- `Pipeline`, `Context`, `Agent`, `AgentResult`
- `Governor` (budgets + publish policy gates + audit)
- `Verifier` + reusable checks (`has_section`, `min_length`, `all_bullets_sourced`)
- `Trace` (in-memory + optional JSONL audit log)
- `MockLLM` (offline/deterministic) + `OpenAICompatible` (any OpenAI-style endpoint)
- Example workflow: `Researcher` → `Writer` → `FactChecker`
- CI on Python 3.10–3.13, 6 tests, demo script
