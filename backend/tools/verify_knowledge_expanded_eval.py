"""Validate frozen evaluation or score a separately obtained retrieval result file."""

import argparse
import json
from pathlib import Path

from knowledge_corpus.builder import ROOT
from knowledge_corpus.evaluation import evaluate
from knowledge_corpus.quality import verify_evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--results", type=Path)
    args = parser.parse_args()
    try:
        result = verify_evaluation(args.root)
        if args.results and not result["errors"]:
            result["retrieval_evaluation"] = evaluate(args.results, args.root / "cases.jsonl")
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1 if result["errors"] else 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"errors": [str(error)]}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
