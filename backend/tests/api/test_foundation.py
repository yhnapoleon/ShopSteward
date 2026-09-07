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
        "/api/v1/actions/{action_id}",
        "/dev/v1/scenarios/{run_id}/advance",
        "/api/v1/dashboard",
        "/api/v1/alerts",
        "/api/v1/alerts/{alert_id}/acknowledgement",
        "/api/v1/missions/{mission_id}/timeline",
    }
    assert schema["paths"]["/api/v1/monitoring/status"]["get"]["security"] == [{"UserBearer": []}]
    async with client_for(app) as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/api/v1/agent-runs/anything")).status_code == 404


async def test_production_default_hides_docs():
    async with client_for(make_app(app_env="production")) as client:
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404


async def test_all_runtime_operations_have_phase_and_implementation_metadata():
    for environment in ("development", "production"):
        schema = make_app(app_env=environment).openapi()
        for path, item in schema["paths"].items():
            for method, operation in item.items():
                if method not in {"get", "post", "patch"}:
                    continue
                assert operation.get("x-phase") == "B0", (method, path)
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
