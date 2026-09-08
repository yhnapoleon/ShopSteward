"""Build only authored expanded fixtures; --verify-only is strictly read-only."""

import argparse
import json

from knowledge_corpus.builder import ROOT, build
from knowledge_corpus.manifest import validate_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["pilot", "full"], default="pilot")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--root", type=type(ROOT), default=ROOT)
    args = parser.parse_args()
    try:
        if args.verify_only:
            path = args.root / "manifests" / f"{args.stage}.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
        else:
            manifest = build(args.root, args.stage)
        result = validate_manifest(manifest, args.root)
        result.update(
            stage=args.stage,
            public_gap=manifest["public_gap"],
            quota_status=manifest["quota_status"],
        )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1 if result["errors"] else 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"errors": [str(error)]}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
