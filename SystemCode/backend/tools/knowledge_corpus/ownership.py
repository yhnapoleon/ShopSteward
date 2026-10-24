"""Compare-and-swap writes under an explicitly owned root; never adopt existing files."""

import hashlib
import os
import tempfile
from pathlib import Path, PureWindowsPath


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compare_existing_files(before, after):
    changed = sorted(path for path, sha in before.items() if after.get(path) != sha)
    return {
        "unchanged": not changed,
        "changed_or_missing_files": changed,
        "added_files": sorted(set(after) - set(before)),
    }


def validate_freeze(previous, proposed):
    """Frozen originals, facts and public snapshots are as immutable as frozen queries."""
    if previous.get("stage") != "full":
        return
    annotation_upgrade = (
        previous.get("evaluation_version") == "expanded-v1"
        and proposed.get("evaluation_version") == "expanded-v1.1"
        and bool(proposed.get("revision_reason"))
    )
    allowed_changes = {"relations.jsonl", "schema.json"} if annotation_upgrade else set()
    csv_repair = (
        previous.get("evaluation_version") == "expanded-v1.1"
        and proposed.get("evaluation_version") == "expanded-v1.2"
        and bool(proposed.get("revision_reason"))
    )
    if csv_repair:
        allowed_changes |= {
            "sources.jsonl",
            "facts/evidence.jsonl",
            "manifests/full.json",
            "manifests/pilot.json",
        }
        allowed_changes |= {
            path
            for path in previous["files"]
            if path.startswith("originals/") and path.endswith(".csv")
        }
    if (
        proposed.get("stage") != "full"
        or any(
            proposed.get("files", {}).get(path) != sha
            for path, sha in previous["files"].items()
            if path not in allowed_changes
        )
        or previous["public_originals"] != proposed["public_originals"]
    ):
        raise ValueError("frozen evaluation changed; create a new evaluation version with a reason")


def safe_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ValueError("path must be relative")
    parts = relative.replace("\\", "/").split("/")
    if any(p in {"..", "", "."} or ":" in p for p in parts):
        raise ValueError("path traversal rejected")
    root = Path(root).resolve()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError("path escapes root")
    return path


def write_owned(root: Path, relative: str, data: bytes, previous_sha256: str | None) -> str:
    path = safe_path(root, relative)
    if path.exists():
        if previous_sha256 is None:
            raise ValueError(f"ownership missing: {relative}")
        if not path.is_file() or digest(path.read_bytes()) != previous_sha256:
            raise ValueError(f"owned file modified: {relative}")
    elif previous_sha256 is not None:
        raise ValueError(f"owned file missing: {relative}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".corpus-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest(data)
