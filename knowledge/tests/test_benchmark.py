import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]


def load_benchmark():
    path = REPO / "knowledge/tools/benchmark.py"
    spec = importlib.util.spec_from_file_location("precloud_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs(tmp_path):
    raw = b"Keep chilled."
    (tmp_path / "originals").mkdir()
    (tmp_path / "originals/a.md").write_bytes(raw)
    record = dict(
        document_fixture_id="FD1",
        version_fixture_id="FV1",
        original_path="originals/a.md",
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        metadata={"store_fixture": "FS1"},
    )
    files = {
        "manifest.json": {"documents": [record]},
        "mapping.json": {
            "target_database": "shopsteward_test",
            "stores": {"FS1": "S1"},
            "skus": {"FSKU1": "SKU1"},
            "suppliers": {},
            "principal_id": "P1",
        },
        "receipts.json": {
            "target_url": "http://127.0.0.1:8018/",
            "documents": {"FD1": "D1"},
            "versions": {
                "FV1": {
                    "document_id": "D1",
                    "version_id": "V1",
                    "source_sha256": record["sha256"],
                    "index_receipt": {"request_id": "J1"},
                    "publication_receipt": {"generation_id": "G1", "manifest_hash": "a" * 64},
                }
            },
        },
    }
    for name, value in files.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    query = {
        "case_id": "Q1",
        "split": "dev",
        "query": "chilled",
        "as_of": "2026-01-10",
        "store_fixture": "FS1",
        "entry_entities": [],
        "required_evidence": ["GOLD_SECRET"],
        "forbidden_claims": ["DO_NOT_SEND"],
        "expected_behavior": "answer",
    }
    (tmp_path / "dev.jsonl").write_text(json.dumps(query) + "\n", encoding="utf-8")
    return tmp_path


def load_inputs(module, root):
    return module.load_inputs(
        root / "manifest.json",
        root / "dev.jsonl",
        root / "mapping.json",
        root / "receipts.json",
        root=root,
    )


def candidate():
    text = "Keep chilled."
    return dict(
        document_id="D1",
        version_id="V1",
        generation_id="G1",
        chunk_id="C1",
        store_id="S1",
        metadata_revision=1,
        title="Storage",
        text=text,
        locator={"kind": "paragraph", "paragraph_range": [1, 1]},
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        original_sha256=hashlib.sha256(text.encode()).hexdigest(),
        valid_from="2026-01-01T00:00:00Z",
        valid_until="2026-02-01T00:00:00Z",
    )


def service_response(hits=None, **extra):
    return dict(
        request_id="R1",
        retrieval_profile="lexical-v1",
        candidates=hits or [],
        timings_ms={"total": 1.25},
        degraded=False,
        warnings=[],
        **extra,
    )


def backend_response(request):
    path = request.url.path
    if path == "/health/ready":
        return httpx.Response(200, json={"status": "ok", "component": "backend"})
    if path == "/api/v1/documents/D1":
        return httpx.Response(
            200,
            json={
                "id": "D1",
                "store_id": "S1",
                "metadata_version": 1,
                "evidence_revision": 1,
                "status": "active",
                "publications": [
                    {
                        "version_id": "V1",
                        "generation_id": "G1",
                        "metadata_revision": 1,
                        "manifest_hash": "a" * 64,
                        "valid_from": "2026-01-01T00:00:00Z",
                        "valid_until": "2026-02-01T00:00:00Z",
                    }
                ],
            },
        )
    if path.endswith("/versions/V1"):
        return httpx.Response(
            200,
            json={
                "id": "V1",
                "document_id": "D1",
                "size_bytes": 13,
                "content_sha256": hashlib.sha256(b"Keep chilled.").hexdigest(),
            },
        )
    if path.endswith("/content"):
        return httpx.Response(200, content=b"Keep chilled.")
    if path.endswith("/index-jobs/J1"):
        return httpx.Response(
            200,
            json={
                "state": "SUCCEEDED",
                "document_id": "D1",
                "version_id": "V1",
                "generation_id": "G1",
                "metadata_revision": 1,
                "manifest_hash": "a" * 64,
            },
        )
    raise AssertionError(path)


@pytest.mark.parametrize(
    "url,role",
    [
        ("https://127.0.0.1:8020", "knowledge"),
        ("http://evil:8020", "knowledge"),
        ("http://127.0.0.1:8000", "backend"),
        ("http://u:secret@localhost:8020", "knowledge"),
        ("http://localhost:8020/path", "knowledge"),
        ("http://localhost:8020?x=1", "knowledge"),
        ("http://localhost:8020#x", "knowledge"),
        ("http://localhost:8018", "knowledge"),
    ],
)
def test_endpoints_are_exact_isolated_loopback_ports(url, role):
    with pytest.raises(ValueError):
        load_benchmark().validate_endpoint(url, role)


def test_dev_query_projection_does_not_send_gold(inputs):
    data = load_inputs(load_benchmark(), inputs)
    encoded = json.dumps(data["queries"])
    assert "GOLD_SECRET" not in encoded and "DO_NOT_SEND" not in encoded
    assert data["queries"][0]["query"] == "chilled"
    assert (
        data["hashes"]["manifest"]
        == hashlib.sha256((inputs / "manifest.json").read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("split", ["test", None, "train"])
def test_nondev_rows_cannot_enter_benchmark(inputs, split):
    path = inputs / "dev.jsonl"
    row = json.loads(path.read_text())
    row["split"] = split
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="dev"):
        load_inputs(load_benchmark(), inputs)


def test_mixed_file_is_rejected_even_if_first_row_is_dev(inputs):
    path = inputs / "dev.jsonl"
    row = json.loads(path.read_text())
    row.update(case_id="held-out", split="test")
    with path.open("a") as stream:
        stream.write(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="dev"):
        load_inputs(load_benchmark(), inputs)


def test_manifest_original_hash_is_checked_before_network(inputs):
    (inputs / "originals/a.md").write_bytes(b"changed")
    with pytest.raises(ValueError, match="original"):
        load_inputs(load_benchmark(), inputs)


def test_receipt_target_cannot_point_at_development(inputs):
    path = inputs / "receipts.json"
    receipt = json.loads(path.read_text())
    receipt["target_url"] = "http://127.0.0.1:8000"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="endpoint"):
        load_inputs(load_benchmark(), inputs)


@pytest.mark.parametrize("values", [[0], [2], [1, 1], [11], []])
def test_concurrency_is_bounded(values):
    with pytest.raises(ValueError):
        load_benchmark().validate_concurrency(values)


async def test_benchmark_runs_each_query_at_each_concurrency_with_real_metrics(inputs):
    module = load_benchmark()
    data = load_inputs(module, inputs)
    data["queries"] = [dict(data["queries"][0], case_id=f"Q{i}") for i in range(12)]
    active = peak = calls = 0

    async def handler(request):
        nonlocal active, peak, calls
        body = json.loads(request.content)
        assert body["profile_id"] == "lexical-v1"
        assert "GOLD_SECRET" not in request.content.decode()
        active += 1
        peak = max(peak, active)
        calls += 1
        await asyncio.sleep(0.002)
        active -= 1
        return httpx.Response(200, json=service_response([candidate()]))

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(backend_response)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(handler)
        ) as service,
    ):
        result = await module.benchmark(data, backend, service, concurrency=[1, 5, 10])
    assert calls == 36 and 5 < peak <= 10
    assert [r["attempted"] for r in result["batches"]] == [12, 12, 12]
    assert all(r["succeeded"] == 12 for r in result["batches"])
    assert all(r["latency_ms"]["p95"] >= 0 for r in result["batches"])
    assert result["billable_run_enabled"] is False
    assert result["ingest"]["status"] == "not_run"
    assert result["resources"]["server_peak_ram_bytes"] is None
    assert "chilled" not in json.dumps(result)


