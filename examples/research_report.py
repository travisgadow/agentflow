#!/usr/bin/env python3
"""End-to-end demo: a governed multi-agent research → draft → fact-check pipeline.

Run offline (default, deterministic):
    python examples/research_report.py "agentic AI governance in 2026"

Run against a real LLM (any OpenAI-compatible endpoint, including Ollama):
    AGENTFLOW_API_KEY=sk-... AGENTFLOW_MODEL=gpt-4o-mini \
        python examples/research_report.py --llm openai "..."

Ollama example (localhost):
    AGENTFLOW_BASE_URL=http://localhost:11434/v1 AGENTFLOW_API_KEY=ollama \
    AGENTFLOW_MODEL=llama3.1 \
        python examples/research_report.py --llm openai "..."

Run modes:
    (default) --strict        verification failure stops the pipeline and blocks publish
    --lenient                 record verification failures as warnings; the
                              Governor's policies alone decide publish
    --stop-on-failure         abort immediately when an agent errors (e.g. LLM outage)

Writes an audit trail to ./agentflow_trace.jsonl next to the CWD.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentflow.core import Governor, Pipeline, Trace, make_backend  # noqa: E402
from agentflow.agents import Researcher, Writer, FactChecker  # noqa: E402


def require_clean_publish(action: str, ctx) -> tuple[bool, str]:
    """Governance policy: only publish if fully verified and no warnings."""
    if action != "publish":
        return True, "n/a"
    if ctx.get("warnings"):
        return False, f"unresolved warnings: {ctx['warnings']}"
    if not ctx.get("all_sourced", True):
        return False, "findings not fully sourced"
    return True, "verified and clean"


def build_pipeline(llm, trace_path: str | None, strict: bool, stop_on_failure: bool) -> Pipeline:
    governor = Governor(
        policies=[("clean_publish", require_clean_publish)],
        max_agent_calls=10,
    )
    trace = Trace(path=trace_path)
    return Pipeline(
        agents=[
            Researcher(name="Researcher", llm=llm),
            Writer(name="Writer", llm=llm),
            FactChecker(name="FactChecker", llm=llm),
        ],
        governor=governor,
        trace=trace,
        strict=strict,
        stop_on_failure=stop_on_failure,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("topic", help="The topic to research.")
    ap.add_argument("--llm", default="mock", choices=["mock", "openai"],
                    help="LLM backend: 'mock' (default, offline) or 'openai' (any OpenAI-compatible endpoint).")
    ap.add_argument("--trace", default=None, help="Path to write the JSONL audit trail (default: ./agentflow_trace.jsonl).")
    ap.add_argument("--json", action="store_true", help="Print the full result object as JSON.")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--lenient", action="store_true",
                       help="Don't stop on verification failure; record warnings and let the Governor decide publish.")
    ap.add_argument("--stop-on-failure", action="store_true",
                    help="Abort the pipeline immediately if an agent errors (e.g. LLM outage).")
    ap.add_argument("--temperature", type=float, default=None,
                    help="Sampling temperature for OpenAI-compatible backends (0.0-2.0).")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Cap on completion tokens for OpenAI-compatible backends.")
    ap.add_argument("--retries", type=int, default=2,
                    help="Extra attempts after a failed LLM call (default: 2).")
    args = ap.parse_args()

    llm = make_backend(args.llm, temperature=args.temperature, max_tokens=args.max_tokens, retries=args.retries)
    trace_path = args.trace or os.path.join(os.getcwd(), "agentflow_trace.jsonl")
    # Start fresh for the demo so the audit file is easy to read.
    if os.path.exists(trace_path):
        os.remove(trace_path)

    pipeline = build_pipeline(llm, trace_path, strict=not args.lenient, stop_on_failure=args.stop_on_failure)
    result = pipeline.run(args.topic)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print("=" * 62)
    print(f"agentflow demo  |  backend: {llm.name}  |  mode: {'lenient' if args.lenient else 'strict'}")
    print("=" * 62)
    print("\n--- FINAL OUTPUT ---\n")
    print(result["output"])
    print("\n--- GOVERNANCE ---")
    print(f"  publish: {'ALLOWED' if result['decision']['allow'] else 'BLOCKED'}")
    print(f"  reason : {result['decision']['reason']}")
    print(f"  budget : {result['budget']}")
    if result["warnings"]:
        print(f"  warnings: {result['warnings']}")
    if result["aborted"]:
        print(f"  aborted: {result['aborted']}")
    print(f"\n  publishable: {result['publishable']}")
    print(f"  audit     : {trace_path}")
    print(f"  trace     : {result['trace_summary']}")
    print("=" * 62)
    return 0 if result["publishable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
