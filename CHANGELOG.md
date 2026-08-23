# Changelog

All notable changes to `agentflow` are documented here.

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
