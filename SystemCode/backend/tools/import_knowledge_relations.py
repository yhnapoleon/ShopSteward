"""Bind authored synthetic relations to parser evidence; import only into isolated tests."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shopsteward_knowledge.api import RelationBatch
from shopsteward_knowledge.contracts import EvidenceLocator, OriginalRef, SearchResponse
from shopsteward_knowledge.parsing import parse_original
from shopsteward_knowledge.parsing.chunking import chunk_blocks

from tools.import_knowledge_corpus import prepare_upload

PREDICATES = {"SUPPLIES", "HAS_APPLICABLE_DOCUMENT", "SUPERSEDES"}


def bind_quote(record, root, mapping, version_id, quote, profile="lexical-v1"):
    """Whitespace-only normalization tolerates PDF line wraps, never changes wording."""
    prepared = prepare_upload(record, root, mapping)
    if not prepared["metadata"]["provenance"].get("synthetic"):
        raise ValueError("only authored synthetic evidence is supported by this importer")
    ref = OriginalRef(
        version_id=version_id,
        sha256=prepared["content_sha256"],
        mime=record["mime"],
        storage_key=record["original_path"],
        size_bytes=prepared["path"].stat().st_size,
    )
    parsed = parse_original(ref, prepared["path"].read_bytes())
    if parsed.status not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("source is not searchable")
    normalized = "".join(quote.split())
    if not normalized:
        raise ValueError("empty evidence quote")
    matches = [
        c
        for c in chunk_blocks(parsed.blocks, {"id": profile})
        if normalized in "".join(c["text"].split()) and not c.get("truncated")
    ]
    # One complete source occurrence is needed; ambiguous duplicates require review.
    if len(matches) != 1:
        raise ValueError("quote must match exactly one complete parser chunk")
    return matches


def validate_authored_edge(row, edge):
    if (
        row.get("assertion_status") != "synthetic_verified"
        or row.get("assertion_scope") != "synthetic_fact_only_not_real_business_verification"
    ):
        raise ValueError("relation is not an authored synthetic assertion")
    conditions = row.get("machine_conditions")
    if (
        row.get("condition_semantics") != "all_equal_required_keys_fail_closed"
        or not isinstance(conditions, dict)
        or not conditions
        or edge.get("conditions") != conditions
        or any(type(edge["conditions"][k]) is not type(v) for k, v in conditions.items())
        or any(type(v) not in {str, int, bool, float} for v in conditions.values())
    ):
        raise ValueError("explicit scalar conditions must be preserved")
    if (
        edge.get("source_version_fixture_id") != row.get("source_version_id")
        or edge.get("predicate") not in PREDICATES
    ):
        raise ValueError("unsupported source or retrieval predicate")
    if edge.get("evidence_quote") != row.get("evidence_quote"):
        raise ValueError("retrieval evidence quote differs from the authored assertion")
    if row.get("relation_type") == "APPLIES_TO":
        expected = (row.get("to_entity"), "HAS_APPLICABLE_DOCUMENT", row.get("from_entity"))
    elif row.get("relation_type") in {"SUPPLIES", "SUPERSEDES"}:
        expected = (row.get("from_entity"), row["relation_type"], row.get("to_entity"))
    else:
        raise ValueError("unsupported parent assertion")
    if (
        not row.get("relation_id")
        or edge.get("semantic_relation_id") != row["relation_id"]
        or (edge.get("subject"), edge.get("predicate"), edge.get("object")) != expected
    ):
        raise ValueError("retrieval endpoints differ from the parent assertion")


def verify_candidate(candidate, chunk, identity):
    if (
        any(getattr(candidate, k) != v for k, v in identity.items())
        or not candidate.synthetic
        or candidate.truncated
        or candidate.chunk_id != chunk["chunk_id"]
        or candidate.text != chunk["text"]
        or candidate.content_sha256 != chunk["content_sha256"]
        or candidate.locator != EvidenceLocator.model_validate(chunk["locator"])
    ):
        raise ValueError("remote evidence differs from the source parser binding")


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result


def endpoint(value, role):
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port != {"backend": 8018, "knowledge": 8020}[role]
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("isolated loopback test API on 8018/8020 required")
    return value.rstrip("/")


def mapped_entity(value, mapping, receipts):
    for group in ("skus", "suppliers"):
        if value in mapping[group]:
            return mapping[group][value]
    if value in receipts.get("versions", {}):
        return receipts["versions"][value]["version_id"]
    raise ValueError("relation endpoint has no actual entity/version mapping")


async def import_edge(backend, service, row, edge, record, root, mapping, receipts):
    validate_authored_edge(row, edge)
    saved = receipts["versions"][row["source_version_id"]]
    prepared = prepare_upload(record, root, mapping)
    if saved["source_sha256"] != prepared["content_sha256"]:
        raise ValueError("upload receipt source hash differs")
    doc_id, version_id = saved["document_id"], saved["version_id"]
    publication = saved["publication_receipt"]
    generation = publication["generation_id"]
    response = await backend.get(f"/api/v1/documents/{doc_id}")
    response.raise_for_status()
    doc = response.json()
    revision = doc["evidence_revision"]
    matches = [
        p
        for p in doc.get("publications", [])
        if p["version_id"] == version_id
        and p["generation_id"] == generation
        and p["metadata_revision"] == revision
        and p["manifest_hash"] == publication["manifest_hash"]
    ]
    if (
        doc["id"] != doc_id
        or doc["status"] != "active"
        or doc["store_id"] != prepared["store_id"]
        or not matches
    ):
        raise ValueError("source publication is no longer authorized")
    # Use an existing publication interval inside the authored relation/source interval.
    interval = row["effective_interval"]
    starts = [
        instant(v) for v in (interval.get("from"), prepared["metadata"].get("valid_from")) if v
    ]
    ends = [
        instant(v) for v in (interval.get("until"), prepared["metadata"].get("valid_until")) if v
    ]
    start, end = max(starts) if starts else None, min(ends) if ends else None
    if start and end and end <= start:
        raise ValueError("relation interval does not intersect its source")
    as_of = None
    for pub in matches:
        lower = [v for v in (start, instant(pub["valid_from"]) if pub["valid_from"] else None) if v]
        upper = [v for v in (end, instant(pub["valid_until"]) if pub["valid_until"] else None) if v]
        point = (
            max(lower)
            if lower
            else (min(upper) - timedelta(microseconds=1) if upper else datetime.now(UTC))
        )
        if not upper or point < min(upper):
            as_of = point
            break
    if as_of is None:
        raise ValueError("no published interval for this relation")
    # Chunk IDs use the worker profile and real uploaded version ID.
    profile = saved["index_profile_id"]
    chunks = bind_quote(record, root, mapping, version_id, edge["evidence_quote"], profile)
    scope = dict(
        principal_ref="precloud-relation-import",
        store_id=doc["store_id"],
        as_of=as_of.isoformat(),
        expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        allowed_versions=[
            dict(version_id=version_id, generation_id=generation, metadata_revision=revision)
        ],
    )
    response = await service.post(
        "/internal/v1/evidence", json={"scope": scope, "chunk_ids": [c["chunk_id"] for c in chunks]}
    )
    response.raise_for_status()
    evidence = SearchResponse.model_validate(response.json())
    if evidence.degraded or len(evidence.candidates) != len(chunks):
        raise ValueError("remote evidence unavailable")
    identity = dict(
        document_id=doc_id,
        version_id=version_id,
        generation_id=generation,
        metadata_revision=revision,
        store_id=doc["store_id"],
        original_sha256=prepared["content_sha256"],
    )
    for chunk, candidate in zip(chunks, evidence.candidates, strict=True):
        verify_candidate(candidate, chunk, identity)
    batch = RelationBatch.model_validate(
        dict(
            generation_id=generation,
            metadata_revision=revision,
            edges=[
                dict(
                    subject=mapped_entity(edge["subject"], mapping, receipts),
                    object=mapped_entity(edge["object"], mapping, receipts),
                    predicate=edge["predicate"],
                    confirmed=True,
                    conditions=edge["conditions"],
                    evidence_chunk_ids=[c["chunk_id"] for c in chunks],
                    valid_from=start,
                    valid_until=end,
                )
            ],
        )
    )
    # The service rechecks READY and current projection inside its own transaction.
    response = await service.post("/internal/v1/relations", json=batch.model_dump(mode="json"))
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-test", action="store_true", required=True)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8018")
    parser.add_argument("--service-url", default="http://127.0.0.1:8020")
    args = parser.parse_args()
    root = args.manifest.resolve().parent.parent
    manifest = json.loads(args.manifest.read_text("utf-8"))
    records = {r["version_fixture_id"]: r for r in manifest["documents"]}
    mapping = json.loads(args.mapping.read_text("utf-8"))
    rows = [json.loads(line) for line in (root / "relations.jsonl").read_text("utf-8").splitlines()]
    selected = [r for r in rows if r["source_version_id"] in records]
    result = dict(
        mode="offline_quote_binding" if args.dry_run else "real_http_relation_import",
        manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        selected_relations=len(selected),
        bound=0,
        imported=0,
        failures=[],
        business_permission_granted=False,
        receipts=[],
    )

    async def run():
        receipts = json.loads(args.receipts.read_text("utf-8")) if args.receipts else {}
        backend_url = endpoint(args.backend_url, "backend")
        service_url = endpoint(args.service_url, "knowledge")
        if not args.dry_run:
            if (
                not mapping.get("seeded")
                or mapping.get("target_database") != "shopsteward_test"
                or receipts.get("target_url", "").rstrip("/") != backend_url
            ):
                raise ValueError("seeded test mapping and receipts for this API required")
            token, key = (
                os.environ.get("KNOWLEDGE_IMPORT_TOKEN"),
                os.environ.get("KNOWLEDGE_SERVICE_KEY"),
            )
            if not token or not key:
                raise ValueError("KNOWLEDGE_IMPORT_TOKEN and KNOWLEDGE_SERVICE_KEY required")
        else:
            token = key = "unused-offline"
        async with (
            httpx.AsyncClient(
                base_url=backend_url,
                timeout=30,
                trust_env=False,
                headers={"Authorization": f"Bearer {token}"},
            ) as backend,
            httpx.AsyncClient(
                base_url=service_url,
                timeout=30,
                trust_env=False,
                headers={"Authorization": f"Bearer {key}"},
            ) as service,
        ):
            for row in selected:
                for edge in row["retrieval_edges"]:
                    try:
                        validate_authored_edge(row, edge)
                        record = records[row["source_version_id"]]
                        if args.dry_run:
                            bind_quote(
                                record,
                                root,
                                mapping,
                                row["source_version_id"],
                                edge["evidence_quote"],
                            )
                            result["bound"] += 1
                        else:
                            receipt = await import_edge(
                                backend, service, row, edge, record, root, mapping, receipts
                            )
                            result["imported"] += 1
                            result["receipts"].append({"edge_id": edge["id"], "receipt": receipt})
                    except (ValueError, KeyError, httpx.HTTPError) as exc:
                        result["failures"].append(
                            {"edge_id": edge["id"], "error_type": type(exc).__name__}
                        )
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
                    )

    asyncio.run(run())
    print(json.dumps({k: v for k, v in result.items() if k != "receipts"}))
    raise SystemExit(1 if result["failures"] else 0)


if __name__ == "__main__":
    main()
