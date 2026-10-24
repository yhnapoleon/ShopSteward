"""Read-only corpus audit, with optional isolated reproducibility rebuilds."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from knowledge_corpus.builder import ROOT, build, json_bytes
from knowledge_corpus.manifest import validate_manifest
from knowledge_corpus.ownership import compare_existing_files, digest
from knowledge_corpus.quality import near_duplicates
from knowledge_corpus.validate import read_jsonl


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): digest(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def verify(path, reproducible=False):
    root = path.resolve().parent.parent
    manifest = json.loads(path.read_text(encoding="utf-8"))
    result = validate_manifest(manifest, root)
    result.update(public_gap=manifest["public_gap"], quota_status=manifest["quota_status"])
    rows = read_jsonl(root / "facts/document-texts.jsonl")
    selected = {d["document_fixture_id"] for d in manifest["documents"]}
    rows = [r for r in rows if r["id"] in selected]
    duplicates = near_duplicates(rows)
    hashes = {}
    for row in manifest["documents"]:
        hashes.setdefault(row["sha256"], []).append(row["version_fixture_id"])
    exact = [ids for ids in hashes.values() if len(ids) > 1]
    result.update(
        exact_duplicate_groups=exact,
        near_duplicate_candidates=duplicates,
        near_duplicate_count=len(duplicates),
        human_review="pending",
        duplicate_scope=(
            "synthetic original business text; revisions excluded from near-duplicate count"
        ),
    )
    if exact:
        result["errors"].append("identical original bytes must not count as independent documents")
    if reproducible:
        external_before = snapshot(root)
        k0 = ROOT.parent / "knowledge"
        k0_before = snapshot(k0)
        fingerprints = []
        for _ in range(2):
            with tempfile.TemporaryDirectory(prefix="knowledge-expanded-repro-") as temporary:
                isolated = Path(temporary).resolve()
                # This fresh temporary root is the context's only deletion target.
                if (root / "public").is_dir():
                    shutil.copytree(root / "public", isolated / "public")
                if (root / "public-sources.jsonl").exists():
                    shutil.copyfile(
                        root / "public-sources.jsonl", isolated / "public-sources.jsonl"
                    )
                build(isolated, manifest["stage"])
                ledger = json.loads((isolated / "ownership.json").read_text(encoding="utf-8"))
                fingerprints.append(ledger["files"])
        same = fingerprints[0] == fingerprints[1]
        matches_checked_manifest = fingerprints[0][f"manifests/{manifest['stage']}.json"] == digest(
            json_bytes(manifest)
        )
        external_changes = compare_existing_files(external_before, snapshot(root))
        external_unchanged = external_changes["unchanged"]
        k0_unchanged = snapshot(k0) == k0_before
        result["reproducibility"] = {
            "two_isolated_builds_identical": same,
            "matches_checked_manifest": matches_checked_manifest,
            "external_files_unchanged": external_unchanged,
            "external_check_scope": (
                "preexisting files; concurrent new acquisitions listed separately"
            ),
            "external_added_files": external_changes["added_files"],
            "external_changed_or_missing_files": external_changes["changed_or_missing_files"],
            "k0_files_unchanged": k0_unchanged,
            "k0_file_count": len(k0_before),
            "k0_sha256": k0_before,
        }
        if not same or not matches_checked_manifest or not external_unchanged or not k0_unchanged:
            result["errors"].append("reproducibility/external preservation check failed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "manifests/pilot.json")
    parser.add_argument("--check-reproducible", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.manifest, args.check_reproducible)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1 if result["errors"] else 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"errors": [str(error)]}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
