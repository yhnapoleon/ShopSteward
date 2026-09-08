import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from test_benchmark import (
    backend_response,
    candidate,
    load_benchmark,
    load_inputs,
    service_response,
)
from test_benchmark import inputs as inputs

REPO = Path(__file__).resolve().parents[2]


def verifier():
    spec = importlib.util.spec_from_file_location(
        "precloud_verifier", REPO / "backend/tools/verify_knowledge_precloud.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def knowledge_response(request):
    if request.url.path == "/health/ready":
        return httpx.Response(200, json={"status": "ready"})
    body = json.loads(request.content)
    scope = body["scope"]
    hits = [candidate()]
    if (
        not scope["allowed_versions"]
        or scope["store_id"] != "S1"
        or body.get("query", "").startswith("precloudnomatch")
    ):
        hits = []
    reply = service_response(hits)
    if request.url.path.endswith("/evidence"):
        reply["retrieval_profile"] = "evidence-v1"
    return httpx.Response(200, json=reply)


async def test_http_checks_cannot_substitute_for_build_restore_or_agent(inputs):
    data = load_inputs(load_benchmark(), inputs)
    data["receipts"]["checks"] = dict.fromkeys(
        ["build", "restore", "versioning", "agent_tools", "corpus_200"], "passed"
    )
    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(backend_response)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(knowledge_response)
        ) as service,
    ):
        report = await verifier().verify_precloud(data, backend, service)
    assert report["checks"]["real_http"] == "passed"
    assert all(
        report["checks"][k] == "not_run" for k in ["build", "restore", "agent_tools", "versioning"]
    )
    assert report["pilot_ready"] is False and report["MVP_ready"] is False
    assert report["checks"]["corpus_200"] != "passed"
    assert report["scenarios"]["worker_restart"]["status"] == "not_run"


async def test_unavailable_real_http_is_a_failure_not_mocked_fallback(inputs):
    data = load_inputs(load_benchmark(), inputs)

    def down(request):
        raise httpx.ConnectError("private-token", request=request)

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(down)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(down)
        ) as service,
    ):
        report = await verifier().verify_precloud(data, backend, service)
    assert report["checks"]["real_http"] == "failed"
    assert report["pilot_ready"] is False
    assert "private-token" not in json.dumps(report)


async def test_changed_original_bytes_fail_live_corpus_verification(inputs):
    data = load_inputs(load_benchmark(), inputs)

    def corrupt(request):
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=b"Wrong bytes!!")
        return backend_response(request)

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(corrupt)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(knowledge_response)
        ) as service,
    ):
        report = await verifier().verify_precloud(data, backend, service)
    assert report["checks"]["corpus_200"] == "failed"
    assert report["scenarios"]["original_integrity"]["status"] == "failed"


async def test_evidence_hash_or_scope_violation_fails_http_acceptance(inputs):
    data = load_inputs(load_benchmark(), inputs)

    def wrong(request):
        if request.url.path.endswith("/evidence"):
            hit = candidate()
            hit["generation_id"] = "OLD"
            return httpx.Response(200, json=service_response([hit]))
        return knowledge_response(request)

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(backend_response)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(wrong)
        ) as service,
    ):
        report = await verifier().verify_precloud(data, backend, service)
    assert report["checks"]["real_http"] == "failed"
    assert report["scenarios"]["evidence_integrity"]["status"] == "failed"


async def test_bundle_verification_delegates_generation_identity_to_adapter(monkeypatch):
    from test_bundle import ready_snapshot

    from shopsteward_knowledge.bundle import rebuild_lexical
    from shopsteward_knowledge.retrieval import opensearch

    verified = []

    class Index:
        def __init__(self, *args):
            pass

        async def upsert(self, generation, chunks):
            pass

        async def count(self, generation):
            return 1

        async def verify_generation(self, generation, chunks):
            verified.append((generation, chunks[0]["chunk_id"]))
            return True

        def index_name(self, generation):
            pytest.fail("bundle must not assume generation index layout or raw chunk IDs")

    original = httpx.AsyncClient
    monkeypatch.setattr(opensearch, "OpenSearchIndex", Index)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])), **kw
        ),
    )
    assert (
        await rebuild_lexical(
            ready_snapshot(), "http://localhost:19201", "shopsteward-restore-test-c3"
        )
        == 1
    )
    assert verified == [("G1", "C1")]


