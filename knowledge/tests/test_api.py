from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from shopsteward_knowledge.api import create_app
from shopsteward_knowledge.config import Settings


def configured_app(**kwargs):
    return create_app(Settings(database_url=None, service_key="test-service-secret"), **kwargs)


def scope():
    now = datetime.now(UTC)
    return {
        "principal_ref": "backend-user",
        "store_id": "store1",
        "as_of": now.isoformat(),
        "expires_at": (now + timedelta(minutes=1)).isoformat(),
        "allowed_versions": [],
    }


def test_no_database_is_live_but_never_ready():
    with TestClient(configured_app()) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert (
            client.get(
                "/internal/v1/jobs/missing", headers={"Authorization": "Bearer test-service-secret"}
            ).status_code
            == 503
        )


def test_unreachable_database_returns_503_without_exception_details():
    class Offline:
        def __call__(self):
            raise ConnectionError("private database host")

    with TestClient(configured_app(session_factory=Offline())) as client:
        response = client.get(
            "/internal/v1/ingestions/job1", headers={"Authorization": "Bearer test-service-secret"}
        )
        assert response.status_code == 503
        assert "private database host" not in response.text


def test_forged_principal_and_missing_service_configuration_are_rejected():
    with TestClient(configured_app()) as client:
        for headers in ({}, {"X-Principal": "admin"}, {"Authorization": "Bearer wrong"}):
            assert (
                client.post(
                    "/internal/v1/search",
                    json={"query": "hello", "scope": scope()},
                    headers=headers,
                ).status_code
                == 401
            )
    with TestClient(create_app(Settings(database_url=None, service_key=None))) as client:
        assert (
            client.post(
                "/internal/v1/search",
                json={"query": "hello", "scope": scope()},
                headers={"Authorization": "Bearer anything"},
            ).status_code
            == 503
        )


def test_search_and_evidence_use_trusted_service_boundary():
    class Retrieval:
        async def search(self, request):
            return {
                "request_id": "request1",
                "retrieval_profile": request.profile_id,
                "candidates": [],
                "warnings": [request.scope.principal_ref],
            }

        async def evidence(self, request):
            return {
                "request_id": "evidence1",
                "retrieval_profile": "evidence-v1",
                "candidates": [],
                "warnings": request.chunk_ids,
            }

    with TestClient(configured_app(search_service=Retrieval())) as client:
        headers = {"Authorization": "Bearer test-service-secret"}
        response = client.post(
            "/internal/v1/search", headers=headers, json={"query": "hello", "scope": scope()}
        )
        assert response.status_code == 200
        assert response.json()["warnings"] == ["backend-user"]
        response = client.post(
            "/internal/v1/evidence",
            headers=headers,
            json={"scope": scope(), "chunk_ids": ["chunk1"]},
        )
        assert response.status_code == 200
        assert response.json()["warnings"] == ["chunk1"]


def test_search_and_evidence_openapi_include_response_contract():
    schema = configured_app().openapi()
    for path in ("/internal/v1/search", "/internal/v1/evidence"):
        response = schema["paths"][path]["post"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/SearchResponse"
        }
    assert "Candidate" in schema["components"]["schemas"]


async def test_retry_route_uses_service_auth_and_backend_receipt_contract(monkeypatch):
    import httpx

    from shopsteward_knowledge.contracts import IngestionReceipt
    from shopsteward_knowledge.ingestion import ConflictError, IngestionService

    received = []

    async def retry(self, job_id, key):
        received.append((job_id, key))
        if job_id == "missing":
            return None
        if job_id == "active":
            raise ConflictError("job is not terminal FAILED")
        return IngestionReceipt(job_id=job_id, state="PENDING", generation_id="g1", attempt=5)

    monkeypatch.setattr(IngestionService, "retry", retry, raising=False)
    app = configured_app(session_factory=object(), blob=object())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = "/internal/v1/ingestions/J1/retry"
        assert (await client.post(path, headers={"Idempotency-Key": "retry-1"})).status_code == 401
        auth = {"Authorization": "Bearer test-service-secret"}
        assert (await client.post(path, headers=auth)).status_code == 422
        headers = {**auth, "Idempotency-Key": "retry-1"}
        response = await client.post(path, headers=headers)
        assert response.status_code == 202
        assert IngestionReceipt.model_validate(response.json()).attempt == 5
        assert received == [("J1", "retry-1")]
        assert (
            await client.post("/internal/v1/ingestions/missing/retry", headers=headers)
        ).status_code == 404
        assert (
            await client.post("/internal/v1/ingestions/active/retry", headers=headers)
        ).status_code == 409


def test_unconfigured_hybrid_and_unknown_profiles_are_rejected():
    with TestClient(configured_app()) as client:
        for profile in ("hybrid-v1", "imaginary-model"):
            response = client.post(
                "/internal/v1/search",
                headers={"Authorization": "Bearer test-service-secret"},
                json={"query": "hello", "scope": scope(), "profile_id": profile},
            )
            assert response.status_code == 422


def test_embedding_settings_require_complete_explicit_configuration(monkeypatch):
    import pytest

    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-secret-must-not-be-read")
    assert Settings().embedding_profile() is None
    with pytest.raises(ValueError, match="complete"):
        Settings(embedding_url="https://embedding.invalid/v1/embeddings")
    settings = Settings(
        embedding_url="https://embedding.invalid/v1/embeddings",
        embedding_api_key="test",
        embedding_model="test-model",
        embedding_dimensions=2,
        embedding_document_instruction="document: ",
    )
    profile = settings.embedding_profile()
    assert profile["model"] == "test-model" and profile["dimensions"] == 2
    assert profile["document_instruction"] == "document: "
    assert "test" not in repr(settings.embedding_api_key)


def test_sqlite_database_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(database_url="sqlite+aiosqlite:///:memory:")


def test_documented_ingestion_receipt_path_and_expired_scope():
    with TestClient(configured_app()) as client:
        headers = {"Authorization": "Bearer test-service-secret"}
        assert client.get("/internal/v1/ingestions/job1", headers=headers).status_code == 503
        expired = scope()
        expired["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        assert (
            client.post(
                "/internal/v1/search", headers=headers, json={"query": "hello", "scope": expired}
            ).status_code
            == 422
        )


def test_relation_intake_requires_evidence_and_trusted_service():
    with TestClient(configured_app()) as client:
        payload = {
            "generation_id": "gen1",
            "metadata_revision": 1,
            "edges": [
                {
                    "subject": "policy",
                    "predicate": "APPLIES_TO",
                    "object": "product",
                    "evidence_chunk_ids": [],
                }
            ],
        }
        assert client.post("/internal/v1/relations", json=payload).status_code == 401
        assert (
            client.post(
                "/internal/v1/relations",
                json=payload,
                headers={"Authorization": "Bearer test-service-secret"},
            ).status_code
            == 422
        )
