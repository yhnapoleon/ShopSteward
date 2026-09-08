"""Ingestion whitelist and actual-byte inventory. Questions/facts never enter this projection."""

import csv
import io
from collections import Counter
from pathlib import Path

from .ownership import digest, safe_path

FIELDS = (
    "document_fixture_id",
    "version_fixture_id",
    "original_path",
    "mime",
    "size",
    "sha256",
    "source_family_id",
    "scenario_family_id",
    "metadata",
    "synthetic",
)
GOLD = {
    "gold",
    "expected_answer",
    "expected_path",
    "required_evidence",
    "forbidden_claims",
    "query",
    "cases",
    "facts",
}


def normalize_public(raw):
    """Normalize the independently acquired source rows, preserving raw provenance elsewhere."""
    from .validate import validate_source

    row = validate_source(raw)
    if row["acquisition_status"] != "acquired":
        return row
    if row.get("synthetic", False):
        raise ValueError("public source must not be synthetic")
    metadata = dict(row.get("metadata") or {})
    provenance = {
        key: row.get(key)
        for key in ("source_kind", "source_family_id", "publisher", "jurisdiction")
    }
    provenance.update(
        scenario_family_id=None, synthetic=False, source_url=row.get("source_url") or row.get("url")
    )
    metadata.update(
        title=row["title"],
        category="public",
        store_fixture=None,
        sku_fixture_ids=[],
        supplier_fixture_ids=[],
        entity_refs=[],
        valid_from=None,
        valid_until=None,
        provenance=provenance,
        source_url=provenance["source_url"],
        source_original_path=row["original_path"],
        source_original_sha256=row["content_sha256"],
        acquisition_batch=row.get("acquisition_batch"),
        use_terms_status=row["use_terms_status"],
        attribution=row.get("attribution"),
        license_url=row.get("license_url"),
    )
    # Source agent licenses text companions for indexing separately from PDF images/logos.
    normalized = bool(row.get("normalized_path"))
    return {
        "document_fixture_id": row["document_fixture_id"],
        "version_fixture_id": row["version_fixture_id"],
        "original_path": row["normalized_path"] if normalized else row["original_path"],
        "mime": row["normalized_mime"] if normalized else row["mime"],
        "size": row["normalized_size_bytes"]
        if normalized
        else row.get("size", row.get("size_bytes")),
        "sha256": row["normalized_sha256"] if normalized else row["content_sha256"],
        "source_family_id": row["source_family_id"],
        "scenario_family_id": None,
        "synthetic": False,
        "metadata": metadata,
    }


def reject_gold(value):
    if isinstance(value, dict):
        if GOLD.intersection(value):
            raise ValueError("gold/facts/query forbidden in ingestion")
        for v in value.values():
            reject_gold(v)
    elif isinstance(value, list):
        for v in value:
            reject_gold(v)


def logical_count(rows: list[dict]) -> int:
    return len({r["document_fixture_id"] for r in rows})


def counts(rows):
    return {
        "logical_document_count": logical_count(rows),
        "version_count": len(rows),
        "source_family_count": len({r["source_family_id"] for r in rows}),
        "chunk_count": None,
    }


def build_manifest(records: list[dict], root: Path) -> dict:
    documents = []
    for record in records:
        if record.get("acquisition_status") == "reference_only":
            continue
        reject_gold(record)
        item = {k: record[k] for k in FIELDS}
        safe_path(root, item["original_path"])
        if item["original_path"].replace("\\", "/").split("/")[0] not in {"originals", "public"}:
            raise ValueError("ingest path must be under originals/ or public/")
        documents.append(item)
    return {"schema_version": "expanded-v1", "documents": documents, "counts": counts(documents)}


def validate_manifest(manifest: dict, root: Path) -> dict:
    errors = []
    rows = manifest.get("documents", [])
    seen = set()
    versions = {}
    for n, row in enumerate(rows):
        try:
            reject_gold(row)
            if any(k not in row for k in FIELDS):
                raise ValueError("required document fields missing")
            if row["original_path"].replace("\\", "/").split("/")[0] not in {"originals", "public"}:
                raise ValueError("invalid original path")
            path = safe_path(root, row["original_path"])
            data = path.read_bytes()
            if digest(data) != row["sha256"]:
                errors.append(f"documents[{n}]: sha256 mismatch")
            if len(data) != row["size"] or not data:
                errors.append(f"documents[{n}]: size mismatch/empty original")
            if row["synthetic"] and path.suffix.lower() == ".csv":
                table = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
                if (
                    len(table) < 3
                    or table[0] != ["section", "heading", "text"]
                    or any(len(cells) != 3 for cells in table)
                    or table[1][0] != "metadata"
                ):
                    errors.append(f"documents[{n}]: invalid synthetic CSV header/row shape")
            metadata = row["metadata"]
            if metadata.get("source_original_path"):
                archive = safe_path(root, metadata["source_original_path"]).read_bytes()
                if digest(archive) != metadata.get("source_original_sha256"):
                    errors.append(f"documents[{n}]: source original sha256 mismatch")
            key = row["version_fixture_id"]
            if key in seen:
                errors.append(f"documents[{n}]: duplicate version ID")
            seen.add(key)
            versions.setdefault(row["document_fixture_id"], []).append(row)
        except (ValueError, OSError, KeyError, TypeError, csv.Error) as error:
            errors.append(f"documents[{n}]: {type(error).__name__}: {error}")
    actual = counts(rows)
    if manifest.get("counts") != actual:
        errors.append("manifest counts disagree with actual records")
    unique = {r["document_fixture_id"]: r for r in rows}.values()
    return {
        **actual,
        "errors": errors,
        "category_counts": dict(Counter(r["metadata"].get("category", "public") for r in unique)),
        "format_counts": dict(Counter(Path(r["original_path"]).suffix for r in rows)),
        "total_bytes": sum(r["size"] for r in rows),
        "synthetic_logical_count": logical_count([r for r in rows if r["synthetic"]]),
        "public_logical_count": logical_count([r for r in rows if not r["synthetic"]]),
    }
