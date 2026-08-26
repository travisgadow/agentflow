#!/usr/bin/env python3
"""Swarm demo (agentflow 0.3): research a topic in *parallel*, then draft + fact-check.

Runs N researcher agents concurrently via :class:`FanOut`, merges their sourced
findings into one Findings section, then drafts a report and fact-checks it —
the "parallel stages / swarm" workflow from agentflow's roadmap.

Offline & deterministic by default (MockLLM):
    python examples/swarm_research.py "agentic AI governance in 2026"

Tune the swarm size / use a real backend:
    python examples/swarm_research.py --workers 5 "your topic"
    AGENTFLOW_API_KEY=sk-... python examples/swarm_research.py --llm openai "..."
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentflow.core import Governor, FanOut, Pipeline, make_backend  # noqa: E402
from agentflow.agents import FactChecker, Researcher, Writer  # noqa: E402


class AngledResearcher(Researcher):
    """A Researcher that focuses on a single *angle* of the topic."""

    def __init__(self, angle: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.angle = angle

    def act(self, task: str, ctx) -> "object":
        # Prepend the angle so each parallel researcher produces distinct output.
        return super().act(f"{task} (angle: {self.angle})", ctx)


def merge_findings(task: str, ctx, results) -> str:
    """Collect every sourced bullet from the parallel researchers into one section.

    Keeps the ``## Findings`` header and the ``[S#]`` source tags intact so the
    downstream Writer + FactChecker invariants still hold.
    """
    bullets = []
    for r in results:
        if r.ok:
            for line in r.output.splitlines():
                s = line.strip()
                if s.startswith("-"):
                    bullets.append(s)
    if not bullets:
        bullets = ["- (no findings)"]
    return "## Findings\n" + "\n".join(bullets) + "\n"


def build_pipeline(llm, workers: int, angles):
    swarm = [AngledResearcher(name=f"Researcher[{a}]", angle=a, llm=llm) for a in angles]
    fanout = FanOut(name="Researcher", agents=swarm, merge=merge_findings, max_workers=workers)

    def sourced(action, ctx):
        if action != "publish":
            return True, "n/a"
        return bool(ctx.get("all_sourced", False)), "findings not fully sourced"

    gov = Governor(policies=[("sourced", sourced)], max_agent_calls=10)
    return Pipeline(
        agents=[fanout, Writer(name="Writer", llm=llm), FactChecker(name="FactChecker", llm=llm)],
        governor=gov,
        strict=True,
        stop_on_failure=False,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("topic", help="The topic to research in parallel.")
    ap.add_argument("--workers", type=int, default=3, help="Number of parallel researchers (default: 3).")
    ap.add_argument("--llm", default="mock", choices=["mock", "openai"],
                    help="'mock' (default, offline) or 'openai' (any OpenAI-compatible endpoint).")
    ap.add_argument("--json", action="store_true", help="Print the full result object as JSON.")
    args = ap.parse_args()

    workers = max(1, args.workers)
    angles = ["risk", "adoption", "governance", "cost", "safety", "compliance", "tooling", "policy"][:workers]
    llm = make_backend(args.llm)

    pipeline = build_pipeline(llm, workers, angles)
    result = pipeline.run(args.topic)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    findings = [l for l in result["stage_outputs"].get("Researcher", "").splitlines() if l.strip().startswith("-")]
    print("=" * 62)
    print(f"agentflow swarm demo  |  backend: {llm.name}  |  workers: {workers}")
    print("=" * 62)
    print(f"\n  swarm : {workers} parallel researchers -> {len(findings)} merged findings")
    print("\n--- FINAL OUTPUT ---\n")
    print(result["output"])
    print("\n--- GOVERNANCE ---")
    print(f"  publish : {'ALLOWED' if result['decision']['allow'] else 'BLOCKED'}  ({result['decision']['reason']})")
    print(f"  budget  : {result['budget']}")
    if result["warnings"]:
        print(f"  warnings: {result['warnings']}")
    print(f"\n  publishable: {result['publishable']}")
    print(f"  trace     : {result['trace_summary']}")
    print("=" * 62)
    return 0 if result["publishable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