@pytest.mark.parametrize(
    "fault,want",
    [
        ("timeout", "timeout"),
        ("http", "http_503"),
        ("scope", "invalid_response"),
        ("degraded", "degraded"),
    ],
)
async def test_benchmark_counts_every_error_and_never_reports_empty_success(inputs, fault, want):
    module = load_benchmark()
    data = load_inputs(module, inputs)

    def handler(request):
        if fault == "timeout":
            raise httpx.ReadTimeout("secret bearer private", request=request)
        if fault == "http":
            return httpx.Response(503, text="secret bearer private")
        hit = candidate()
        if fault == "scope":
            hit["store_id"] = "OTHER"
        body = service_response([hit])
        if fault == "degraded":
            body["degraded"] = True
        return httpx.Response(200, json=body)

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(backend_response)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(handler)
        ) as service,
    ):
        report = await module.benchmark(data, backend, service, concurrency=[1])
    batch = report["batches"][0]
    assert batch["attempted"] == 1 and batch["failed"] == 1 and batch["succeeded"] == 0
    assert batch["samples"][0]["error"] == want
    assert batch["errors_by_category"] == {want: 1}
    assert batch["latency_all_attempts_ms"]["denominator"] == 1
    assert batch["latency_ms"]["p95"] is None
    assert "secret" not in json.dumps(report)


def test_cloud_config_starts_without_choices_prices_or_spending():
    value = json.loads(
        (REPO / "docs/evaluation/knowledge-expanded/cloud-experiment.json").read_text()
    )
    load_benchmark().validate_cloud_config(value)
    assert value["billable_run_enabled"] is False
    assert value["regions"] == [] and value["models"] == []
    assert value["budget"]["max_total"] is None


@pytest.mark.parametrize("mutation", ["regions", "models", "budget"])
def test_cloud_config_cannot_enable_unbounded_experiment(mutation):
    module = load_benchmark()
    config = {"billable_run_enabled": False, "regions": [], "models": [], "budget": {}}
    if mutation == "budget":
        config["billable_run_enabled"] = True
    else:
        config[mutation] = [{}, {}, {}]
    with pytest.raises(ValueError):
        module.validate_cloud_config(config)


