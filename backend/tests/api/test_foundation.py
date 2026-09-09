import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

ADMIN = "test-admin-token-000000000000000001"
VIEWER = "test-viewer-token-00000000000000001"
SERVICE = "test-service-token-0000000000000001"

K2_ROUTES = {
    "/api/v1/documents/{document_id}/versions/{version_id}/index-jobs": (
        "post",
        "request_knowledge_index",
        "202",
    ),
    "/api/v1/documents/{document_id}/index-jobs/{request_id}": (
        "get",
        "get_knowledge_index",
        "200",
    ),
    "/api/v1/documents/{document_id}/index-jobs/{request_id}/retry": (
        "post",
        "retry_knowledge_index",
        "202",
    ),
    "/api/v1/documents/{document_id}/publications": (
        "post",
        "publish_knowledge_generation",
        "200",
    ),
}


def make_app(**overrides):
    from app.core.config import Settings
    from app.main import create_app

    options = {
        "app_env": "test",
        "database_url": None,
        "auth_tokens": [
            {"token": ADMIN, "principal_id": "admin", "kind": "user", "roles": ["admin"]},
            {
                "token": VIEWER,
                "principal_id": "viewer",
                "kind": "user",
                "roles": ["viewer"],
                "store_ids": ["store_a"],
            },
            {"token": SERVICE, "principal_id": "agent", "kind": "service", "roles": ["admin"]},
        ],
        **overrides,
    }
    return create_app(Settings(_env_file=None, **options))


@asynccontextmanager
async def client_for(app):
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def assert_design(schema_name, value):
    path = Path(__file__).resolve().parents[3] / "docs/api/backend.openapi.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(
        {"$ref": f"#/components/schemas/{schema_name}", "components": document["components"]},
        format_checker=FormatChecker(),
    ).validate(value)


