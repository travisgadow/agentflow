"""CLI entry point for agentflow.

Usage:
    python -m agentflow serve [--port 8080] [--host 0.0.0.0] [--memory PATH]
    python -m agentflow run "your topic" [--llm mock|openai] [--lenient]
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agentflow",
        description="agentflow — a governed, verifiable, multi-agent pipeline toolkit.",
    )
    sub = parser.add_subparsers(dest="cmd")

    serve_p = sub.add_parser("serve", help="Start the interactive web UI")
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--memory", default="agentflow_memory.json")

    run_p = sub.add_parser("run", help="Run a pipeline from the CLI")
    run_p.add_argument("task", help="Topic or task description")
    run_p.add_argument("--llm", default="mock", choices=["mock", "openai"])
    run_p.add_argument("--lenient", action="store_true")
    run_p.add_argument("--stop-on-failure", action="store_true")
    run_p.add_argument("--model", default="")
    run_p.add_argument("--temperature", type=float, default=None)
    run_p.add_argument("--max-tokens", type=int, default=None)

    args = parser.parse_args()

    if args.cmd == "serve":
        from agentflow.webui import WebUIServer
        server = WebUIServer(host=args.host, port=args.port, memory_path=args.memory)
        server.serve_forever()

    elif args.cmd == "run":
        from agentflow import (
            Governor, Pipeline, Researcher, Writer, FactChecker, make_backend,
        )
        from agentflow.core import LLMError

        kwargs = {}
        if args.llm == "openai":
            kwargs["retries"] = 2
            if args.model:
                kwargs["model"] = args.model
            if args.temperature is not None:
                kwargs["temperature"] = args.temperature
            if args.max_tokens is not None:
                kwargs["max_tokens"] = args.max_tokens

        llm = make_backend(args.llm, **kwargs)
        gov = Governor(max_agent_calls=10)
        agents = [
            Researcher(name="Researcher", llm=llm),
            Writer(name="Writer", llm=llm),
            FactChecker(name="FactChecker", llm=llm),
        ]
        pipeline = Pipeline(
            agents=agents, governor=gov,
            strict=not args.lenient, stop_on_failure=args.stop_on_failure,
        )
        try:
            result = pipeline.run(args.task)
        except LLMError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"\n\033[1mTask:\033[0m    {args.task}")
        status = "\033[32mPublishable\033[0m" if result["publishable"] else "\033[31mBlocked\033[0m"
        print(f"\033[1mStatus:\033[0m  {status}")
        if result.get("warnings"):
            print(f"\033[1mWarnings:\033[0m")
            for w in result["warnings"]:
                print(f"  \033[33m⚠\033[0m {w}")
        if result.get("decision"):
            d = result["decision"]
            print(f"\033[1mGovernor:\033[0m {d['action']} → {'allow' if d['allow'] else 'deny'} ({d['reason']})")
        b = result.get("budget", {})
        print(f"\033[1mBudget:\033[0m   {b.get('calls_used',0)}/{b.get('max_agent_calls','∞')} calls, "
              f"{b.get('tokens_used',0)}/{b.get('max_total_tokens','∞')} tokens")
        print(f"\n\033[1mOutput:\033[0m")
        print(result.get("output", "(no output)"))
        print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
