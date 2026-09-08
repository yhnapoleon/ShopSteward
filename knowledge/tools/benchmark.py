"""Bounded lexical HTTP benchmark; never ingests, launches services, or calls a model.

Run from the repository root with --target-test --manifest ... --root <corpus-root>
--queries <dev-only.jsonl> --mapping <test-mapping.json> --receipts <import-receipts.json>
--output <new-report.json> --concurrency 1,5,10 --mode lexical.
Authentication comes only from KNOWLEDGE_VERIFY_TOKEN (or KNOWLEDGE_IMPORT_TOKEN)
and KNOWLEDGE_SERVICE_KEY. Missing infrastructure is not replaced with fixtures.
Shared read-only helpers are also used by verify_knowledge_precloud.py.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "knowledge/src"))

from shopsteward_knowledge.bundle import file_info, safe_path  # noqa: E402
from shopsteward_knowledge.contracts import SearchResponse  # noqa: E402

MAX_RESPONSE_BYTES = 21 * 1024 * 1024


class ProbeError(ValueError):
    """Only a fixed error category, never remote response text/headers/credentials."""


def validate_endpoint(url, role):
    try:
        parsed = urlsplit(str(url))
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
            raise ValueError()
    except (ValueError, KeyError):
        raise ValueError(
            "endpoint must be isolated loopback backend:8018 or knowledge:8020"
        ) from None
    return f"http://{parsed.hostname}:{parsed.port}"


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise ValueError("invalid input identifier")
    return value


def instant(value):
    if not isinstance(value, str):
        raise ValueError("query requires an explicit as_of date")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value += "T00:00:00+00:00"
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    return result


def read_input(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, ValueError):
        raise ValueError("missing or malformed input JSON") from None


def load_inputs(
    manifest_path, queries_path=None, mapping_path=None, receipts_path=None, *, root=None
):
    manifest_path = Path(manifest_path)
    base = manifest_path.parent
    root = Path(root or (base.parent if base.name == "manifests" else base))
    manifest = read_input(manifest_path)
    records = manifest.get("documents", [])
    if not 1 <= len(records) <= 2000:
        raise ValueError("manifest requires 1..2000 original versions")
    normalized, versions = [], set()
    for row in records:
        fixture = identifier(row["version_fixture_id"])
        if fixture in versions:
            raise ValueError("duplicate manifest version")
        versions.add(fixture)
        name = row["original_path"]
        if any(p.lower() in {"facts", "eval", "evaluation", "gold"} for p in name.split("/")):
            raise ValueError("evaluation assets are not originals")
        path = safe_path(root, name)
        expected = row.get("sha256", row.get("content_sha256"))
        size = row.get("size", row.get("size_bytes"))
        if not path.is_file() or not 1 <= size <= 20 * 1024 * 1024:
            raise ValueError("missing or oversized original")
        if file_info(path) != {"sha256": expected, "size": size}:
            raise ValueError("original hash/size mismatch")
        normalized.append(
            {
                "version_fixture_id": fixture,
                "document_fixture_id": identifier(row["document_fixture_id"]),
                "sha256": expected,
                "size": size,
                "store_fixture": row.get("store_fixture")
                or row.get("metadata", {}).get("store_fixture"),
            }
        )
    mapping = read_input(mapping_path) if mapping_path else None
    if mapping is not None:
        if mapping.get("target_database") != "shopsteward_test" or not mapping.get("stores"):
            raise ValueError("mapping must designate isolated shopsteward_test")
        for group in ("stores", "skus", "suppliers"):
            for key, value in mapping.get(group, {}).items():
                identifier(key)
                identifier(value)
    receipts = read_input(receipts_path) if receipts_path else None
    if receipts is not None:
        validate_endpoint(receipts.get("target_url", ""), "backend")
        seen = set()
        for row in receipts.get("versions", {}).values():
            identifier(row["document_id"])
            version = identifier(row["version_id"])
            if version in seen:
                raise ValueError("receipt aliases multiple fixtures to one version")
            seen.add(version)
    queries = []
    if queries_path:
        path = Path(queries_path)
        if re.search(r"(^|[-_.])(test|gold|heldout)([-_.]|$)", path.name.lower()) or any(
            p.lower() in {"test", "gold", "heldout"} for p in path.parent.parts
        ):
            raise ValueError("queries must come from a dev-only file")
        try:
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, ValueError):
            raise ValueError("missing or malformed dev queries") from None
        if not 1 <= len(rows) <= 300 or any(row.get("split") != "dev" for row in rows):
            raise ValueError(
                "queries must contain 1..300 explicitly dev rows; mixed splits refused"
            )
        ids = set()
        for row in rows:
            case_id = identifier(row["case_id"])
            if (
                case_id in ids
                or not isinstance(row.get("query"), str)
                or not 1 <= len(row["query"]) <= 4000
            ):
                raise ValueError("invalid or duplicate dev query")
            ids.add(case_id)
            # Explicit projection: answer keys and offline evidence labels never reach HTTP.
            queries.append(
                {
                    "case_id": case_id,
                    "query": row["query"],
                    "as_of": instant(row["as_of"]).isoformat(),
                    "store_fixture": identifier(row["store_fixture"]),
                    "entry_entities": [identifier(v) for v in row.get("entry_entities", [])],
                }
            )
    hashes = {
        name: file_info(Path(path))["sha256"]
        for name, path in (
            ("manifest", manifest_path),
            ("queries", queries_path),
            ("mapping", mapping_path),
            ("receipts", receipts_path),
        )
        if path
    }
    return {
        "records": normalized,
        "queries": queries,
        "mapping": mapping,
        "receipts": receipts,
        "hashes": hashes,
    }


def validate_concurrency(values):
    if (
        not values
        or len(set(values)) != len(values)
        or any(type(v) is not int or v not in {1, 5, 10} for v in values)
    ):
        raise ValueError("concurrency must be unique values from 1,5,10")


def validate_cloud_config(value):
    if (
        type(value.get("billable_run_enabled")) is not bool
        or not isinstance(value.get("regions"), list)
        or len(value["regions"]) > 2
        or not isinstance(value.get("models"), list)
        or len(value["models"]) > 2
    ):
        raise ValueError("cloud experiment allows at most two regions and models")
    if value["billable_run_enabled"]:
        budget = value.get("budget", {})
        if (
            not budget.get("currency")
            or not value["regions"]
            or not value["models"]
            or any(
                type(budget.get(k)) not in {int, float}
                or not math.isfinite(budget[k])
                or budget[k] <= 0
                for k in ("max_total", "max_calls", "max_input_tokens")
            )
            or not budget.get("unit_prices")
        ):
            raise ValueError("billable configuration requires explicit finite budget and prices")


async def request_bytes(client, path, *, body=None, max_bytes=MAX_RESPONSE_BYTES):
    try:
        async with asyncio.timeout(8):
            async with client.stream(
                "POST" if body is not None else "GET",
                path,
                json=body,
                timeout=8,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise ProbeError(f"http_{response.status_code}")
                parts, total = [], 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ProbeError("response_too_large")
                    parts.append(chunk)
                return b"".join(parts)
    except (httpx.TimeoutException, TimeoutError):
        raise ProbeError("timeout") from None
    except httpx.HTTPError:
        raise ProbeError("connection_error") from None


async def request_json(client, path, *, body=None):
    content = await request_bytes(client, path, body=body, max_bytes=2 * 1024 * 1024)
    try:
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except ValueError:
        raise ProbeError("invalid_response") from None


def in_interval(row, as_of):
    return (not row.get("valid_from") or instant(row["valid_from"]) <= as_of) and (
        not row.get("valid_until") or as_of < instant(row["valid_until"])
    )


async def live_inventory(data, backend):
    """Receipts are ID hints. All claims are checked against live authorized GETs."""
    result = {"documents": {}, "versions": {}, "errors": [], "missing_receipts": 0}
    mapping, receipts = data.get("mapping"), data.get("receipts")
    if not mapping or not receipts:
        result["missing_receipts"] = len(data["records"])
        return result
    validate_endpoint(str(backend.base_url), "backend")
    if urlsplit(receipts["target_url"]).port != backend.base_url.port:
        raise ValueError("receipt target differs from benchmark endpoint")
    try:
        async with asyncio.timeout(120):
            for record in data["records"]:
                receipt = receipts.get("versions", {}).get(record["version_fixture_id"])
                if not receipt or not receipt.get("index_receipt", {}).get("request_id"):
                    result["missing_receipts"] += 1
                    continue
                try:
                    doc_id, version_id = (
                        identifier(receipt["document_id"]),
                        identifier(receipt["version_id"]),
                    )
                    if (
                        receipt.get("source_sha256") != record["sha256"]
                        or receipts.get("documents", {}).get(record["document_fixture_id"])
                        != doc_id
                    ):
                        raise ProbeError("receipt_identity_mismatch")
                    fixture = record["store_fixture"] or mapping.get("default_store_fixture")
                    store = mapping["stores"][fixture]
                    doc = await request_json(backend, f"/api/v1/documents/{doc_id}")
                    version = await request_json(
                        backend, f"/api/v1/documents/{doc_id}/versions/{version_id}"
                    )
                    content = await request_bytes(
                        backend, f"/api/v1/documents/{doc_id}/versions/{version_id}/content"
                    )
                    job_id = identifier(receipt["index_receipt"]["request_id"])
                    job = await request_json(
                        backend, f"/api/v1/documents/{doc_id}/index-jobs/{job_id}"
                    )
                    if (
                        doc["id"] != doc_id
                        or doc["store_id"] != store
                        or version["id"] != version_id
                        or version["document_id"] != doc_id
                        or version["size_bytes"] != record["size"]
                        or version["content_sha256"] != record["sha256"]
                        or len(content) != record["size"]
                        or hashlib.sha256(content).hexdigest() != record["sha256"]
                    ):
                        raise ProbeError("original_integrity")
                    if (
                        job["state"] != "SUCCEEDED"
                        or job["version_id"] != version_id
                        or job["document_id"] != doc_id
                        or not any(
                            p["version_id"] == version_id
                            and p["generation_id"] == job["generation_id"]
                            and p["manifest_hash"] == job["manifest_hash"]
                            and p["metadata_revision"] == job["metadata_revision"]
                            for p in doc.get("publications", [])
                        )
                    ):
                        raise ProbeError("publication_not_verified")
                    result["documents"][doc_id] = doc
                    result["versions"][version_id] = {
                        "document_id": doc_id,
                        "sha256": record["sha256"],
                    }
                except (KeyError, TypeError, ValueError) as exc:
                    result["errors"].append(
                        {
                            "version_fixture_id": record["version_fixture_id"],
                            "error": str(exc)
                            if isinstance(exc, ProbeError)
                            else "invalid_response",
                        }
                    )
    except TimeoutError:
        result["errors"].append({"error": "inventory_timeout"})
    return result


def refresh_scope(scope):
    return scope | {"expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat()}


def make_scope(data, inventory, query):
    mapping = data["mapping"]
    store = mapping["stores"][query["store_fixture"]]
    as_of = instant(query["as_of"])
    allowed = []
    for doc in inventory["documents"].values():
        if doc["store_id"] != store or doc["status"] != "active":
            continue
        for pub in doc.get("publications", []):
            if (
                pub["version_id"] in inventory["versions"]
                and in_interval(pub, as_of)
                and pub["metadata_revision"] == doc.get("evidence_revision")
            ):
                allowed.append(
                    {k: pub[k] for k in ("version_id", "generation_id", "metadata_revision")}
                )
    return {
        "principal_ref": identifier(mapping.get("principal_id", "precloud-verification")),
        "store_id": store,
        "as_of": as_of.isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        "allowed_versions": allowed,
    }


def search_body(data, scope, query):
    entities = data["mapping"].get("skus", {}) | data["mapping"].get("suppliers", {})
    return {
        "query": query["query"],
        "scope": scope,
        "profile_id": "lexical-v1",
        "deadline_ms": 8000,
        "limit": 6,
        "entity_ids": [entities[key] for key in query.get("entry_entities", [])],
    }


def validate_response(value, scope, inventory, *, profile="lexical-v1", entity_ids=()):
    try:
        response = SearchResponse.model_validate(value)
        if response.retrieval_profile != profile:
            raise ValueError()
        allowed = {
            (v["version_id"], v["generation_id"], v["metadata_revision"])
            for v in scope["allowed_versions"]
        }
        ids = set()
        for hit in response.candidates:
            identity = (hit.version_id, hit.generation_id, hit.metadata_revision)
            version = inventory["versions"][hit.version_id]
            if (
                identity not in allowed
                or hit.store_id != scope["store_id"]
                or hit.document_id != version["document_id"]
                or hit.original_sha256 != version["sha256"]
                or not in_interval(hit.model_dump(mode="json"), instant(scope["as_of"]))
                or (entity_ids and not set(entity_ids).intersection(hit.entity_refs))
                or (hit.generation_id, hit.chunk_id) in ids
            ):
                raise ValueError()
            ids.add((hit.generation_id, hit.chunk_id))
        if any(not math.isfinite(v) or v < 0 for v in response.timings_ms.values()):
            raise ValueError()
        if response.degraded:
            raise ProbeError("degraded")
        return response
    except ProbeError:
        raise
    except (KeyError, ValueError, TypeError):
        raise ProbeError("invalid_response") from None


async def recheck_authority(backend, hits, scope):
    for doc_id in sorted({hit.document_id for hit in hits}):
        doc = await request_json(backend, f"/api/v1/documents/{identifier(doc_id)}")
        for hit in (h for h in hits if h.document_id == doc_id):
            if (
                doc.get("id") != doc_id
                or doc.get("status") != "active"
                or doc.get("store_id") != scope["store_id"]
                or doc.get("evidence_revision") != hit.metadata_revision
                or not any(
                    p["version_id"] == hit.version_id
                    and p["generation_id"] == hit.generation_id
                    and p["metadata_revision"] == hit.metadata_revision
                    and in_interval(p, instant(scope["as_of"]))
                    for p in doc.get("publications", [])
                )
            ):
                raise ProbeError("authority_changed")


def percentile(values, fraction):
    if not values:
        return None
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 3)


def summary(samples, elapsed):
    passed = [s for s in samples if s["status"] == "passed"]
    timings = [s["elapsed_ms"] for s in passed]
    stages = sorted({stage for s in passed for stage in s["server_timings_ms"]})
    attempted_timings = [s["elapsed_ms"] for s in samples if s["dispatched"]]
    return {
        "scheduled": len(samples),
        "attempted": sum(s["dispatched"] for s in samples),
        "succeeded": len(passed),
        "failed": sum(s["status"] == "failed" for s in samples),
        "not_run": sum(s["status"] == "not_run" for s in samples),
        "timeouts": sum(s["error"] == "timeout" for s in samples),
        "errors_by_category": dict(Counter(s["error"] for s in samples if s["error"])),
        "wall_ms": round(elapsed * 1000, 3),
        "latency_ms": {
            "p50": percentile(timings, 0.5),
            "p95": percentile(timings, 0.95),
            "denominator": len(passed),
            "population": "successful_queries",
        },
        "latency_all_attempts_ms": {
            "p50": percentile(attempted_timings, 0.5),
            "p95": percentile(attempted_timings, 0.95),
            "denominator": len(attempted_timings),
            "population": "all_dispatched_queries_including_failures",
        },
        "stages_ms": {
            stage: {
                "p50": percentile(
                    [
                        s["server_timings_ms"][stage]
                        for s in passed
                        if stage in s["server_timings_ms"]
                    ],
                    0.5,
                ),
                "p95": percentile(
                    [
                        s["server_timings_ms"][stage]
                        for s in passed
                        if stage in s["server_timings_ms"]
                    ],
                    0.95,
                ),
                "denominator": sum(stage in s["server_timings_ms"] for s in passed),
            }
            for stage in stages
        },
        "samples": samples,
    }


async def benchmark(data, backend, service, *, concurrency=(1, 5, 10)):
    validate_concurrency(concurrency)
    validate_endpoint(str(backend.base_url), "backend")
    validate_endpoint(str(service.base_url), "knowledge")
    if not data["queries"] or not data.get("mapping") or not data.get("receipts"):
        raise ValueError("benchmark requires dev queries, test mapping and API receipts")
    inventory = await live_inventory(data, backend)
    if inventory["errors"] or inventory["missing_receipts"]:
        raise ProbeError("inventory_not_verified")
    report = {
        "schema_version": 1,
        "environment": "loopback/local",
        "mode": "lexical",
        "profile": "lexical-v1",
        "latency_scope": "search_HTTP_and_final_authority_recheck_excluding_queue",
        "cache_state": "uncontrolled_sequential_batches_no_cache_reset",
        "billable_run_enabled": False,
        "input_hashes": data["hashes"],
        "documents_verified": len(inventory["documents"]),
        "versions_verified": len(inventory["versions"]),
        "batches": [],
        "ingest": {
            "status": "not_run",
            "reason": "read_only_query_benchmark",
            "initial_index_ms": None,
            "incremental_index_ms": None,
            "chunk_count": None,
            "parser_coverage": None,
        },
        "resources": {
            "server_peak_ram_bytes": None,
            "server_peak_cpu_percent": None,
            "server_disk_bytes": None,
            "status": "not_run",
        },
        "tokens": {
            "actual": None,
            "query_characters": sum(len(q["query"]) for q in data["queries"]),
            "note": "characters are not model tokens",
        },
    }
    for level in concurrency:
        semaphore = asyncio.Semaphore(level)
        start = time.perf_counter()

        async def one(query, gate=semaphore):
            queued = time.perf_counter()
            async with gate:
                began = time.perf_counter()
                sample = {
                    "case_id": query["case_id"],
                    "query_sha256": hashlib.sha256(query["query"].encode()).hexdigest(),
                    "queue_ms": round((began - queued) * 1000, 3),
                    "status": "not_run",
                    "dispatched": False,
                    "error": None,
                    "server_timings_ms": {},
                    "candidate_count": 0,
                }
                try:
                    async with asyncio.timeout(10):
                        scope = make_scope(data, inventory, query)
                        if not scope["allowed_versions"]:
                            sample["error"] = "no_visible_versions"
                            return sample | {
                                "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)
                            }
                        body = search_body(data, scope, query)
                        sample["dispatched"] = True
                        response = validate_response(
                            await request_json(service, "/internal/v1/search", body=body),
                            scope,
                            inventory,
                            entity_ids=body["entity_ids"],
                        )
                        await recheck_authority(backend, response.candidates, scope)
                        sample.update(
                            status="passed",
                            server_timings_ms=response.timings_ms,
                            candidate_count=len(response.candidates),
                        )
                except (TimeoutError, httpx.TimeoutException):
                    sample.update(status="failed", error="timeout")
                except (ValueError, KeyError, TypeError) as exc:
                    sample.update(
                        status="failed",
                        error=str(exc) if isinstance(exc, ProbeError) else "invalid_input",
                    )
                sample["elapsed_ms"] = round((time.perf_counter() - began) * 1000, 3)
                return sample

        samples = await asyncio.gather(*(one(q) for q in data["queries"]))
        report["batches"].append(
            {"concurrency": level, **summary(samples, time.perf_counter() - start)}
        )
    return report


def add_input_arguments(parser):
    parser.add_argument("--target-test", action="store_true", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--queries", type=Path, help="separate JSONL file containing only dev rows")
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8018")
    parser.add_argument("--knowledge-url", default="http://127.0.0.1:8020")


def cli_inputs(args):
    validate_endpoint(args.backend_url, "backend")
    validate_endpoint(args.knowledge_url, "knowledge")
    if args.output.exists():
        raise ValueError("output must be a new report file")
    return load_inputs(args.manifest, args.queries, args.mapping, args.receipts, root=args.root)


def credentials():
    token = os.environ.get("KNOWLEDGE_VERIFY_TOKEN") or os.environ.get("KNOWLEDGE_IMPORT_TOKEN")
    key = os.environ.get("KNOWLEDGE_SERVICE_KEY")
    if not token or not key:
        raise ProbeError("missing_authentication")
    return token, key


async def run_http(args, data, operation):
    token, key = credentials()
    async with (
        httpx.AsyncClient(
            base_url=args.backend_url,
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
            follow_redirects=False,
            timeout=8,
        ) as backend,
        httpx.AsyncClient(
            base_url=args.knowledge_url,
            headers={"Authorization": "Bearer " + key},
            trust_env=False,
            follow_redirects=False,
            timeout=8,
        ) as service,
    ):
        return await operation(data, backend, service)


def write_report(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_input_arguments(parser)
    parser.add_argument("--concurrency", default="1,5,10")
    parser.add_argument("--mode", choices=["lexical"], default="lexical")
    parser.add_argument(
        "--budget-config",
        type=Path,
        help="validate cloud planning inputs; never enables spending here",
    )
    args = parser.parse_args(argv)
    try:
        data = cli_inputs(args)
        levels = [int(v) for v in args.concurrency.split(",")]
        validate_concurrency(levels)
        if args.budget_config:
            validate_cloud_config(read_input(args.budget_config))

        async def operation(data, backend, service):
            return await benchmark(data, backend, service, concurrency=levels)

        try:
            result = asyncio.run(run_http(args, data, operation))
        except ProbeError as exc:
            result = {
                "schema_version": 1,
                "environment": "loopback/local",
                "mode": "lexical",
                "profile": "lexical-v1",
                "billable_run_enabled": False,
                "input_hashes": data["hashes"],
                "batches": [],
                "status": "not_run" if str(exc) == "missing_authentication" else "failed",
                "error": str(exc),
            }
        write_report(args.output, result)
        success = bool(result["batches"]) and all(
            b["failed"] == 0 and b["not_run"] == 0 for b in result["batches"]
        )
        print(
            json.dumps(
                {"status": "passed" if success else "failed", "batches": len(result["batches"])}
            )
        )
        return 0 if success else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {
                    "status": "not_run",
                    "error": str(exc) if isinstance(exc, ProbeError) else "invalid_inputs",
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