async def test_liveness_does_not_require_database_and_returns_request_id():
    async with client_for(make_app()) as client:
        response = await client.get("/health/live", headers={"X-Request-ID": "incoming-123"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "component": "backend"}
        assert response.headers["x-request-id"]
        assert_design("Health", response.json())


async def test_readiness_is_unavailable_without_database_configuration():
    async with client_for(make_app()) as client:
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "unavailable"
        assert_design("Health", response.json())


@pytest.mark.parametrize(
    "token,status,code",
    [
        (None, 401, "UNAUTHENTICATED"),
        ("invalid", 401, "UNAUTHENTICATED"),
        (VIEWER, 403, "FORBIDDEN"),
        (SERVICE, 403, "FORBIDDEN"),
    ],
)
async def test_monitoring_requires_actual_user_admin(token, status, code):
    async with client_for(make_app()) as client:
        response = await client.get(
            "/api/v1/monitoring/status",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
        assert_design("Error", response.json())


async def test_admin_sees_dependency_error_without_credentials_or_traceback():
    async with client_for(make_app()) as client:
        response = await client.get(
            "/api/v1/monitoring/status", headers={"Authorization": f"Bearer {ADMIN}"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
        assert ADMIN not in response.text
        assert_design("Error", response.json())


async def test_invalid_job_id_uses_uniform_422_without_echoing_authorization():
    async with client_for(make_app()) as client:
        response = await client.get(
            "/api/v1/job-runs/" + "x" * 129, headers={"Authorization": f"Bearer {ADMIN}"}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert ADMIN not in response.text
        assert_design("Error", response.json())


async def test_runtime_schema_registers_only_implemented_routes_and_auth():
    app = make_app()
    schema = app.openapi()  # Must not connect to a database.
    assert set(schema["paths"]) == {
        "/api/v1/me",
        "/api/v1/stores",
        "/api/v1/sales",
        "/api/v1/sales/summary",
        "/api/v1/actions",
        "/api/v1/inbounds",
        "/api/v1/ledger-entries",
        "/health/live",
        "/health/ready",
        "/api/v1/monitoring/status",
        "/api/v1/job-runs/{job_run_id}",
        "/api/v1/catalog",
        "/internal/v1/events/batches",
        "/dev/v1/scenarios",
        "/api/v1/missions",
        "/api/v1/missions/{mission_id}",
        "/api/v1/missions/{mission_id}/control",
        "/api/v1/missions/{mission_id}/schedule",
        "/api/v1/missions/{mission_id}/checks",
        "/api/v1/missions/{mission_id}/plans",
        "/api/v1/plans/{plan_id}",
        "/api/v1/plans/{plan_id}/decision",
        "/api/v1/plans/{plan_id}/revision",
        "/api/v1/actions/{action_id}",
        "/dev/v1/scenarios/{run_id}/advance",
        "/api/v1/dashboard",
        "/api/v1/alerts",
        "/api/v1/alerts/{alert_id}/acknowledgement",
        "/api/v1/missions/{mission_id}/timeline",
        "/api/v1/missions/{mission_id}/conversations",
        "/api/v1/conversations/{conversation_id}/messages",
        "/api/v1/conversations/{conversation_id}/followup",
        "/api/v1/agent-runs/{run_id}",
        "/api/v1/agent-runs/{run_id}/events",
        "/api/v1/agent-runs/{run_id}/evidence",
        "/api/v1/agent-runs/{run_id}/events/stream",
        "/api/v1/agent-runs/{run_id}/resume",
        "/api/v1/agent-runs/{run_id}/cancel",
        "/api/v1/stores/{store_id}/agent-knowledge",
        "/internal/v1/agent-tools/{tool_name}",
        "/api/v1/stores/{store_id}/documents",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/versions",
        "/api/v1/documents/{document_id}/versions/{version_id}",
        "/api/v1/documents/{document_id}/versions/{version_id}/content",
        "/api/v1/documents/{document_id}/control",
        "/api/v1/work-items",
        "/api/v1/work-items/{item_id}",
        "/api/v1/work-items/{item_id}/messages",
        "/api/v1/work-items/{item_id}/mission",
        "/api/v1/work-items/{item_id}/control",
        "/api/v1/missions/{mission_id}/work-item",
        "/internal/v1/work-items",
        "/internal/v1/work-items/{item_id}/claim",
        "/internal/v1/work-items/{item_id}/context",
        "/internal/v1/work-items/{item_id}/updates",
        *K2_ROUTES,
    }
    assert schema["paths"]["/api/v1/monitoring/status"]["get"]["security"] == [{"UserBearer": []}]
    for path, (method, operation_id, success_status) in K2_ROUTES.items():
        assert set(schema["paths"][path]) == {method}
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["security"] == [{"UserBearer": []}]
        assert {s for s in operation["responses"] if s.startswith("2")} == {success_status}
    async with client_for(app) as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/api/v1/agent-runs/anything")).status_code == 401


async def test_production_default_hides_docs():
    async with client_for(make_app(app_env="production")) as client:
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404


async def test_all_runtime_operations_have_phase_and_implementation_metadata():
    for environment in ("development", "production"):
        schema = make_app(app_env=environment).openapi()
        assert set(K2_ROUTES) <= schema["paths"].keys()
        for path, item in schema["paths"].items():
            for method, operation in item.items():
                if method not in {"get", "post", "patch"}:
                    continue
                if path in K2_ROUTES:
                    assert method == K2_ROUTES[path][0], (method, path)
                    assert operation.get("x-phase") == "K2", (method, path)
                else:
                    assert operation.get("x-phase") in {"B0", "B2-A", "K1"}, (method, path)
                assert operation.get("x-implementation-status") == "implemented", (method, path)


@pytest.mark.parametrize(
    "options",
    [
        {"job_lease_seconds": 10, "job_heartbeat_seconds": 10},
        {"worker_concurrency": 0},
        {"database_url": "sqlite:///test.db"},
        {
            "auth_tokens": [
                {"token": ADMIN, "principal_id": "a"},
                {"token": ADMIN, "principal_id": "b"},
            ]
        },
    ],
)
async def test_invalid_configuration_is_rejected_before_serving(options):
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **options)


async def test_cors_allows_configured_origin_and_exposes_request_id():
    async with client_for(make_app(cors_origins=["http://localhost:3000"])) as client:
        response = await client.options(
            "/api/v1/monitoring/status",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,idempotency-key",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        response = await client.get("/health/live", headers={"Origin": "http://localhost:3000"})
        assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


async def test_non_ascii_invalid_bearer_is_unauthenticated_not_server_error():
    app = make_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/monitoring/status", headers={"Authorization": b"Bearer \xffinvalid"}
            )
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_catalog_checks_store_scope_before_opening_database():
    async with client_for(make_app()) as client:
        headers = {"Authorization": f"Bearer {VIEWER}"}
        assert (
            await client.get("/api/v1/catalog", params={"store_id": "store_b"}, headers=headers)
        ).status_code == 404
        assert (
            await client.get("/api/v1/catalog", params={"store_id": "store_a"}, headers=headers)
        ).status_code == 503


async def test_business_payload_rejects_coerced_money_and_quantities():
    from app.operations.schemas import SalePayload

    for value in [1.2, True, "2", -1, 0]:
        with pytest.raises(ValidationError):
            SalePayload(sku_id="sku", quantity=value, unit_price_minor=2000)
        with pytest.raises(ValidationError):
            SalePayload(sku_id="sku", quantity=1, unit_price_minor=value)


def test_embedded_upload_provenance_keeps_constraints_without_orphan_refs():
    schema = make_app().openapi()
    metadata = schema["paths"]["/api/v1/stores/{store_id}/documents"]["post"]["requestBody"][
        "content"
    ]["multipart/form-data"]["schema"]["properties"]["metadata"]["contentSchema"]
    validator = Draft202012Validator(metadata)
    validator.validate({"title": "Example", "provenance": {"synthetic": True}})
    assert list(validator.iter_errors({"title": "Example", "provenance": {"synthetic": "yes"}}))
    assert "#/$defs/" not in json.dumps(metadata)


async def test_intake_capabilities_remain_available_with_production_docs_disabled():
    async with client_for(make_app(app_env="production")) as client:
        assert (await client.get("/openapi.json")).status_code == 404
        response = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + VIEWER})
        assert response.status_code == 200
        assert set(response.json()["capabilities"]) == {"work_intake", "plan_revision"}
