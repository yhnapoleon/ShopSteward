"""Export only explicitly paused, dedicated local test databases; never read .env."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "knowledge/src"))

from shopsteward_knowledge.bundle import export_bundle  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-test", action="store_true", required=True)
    parser.add_argument(
        "--writers-paused",
        action="store_true",
        required=True,
        help="attest this task's publisher/upload/ingestion writers are drained/paused",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authority-storage", type=Path, required=True)
    parser.add_argument("--derived-storage", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(
            export_bundle(
                output=args.output,
                authority_url=os.environ.get("KNOWLEDGE_BUNDLE_AUTHORITY_DATABASE_URL", ""),
                derived_url=os.environ.get("KNOWLEDGE_BUNDLE_DERIVED_DATABASE_URL", ""),
                authority_storage=args.authority_storage,
                derived_storage=args.derived_storage,
                repo=REPO,
                writers_paused=args.writers_paused,
            )
        )
        print(json.dumps(result))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print(
            "Export failed; incomplete output retained. No successful backup claimed.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
