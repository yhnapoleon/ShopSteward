"""Read-only C3 HTTP evidence probes on isolated backend 8018 / knowledge 8020.

Requires --target-test --manifest ... --output <new.json>. Add --root, --queries
(dev-only JSONL), --mapping and --receipts from the separate importer to exercise
retrieval. Auth: KNOWLEDGE_VERIFY_TOKEN (or KNOWLEDGE_IMPORT_TOKEN) and
KNOWLEDGE_SERVICE_KEY. This tool starts no processes, mutates no business data,
and never upgrades supplied 'passed' labels into execution evidence. Build,
restore, Agent and lifecycle exercises require their owners' active execution;
this bounded harness reports those as not_run even if receipt labels say passed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "knowledge/tools"))
sys.path.insert(0, str(REPO / "knowledge/src"))

import benchmark as common  # noqa: E402
from shopsteward_knowledge.readiness import REQUIRED_CHECKS, ready_for_cloud_pilot  # noqa: E402

LIFECYCLE = (
    "resume_import",
    "cross_store_future_versions",
    "archive_final_recheck",
    "failed_publication_preserves_old",
    "worker_lease_loss",
    "worker_restart",
    "api_timeout_degradation",
    "relation_conditions",
    "business_state_unchanged",
)


def empty_report(hashes=None):
    return {
        "schema_version": 1,
        "environment": "loopback/local",
        "input_hashes": hashes or {},
        "checks": dict.fromkeys(sorted(REQUIRED_CHECKS), "not_run"),
        "scenarios": {
            k: {"status": "not_run", "reason": "requires_dedicated_setup_and_active_replay"}
            for k in LIFECYCLE
        },
        "pilot_ready": False,
        "MVP_ready": False,
        "cloud_model_quality": "not_run",
        "cloud_latency": "not_run",
        "cloud_cost": "not_run",
        "billable_run_enabled": False,
        "limitations": [
            "direct_service_probes_do_not_execute_Agent_tools",
            "build_restore_and_lifecycle_are_not_executed_by_this_harness",
            "no_server_resource_or_ingest_benchmark",
        ],
    }


async def verify_precloud(data, backend, service):
    common.validate_endpoint(str(backend.base_url), "backend")
    common.validate_endpoint(str(service.base_url), "knowledge")
    report = empty_report(data["hashes"])

    async def scenario(name, operation):
        began = time.perf_counter()
        try:
            result = await operation()
            report["scenarios"][name] = {"status": "passed", **(result or {})}
            return True
        except (ValueError, KeyError, TypeError) as exc:
            report["scenarios"][name] = {
                "status": "failed",
                "error": str(exc) if isinstance(exc, common.ProbeError) else "invalid_response",
            }
            return False
        finally:
            report["scenarios"][name]["elapsed_ms"] = round((time.perf_counter() - began) * 1000, 3)

    async def health():
        for client, expected in ((backend, "ok"), (service, "ready")):
            reply = await common.request_json(client, "/health/ready")
            if reply.get("status") != expected:
                raise common.ProbeError("not_ready")

    if not await scenario("health", health):
        report["checks"]["real_http"] = "failed"
        return report
    inventory = await common.live_inventory(data, backend)
    report["inventory"] = {
        "versions_verified": len(inventory["versions"]),
        "documents_verified": len(inventory["documents"]),
        "missing_receipts": inventory["missing_receipts"],
        "errors": inventory["errors"],
    }
    if inventory["errors"]:
        report["checks"]["corpus_200"] = "failed"
        report["scenarios"]["original_integrity"] = {"status": "failed"}
        return report
    if inventory["missing_receipts"] or not data.get("queries") or not data.get("mapping"):
        report["scenarios"]["original_integrity"] = {
            "status": "not_run",
            "reason": "missing_inputs_or_receipts",
        }
        return report
    report["scenarios"]["original_integrity"] = {
        "status": "passed",
        "versions": len(inventory["versions"]),
    }
    report["checks"]["corpus_200"] = "passed" if len(inventory["documents"]) >= 200 else "failed"
    # This is protocol/integrity probing, not a relevance-quality score or an Agent run.
    query = data["queries"][0]
    scope = common.make_scope(data, inventory, query)
    if not scope["allowed_versions"]:
        report["scenarios"]["evidence_integrity"] = {
            "status": "not_run",
            "reason": "no_visible_versions",
        }
        return report
    body = common.search_body(data, scope, query)

    async def search(payload):
        payload = payload | {"scope": common.refresh_scope(payload["scope"])}
        result = await common.request_json(service, "/internal/v1/search", body=payload)
        return common.validate_response(
            result, payload["scope"], inventory, entity_ids=payload.get("entity_ids", [])
        )

    async def no_match():
        payload = dict(body, query="precloudnomatch" + uuid4().hex, entity_ids=[])
        response = await search(payload)
        if response.candidates:
            raise common.ProbeError("unexpected_match")
        return {
            "query_sha256": hashlib.sha256(payload["query"].encode()).hexdigest(),
            "candidate_count": 0,
        }

    async def evidence():
        response = await search(body)
        if not response.candidates:
            raise common.ProbeError("no_evidence_for_probe")
        reply = await common.request_json(
            service,
            "/internal/v1/evidence",
            body={
                "scope": common.refresh_scope(scope),
                "chunk_ids": [c.chunk_id for c in response.candidates],
            },
        )
        observed = common.validate_response(reply, scope, inventory, profile="evidence-v1")
        by_id = {(c.generation_id, c.chunk_id): c for c in observed.candidates}
        if len(by_id) != len(response.candidates):
            raise common.ProbeError("evidence_identity_mismatch")
        for hit in response.candidates:
            restored = by_id.get((hit.generation_id, hit.chunk_id))
            if (
                not restored
                or restored.locator != hit.locator
                or (
                    not restored.text.startswith(hit.text)
                    if hit.truncated
                    else restored.text != hit.text
                )
            ):
                raise common.ProbeError("evidence_identity_mismatch")
        await common.recheck_authority(backend, observed.candidates, scope)
        return {
            "candidate_count": len(response.candidates),
            "case_id": query["case_id"],
            "query_sha256": hashlib.sha256(query["query"].encode()).hexdigest(),
        }

    async def hit_filter():
        # Denial probes keep the same query. A synthetic wrong store exercises
        # service filtering, but is not an actual cross-tenant lifecycle rehearsal.
        for denied in (
            dict(scope, allowed_versions=[]),
            dict(scope, store_id="precloud-denied-" + uuid4().hex),
        ):
            if (await search(dict(body, scope=denied))).candidates:
                raise common.ProbeError("scope_leak")
        return {"denial_probes": 2, "scope": "empty_and_wrong_store"}

    outcomes = [
        await scenario("no_match", no_match),
        await scenario("evidence_integrity", evidence),
        await scenario("hit_filter", hit_filter),
    ]
    report["checks"]["real_http"] = "passed" if all(outcomes) else "failed"
    report["pilot_ready"] = ready_for_cloud_pilot(report["checks"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    common.add_input_arguments(parser)
    args = parser.parse_args(argv)
    try:
        data = common.cli_inputs(args)
        try:
            report = asyncio.run(common.run_http(args, data, verify_precloud))
        except common.ProbeError as exc:
            report = empty_report(data["hashes"])
            report["execution_error"] = str(exc)
        common.write_report(args.output, report)
        print(json.dumps({"pilot_ready": report["pilot_ready"], "checks": report["checks"]}))
        return 0 if report["pilot_ready"] else 1
    except (OSError, ValueError, KeyError, TypeError):
        print('{"error":"invalid_inputs","pilot_ready":false}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
