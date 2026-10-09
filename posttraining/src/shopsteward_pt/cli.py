"""Validate, freeze, evaluate and rescore replenishment task policies."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from shopsteward_pt.eval.validation import validate_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser(
        "validate", help="Validate episode specifications and export cases"
    )
    validate.add_argument("--config", required=True, type=Path)
    validate.add_argument("--output-dir", type=Path)
    freeze = commands.add_parser(
        "freeze", help="Freeze model-visible contexts from real test fixtures"
    )
    freeze.add_argument("--config", required=True, type=Path)
    freeze.add_argument("--limit", type=int)
    evaluate = commands.add_parser("evaluate", help="Run a baseline and save raw evidence")
    evaluate.add_argument("--config", required=True, type=Path)
    evaluate.add_argument("--run-dir", required=True, type=Path)
    evaluate.add_argument("--policies", nargs="+", default=["B0", "B1"])
    evaluate.add_argument("--mode", choices=["decision", "execution"], required=True)
    evaluate.add_argument("--suite", choices=["core", "challenge"])
    evaluate.add_argument("--limit", type=int)
    evaluate.add_argument("--resume", action="store_true")
    for name in ("rescore", "report"):
        sub = commands.add_parser(name, help="Rebuild scores and reports from saved raw records")
        sub.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            report = validate_config(args.config, output_dir=args.output_dir)
        else:
            from shopsteward_pt.eval import commands as implementation

            if args.command == "freeze":
                report = asyncio.run(implementation.freeze(args.config, args.limit))
            elif args.command == "evaluate":
                report = asyncio.run(
                    implementation.evaluate(
                        args.config,
                        args.run_dir,
                        args.policies,
                        args.mode,
                        args.suite,
                        args.limit,
                        args.resume,
                    )
                )
            else:
                report = implementation.rescore(args.run_dir)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        label = "validation" if args.command == "validate" else args.command
        print(f"{label} failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