async def test_redirect_response_cannot_forward_authorization_to_another_host():
    module = load_benchmark()

    def handle(request):
        assert request.url.host == "127.0.0.1"
        return httpx.Response(302, headers={"Location": "http://other.example/exfiltrate"})

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8020",
        follow_redirects=True,
        headers={"Authorization": "Bearer unit-private"},
        transport=httpx.MockTransport(handle),
    ) as client:
        with pytest.raises(module.ProbeError, match="http_302"):
            await module.request_json(client, "/health/ready")


def test_benchmark_missing_auth_retains_explicit_not_run_artifact(inputs, monkeypatch):
    module = load_benchmark()
    for key in ("KNOWLEDGE_VERIFY_TOKEN", "KNOWLEDGE_IMPORT_TOKEN", "KNOWLEDGE_SERVICE_KEY"):
        monkeypatch.delenv(key, raising=False)
    output = inputs / "benchmark-result.json"
    result = module.main(
        [
            "--target-test",
            "--manifest",
            str(inputs / "manifest.json"),
            "--queries",
            str(inputs / "dev.jsonl"),
            "--mapping",
            str(inputs / "mapping.json"),
            "--receipts",
            str(inputs / "receipts.json"),
            "--output",
            str(output),
        ]
    )
    assert result != 0
    report = json.loads(output.read_text())
    assert report["status"] == "not_run" and report["batches"] == []
    assert report["error"] == "missing_authentication"


def test_scope_refresh_does_not_change_authorization_or_as_of():
    from datetime import UTC, datetime

    module = load_benchmark()
    original = {
        "as_of": "2026-01-10T00:00:00+00:00",
        "expires_at": "2000-01-01T00:00:00Z",
        "store_id": "S1",
        "allowed_versions": [{"version_id": "V1"}],
    }
    fresh = module.refresh_scope(original)
    assert module.instant(fresh["expires_at"]) > datetime.now(UTC)
    assert fresh["as_of"] == original["as_of"]
    assert fresh["allowed_versions"] == original["allowed_versions"]
    assert original["expires_at"] == "2000-01-01T00:00:00Z"


@pytest.mark.parametrize("revision", [None, 2])
async def test_scope_never_uses_edit_cas_as_evidence_authority(inputs, revision):
    module = load_benchmark()
    data = load_inputs(module, inputs)
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(backend_response)
    ) as backend:
        inventory = await module.live_inventory(data, backend)
    doc = inventory["documents"]["D1"]
    if revision is None:
        del doc["evidence_revision"]
    else:
        doc["evidence_revision"] = revision
    assert module.make_scope(data, inventory, data["queries"][0])["allowed_versions"] == []


async def test_scope_needs_no_edit_cas_when_evidence_revision_is_present(inputs):
    module = load_benchmark()
    data = load_inputs(module, inputs)
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(backend_response)
    ) as backend:
        inventory = await module.live_inventory(data, backend)
    del inventory["documents"]["D1"]["metadata_version"]
    assert module.make_scope(data, inventory, data["queries"][0])["allowed_versions"] == [
        {"version_id": "V1", "generation_id": "G1", "metadata_revision": 1}
    ]


async def test_final_recheck_rejects_missing_evidence_revision_even_if_cas_matches():
    from shopsteward_knowledge.contracts import Candidate

    module = load_benchmark()

    def missing(request):
        reply = backend_response(request).json()
        del reply["evidence_revision"]
        return httpx.Response(200, json=reply)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(missing)
    ) as backend:
        with pytest.raises(module.ProbeError, match="authority_changed"):
            await module.recheck_authority(
                backend,
                [Candidate.model_validate(candidate())],
                {"store_id": "S1", "as_of": "2026-01-10T00:00:00Z"},
            )


async def test_lexical_benchmark_profile_cannot_trigger_configured_model_providers():
    from datetime import UTC, datetime, timedelta

    from shopsteward_knowledge.contracts import SearchRequest
    from shopsteward_knowledge.retrieval.search import SearchService

    calls = []

    class Index:
        async def search(self, request):
            return [candidate()]

    class Provider:
        async def embed(self, *args, **kwargs):
            calls.append("embedding")
            raise AssertionError("lexical must not call a model")

        async def rerank(self, *args, **kwargs):
            calls.append("rerank")
            raise AssertionError("lexical must not call a model")

    service = SearchService(
        Index(),
        embedder=Provider(),
        reranker=Provider(),
        embedding_profile={"provider": "unit", "model": "fixture", "dimensions": 2},
    )
    request = SearchRequest.model_validate(
        {
            "query": "chilled",
            "profile_id": "lexical-v1",
            "scope": {
                "principal_ref": "P1",
                "store_id": "S1",
                "as_of": "2026-01-10T00:00:00Z",
                "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                "allowed_versions": [
                    {"version_id": "V1", "generation_id": "G1", "metadata_revision": 1}
                ],
            },
        }
    )
    await service.search(request)
    assert calls == []