@pytest.mark.parametrize("configured", [False, True])
def test_compose_embedding_configuration_matches_settings_and_blank_disables(tmp_path, configured):
    import os
    import subprocess
    import sys

    from test_bundle import load_local

    local = load_local()
    env_file = tmp_path / "private.env"
    values = {
        "KNOWLEDGE_SERVICE_KEY": "unit-private",
        "KNOWLEDGE_POSTGRES_PASSWORD": "unit-private",
        "KNOWLEDGE_EMBEDDING_URL": "",
        "KNOWLEDGE_EMBEDDING_API_KEY": "",
        "KNOWLEDGE_EMBEDDING_MODEL": "",
        "KNOWLEDGE_EMBEDDING_DIMENSIONS": "",
        "KNOWLEDGE_EMBEDDING_QUERY_INSTRUCTION": "",
        "KNOWLEDGE_EMBEDDING_DOCUMENT_INSTRUCTION": "",
        "KNOWLEDGE_RERANK_URL": "",
        "KNOWLEDGE_RERANK_API_KEY": "",
        "KNOWLEDGE_RERANK_MODEL": "",
    }
    if configured:
        values.update(
            KNOWLEDGE_EMBEDDING_URL="http://127.0.0.1:8999/embeddings",
            KNOWLEDGE_EMBEDDING_API_KEY="unit-private",
            KNOWLEDGE_EMBEDDING_MODEL="fixture",
            KNOWLEDGE_EMBEDDING_DIMENSIONS="2",
            KNOWLEDGE_EMBEDDING_QUERY_INSTRUCTION="Query: ",
            KNOWLEDGE_EMBEDDING_DOCUMENT_INSTRUCTION="Document: ",
            KNOWLEDGE_RERANK_URL="http://127.0.0.1:8999/rerank",
            KNOWLEDGE_RERANK_API_KEY="unit-private",
            KNOWLEDGE_RERANK_MODEL="fixture",
        )
    env_file.write_text("\n".join(f'{key}="{value}"' for key, value in values.items()))
    manager = local.Manager(env_file=env_file, state_dir=tmp_path)
    config = json.loads(manager.compose("config", "--format", "json"))
    service = config["services"]["api"]
    assert "KNOWLEDGE_EMBEDDING_URL" in service["environment"]
    assert "KNOWLEDGE_RERANK_URL" in service["environment"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("KNOWLEDGE_")}
    env.update({k: str(v) for k, v in service["environment"].items()})
    env["PYTHONPATH"] = str(REPO / "knowledge/src")
    check = (
        "import json,os; from shopsteward_knowledge.config import Settings; "
        "s=Settings(); p=s.embedding_profile(); "
        'print(json.dumps({"enabled":p is not None,"profiles":sorted(s.enabled_profiles()),'
        '"rerank_configured":bool(os.getenv("KNOWLEDGE_RERANK_URL")),'
        '"query_instruction":p["query_instruction"] if p else None}))'
    )
    command = service["entrypoint"]
    # Execute the real container entrypoint normalization. Windows has no POSIX
    # process replacement; adapt only execvp to a waited, correctly quoted child.
    driver = (
        "import os,sys,subprocess; "
        "os.execvp=lambda executable,args: subprocess.run(args,check=True); "
        "code=sys.argv[1]; sys.argv=sys.argv[1:]; exec(code)"
    )
    result = subprocess.run(
        [sys.executable, "-c", driver, command[2], sys.executable, "-c", check],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["enabled"] is configured
    assert ("hybrid-v1" in output["profiles"]) is configured
    assert output["query_instruction"] == ("Query: " if configured else None)
    assert output["rerank_configured"] is configured


def test_cli_missing_auth_writes_not_run_report_and_nonzero_exit(inputs, monkeypatch, capsys):
    for key in ("KNOWLEDGE_VERIFY_TOKEN", "KNOWLEDGE_IMPORT_TOKEN", "KNOWLEDGE_SERVICE_KEY"):
        monkeypatch.delenv(key, raising=False)
    output = inputs / "report.json"
    result = verifier().main(
        [
            "--target-test",
            "--manifest",
            str(inputs / "manifest.json"),
            "--root",
            str(inputs),
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
    assert set(report["checks"].values()) == {"not_run"}
    assert report["execution_error"] == "missing_authentication"
    assert report["pilot_ready"] is False


async def test_final_authority_change_during_http_prevents_evidence_pass(inputs):
    data = load_inputs(load_benchmark(), inputs)
    reads = 0

    def changed(request):
        nonlocal reads
        response = backend_response(request)
        if request.url.path == "/api/v1/documents/D1":
            reads += 1
            if reads > 1:
                return httpx.Response(200, json=response.json() | {"evidence_revision": 2})
        return response

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(changed)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(knowledge_response)
        ) as service,
    ):
        report = await verifier().verify_precloud(data, backend, service)
    assert report["checks"]["real_http"] == "failed"
    assert report["scenarios"]["evidence_integrity"]["error"] == "authority_changed"


async def test_append_cas_bump_does_not_invalidate_current_published_evidence(inputs):
    data = load_inputs(load_benchmark(), inputs)

    def appended(request):
        response = backend_response(request)
        if request.url.path == "/api/v1/documents/D1":
            return httpx.Response(
                200,
                json=response.json()
                | {"metadata_version": 3, "evidence_revision": 1, "latest_version_id": "V2"},
            )
        return response

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8018", transport=httpx.MockTransport(appended)
        ) as backend,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8020", transport=httpx.MockTransport(knowledge_response)
        ) as service,
    ):
        report = await verifier().verify_precloud(data, backend, service)
    assert report["scenarios"]["evidence_integrity"]["status"] == "passed"
    assert report["checks"]["real_http"] == "passed"
