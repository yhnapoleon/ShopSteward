"""Validated, resumable corpus import through the real K1/K2 API only."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def prepare_upload(record, root, mapping):
    root = Path(root).resolve()
    relative = record.get("original_path", record.get("path"))
    if not relative:
        raise ValueError("original path required")
    path = root / relative
    if Path(relative).is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("unsafe original path")
    content = path.read_bytes()
    expected = record.get("content_sha256", record.get("sha256"))
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise ValueError("original hash mismatch")
    if not 1 <= len(content) <= 20 * 1024 * 1024 or len(content) != record.get(
        "size_bytes", record.get("size")
    ):
        raise ValueError("original size invalid")
    source_metadata = record.get("metadata", {})
    metadata = {
        k: v
        for k, v in source_metadata.items()
        if k in {"title", "category", "visibility", "valid_from", "valid_until"}
    }
    store = record.get(
        "store_fixture_id", record.get("store_fixture", source_metadata.get("store_fixture"))
    )
    if store is None:
        store = mapping.get("default_store_fixture")
    try:
        store_id = mapping["stores"][store]
        metadata["sku_ids"] = [
            mapping["skus"][key]
            for key in record.get(
                "sku_fixture_ids",
                source_metadata.get("sku_fixture_ids", source_metadata.get("sku_ids", [])),
            )
        ]
        metadata["supplier_ids"] = [
            mapping["suppliers"][key]
            for key in record.get(
                "supplier_fixture_ids",
                source_metadata.get(
                    "supplier_fixture_ids", source_metadata.get("supplier_ids", [])
                ),
            )
        ]
    except KeyError as exc:
        raise ValueError(f"missing explicit fixture mapping: {exc.args[0]}") from None
    metadata.setdefault("title", record.get("title", path.stem))
    metadata.setdefault("category", record.get("category", "general"))
    provenance = record.get("provenance", source_metadata.get("provenance", record))
    metadata["provenance"] = {
        key: provenance[key]
        for key in (
            "source_kind",
            "source_family_id",
            "scenario_family_id",
            "source_url",
            "publisher",
            "jurisdiction",
            "synthetic",
        )
        if key in provenance
    }
    if "source_url" not in metadata["provenance"] and record.get("url"):
        metadata["provenance"]["source_url"] = record["url"]
    for field in ("valid_from", "valid_until"):
        if field in record:
            metadata[field] = record[field]
    # Corpus authoring fields never leak into the strict upload API.
    from app.knowledge.schemas import UploadMetadata

    metadata = UploadMetadata.model_validate(metadata).model_dump(mode="json")
    doc = record["document_fixture_id"]
    version = record["version_fixture_id"]
    key = hashlib.sha256(
        json.dumps([doc, version, store_id, actual], sort_keys=True).encode()
    ).hexdigest()
    return {
        "store_id": store_id,
        "metadata": metadata,
        "path": path,
        "document_fixture_id": doc,
        "version_fixture_id": version,
        "key": key,
        "content_sha256": actual,
    }


async def import_records(
    client,
    prepared,
    *,
    token,
    receipts_path,
    profile_id="lexical-v1",
    publish=False,
    wait_seconds=120,
):
    receipts_path = Path(receipts_path)
    state = (
        json.loads(receipts_path.read_text("utf-8"))
        if receipts_path.exists()
        else {"documents": {}, "versions": {}}
    )
    state.setdefault("pending_uploads", {})
    target = str(client.base_url)
    if state.get("target_url", target) != target:
        raise ValueError("import receipts belong to another API target")
    state["target_url"] = target

    def save():
        receipts_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = receipts_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
        temporary.replace(receipts_path)

    failures = []
    for item in prepared:
        fixture_doc, fixture_version = item["document_fixture_id"], item["version_fixture_id"]
        headers = {"Authorization": "Bearer " + token, "Idempotency-Key": item["key"]}
        try:
            old = state["versions"].get(fixture_version)
            if old and old.get("source_sha256") != item["content_sha256"]:
                raise ValueError("receipt source changed; use a new fixture version")
            if old:
                doc_id, version_id = old["document_id"], old["version_id"]
            else:
                known = state["documents"].get(fixture_doc)
                pending = state["pending_uploads"].get(fixture_version)
                if pending:
                    if pending["key"] != item["key"]:
                        raise ValueError("pending import source changed")
                    path, body = pending["path"], pending["body"]
                elif known:
                    current = await client.get(f"/api/v1/documents/{known}", headers=headers)
                    current.raise_for_status()
                    body = {
                        key: value
                        for key, value in item["metadata"].items()
                        if key in {"valid_from", "valid_until", "provenance"}
                    }
                    body["expected_metadata_version"] = current.json()["metadata_version"]
                    path = f"/api/v1/documents/{known}/versions"
                else:
                    body = item["metadata"]
                    path = f"/api/v1/stores/{item['store_id']}/documents"
                state["pending_uploads"][fixture_version] = {
                    "path": path,
                    "body": body,
                    "key": item["key"],
                }
                # Persist the exact CAS-bearing request before the remote mutation.
                save()
                with item["path"].open("rb") as stream:
                    response = await client.post(
                        path,
                        headers=headers,
                        data={"metadata": json.dumps(body, ensure_ascii=False)},
                        files={"file": (item["path"].name, stream, "application/octet-stream")},
                    )
                response.raise_for_status()
                doc = response.json()
                doc_id, version_id = doc["id"], doc["latest_version_id"]
                state["documents"][fixture_doc] = doc_id
                state["versions"][fixture_version] = {
                    "document_id": doc_id,
                    "version_id": version_id,
                    "source_sha256": item["content_sha256"],
                    "upload_receipt": doc,
                }
                state["pending_uploads"].pop(fixture_version, None)
                save()
            response = await client.post(
                f"/api/v1/documents/{doc_id}/versions/{version_id}/index-jobs",
                headers=headers | {"Idempotency-Key": item["key"] + "-index"},
                json={"profile_id": profile_id},
            )
            response.raise_for_status()
            job = response.json()
            state["versions"][fixture_version]["index_receipt"] = job
            state["versions"][fixture_version]["index_profile_id"] = profile_id
            save()
            if publish:
                saved_version = state["versions"][fixture_version]
                if "publication_receipt" in saved_version:
                    continue
                deadline = time.monotonic() + wait_seconds
                request_id = job.get("request_id", job.get("id"))
                while job.get("state", job.get("status")) not in {"READY", "SUCCEEDED", "FAILED"}:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("index job not ready before import deadline")
                    await asyncio.sleep(0.25)
                    response = await client.get(
                        f"/api/v1/documents/{doc_id}/index-jobs/{request_id}", headers=headers
                    )
                    response.raise_for_status()
                    job = response.json()
                saved_version["index_receipt"] = job
                save()
                if job.get("state", job.get("status")) == "FAILED":
                    raise RuntimeError("index job failed")
                publication_body = saved_version.get("publication_request")
                if publication_body is None:
                    response = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
                    response.raise_for_status()
                    current = response.json()
                    publication_body = {
                        "version_id": version_id,
                        "generation_id": job["generation_id"],
                        "manifest_hash": job["manifest_hash"],
                        "expected_publication_revision": current.get("publication_revision", 0),
                    }
                    saved_version["publication_request"] = publication_body
                    save()
                response = await client.post(
                    f"/api/v1/documents/{doc_id}/publications",
                    headers=headers | {"Idempotency-Key": item["key"] + "-publish"},
                    json=publication_body,
                )
                response.raise_for_status()
                state["versions"][fixture_version]["publication_receipt"] = response.json()
                save()
        except (httpx.HTTPError, ValueError, TimeoutError, RuntimeError, KeyError) as exc:
            # Preserve error categories without serializing request Authorization or URLs.
            failures.append(
                {
                    "version_fixture_id": fixture_version,
                    "error_type": type(exc).__name__,
                    "http_status": exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None,
                }
            )
    return {"uploaded_versions": len(state["versions"]), "failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--target-test", action="store_true", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--entities", type=Path)
    parser.add_argument("--prepare-mapping", action="store_true")
    parser.add_argument("--seed-test", action="store_true")
    parser.add_argument("--namespace", default="precloud01")
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--receipts", type=Path, default=Path("var/precloud/import-receipts.json"))
    args = parser.parse_args()
    target = urlparse(args.base_url)
    if target.hostname not in {"127.0.0.1", "localhost"} or target.port in {8000, 8001, 3000}:
        parser.error("test import requires isolated loopback API, not the development ports")
    manifest = json.loads(args.manifest.read_text("utf-8"))
    root = args.root or args.manifest.resolve().parent.parent
    if args.prepare_mapping or args.seed_test:
        if args.entities is None:
            parser.error("--entities is required for fixture preparation")
        from tools.knowledge_test_fixture import fixture_plan, seed_fixture

        entities = json.loads(args.entities.read_text("utf-8"))
        mapping, _ = fixture_plan(entities, args.namespace)
        if args.mapping.exists():
            existing = json.loads(args.mapping.read_text("utf-8"))
            if any(
                existing.get(k) != mapping.get(k)
                for k in ("entities_sha256", "namespace", "stores", "skus", "suppliers")
            ):
                parser.error("mapping already belongs to different fixtures; use a fresh output")
            mapping["seeded"] = bool(existing.get("seeded") or mapping["seeded"])
        # Validate all source files and existing mapping before any database mutation.
        for record in manifest["documents"]:
            prepare_upload(record, root, mapping)
        if args.seed_test and not args.dry_run:
            url = os.environ.get("TEST_DATABASE_URL")
            if not url:
                parser.error("set TEST_DATABASE_URL to the dedicated local test database")
            mapping = asyncio.run(seed_fixture(entities, args.namespace, url))
        args.mapping.parent.mkdir(parents=True, exist_ok=True)
        args.mapping.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), "utf-8")
    else:
        mapping = json.loads(args.mapping.read_text("utf-8"))
    prepared = [prepare_upload(row, root, mapping) for row in manifest["documents"]]
    if args.dry_run:
        print(json.dumps({"validated_original_versions": len(prepared), "business_writes": 0}))
        return
    if mapping.get("target_database") != "shopsteward_test" or not mapping.get("seeded"):
        parser.error(
            "mapping must identify seeded entities in the dedicated shopsteward_test database"
        )
    token = os.environ.get("KNOWLEDGE_IMPORT_TOKEN")
    if not token:
        parser.error("set KNOWLEDGE_IMPORT_TOKEN for the isolated test API")

    async def run():
        async with httpx.AsyncClient(base_url=args.base_url, timeout=60, trust_env=False) as client:
            return await import_records(
                client, prepared, token=token, receipts_path=args.receipts, publish=args.publish
            )

    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(1 if result["failures"] else 0)


if __name__ == "__main__":
    main()
