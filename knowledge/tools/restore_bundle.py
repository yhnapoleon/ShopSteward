"""Verify offline, or restore a trusted bundle into new empty local test targets."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "knowledge/src"))

from shopsteward_knowledge.bundle import restore_bundle, verify_bundle  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--target-test", action="store_true", required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--storage-target", type=Path)
    parser.add_argument("--index-prefix")
    args = parser.parse_args()
    try:
        result = verify_bundle(args.bundle)
        if not args.verify_only:
            if not args.storage_target or not args.index_prefix:
                raise ValueError("actual restore requires --storage-target and --index-prefix")
            result = asyncio.run(
                restore_bundle(
                    root=args.bundle,
                    storage_target=args.storage_target,
                    authority_url=os.environ.get("KNOWLEDGE_RESTORE_AUTHORITY_DATABASE_URL", ""),
                    derived_url=os.environ.get("KNOWLEDGE_RESTORE_DERIVED_DATABASE_URL", ""),
                    repo=REPO,
                    opensearch_url=os.environ.get("KNOWLEDGE_RESTORE_OPENSEARCH_URL", ""),
                    index_prefix=args.index_prefix,
                )
            )
        print(json.dumps(result))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print(
            "Restore failed; partial targets retained for inspection. Use new empty targets.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
