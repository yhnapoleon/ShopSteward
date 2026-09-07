"""Local developer console does not expose service credentials or cross-site writes."""

from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from test_bootstrap import TOKEN, settings

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def console_client(enabled=True, peer="127.0.0.1"):
    from simulator.main import create_app

    configured = settings().model_copy(update={"sim_console_enabled": enabled})
    app = create_app(configured)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(peer, 123)),
            base_url="http://127.0.0.1:8001",
            headers={"X-Simulator-Console": "1"},
        ) as client,
    ):
        yield client


async def test_console_creates_persistent_data_without_service_token_in_browser():
    async with console_client() as client:
        status = await client.get("/console/api/status")
        assert status.status_code == 200, status.text
        assert status.json()["simulator_ready"] is True
        assert TOKEN not in status.text
        r = await client.post(
            "/console/api/runs",
            json={"scenario": "SANDBOX"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert r.status_code == 201, r.text
        run_id = r.json()["scenario_run_id"]
        changed = await client.post(
            f"/console/api/runs/{run_id}/triggers",
            json={"kind": "sale", "expected_sequence": 0, "quantity": 2, "unit_price_minor": 2000},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert changed.status_code == 200, changed.text
    async with console_client() as client:
        d = (await client.get(f"/console/api/runs/{run_id}")).json()
        assert d["state"]["stocks"][0]["on_hand"] == 18
        assert d["state"]["receivables_minor"] == 4000
        assert TOKEN not in str(d)
        assert (await client.get(f"/console/api/runs/{run_id}/backend")).json()[
            "status"
        ] == "not_configured"


async def test_console_is_disabled_by_default_and_remote_peers_cannot_use_it():
    async with console_client(enabled=False) as client:
        assert (await client.get("/console/api/status")).status_code == 404
    async with console_client(peer="192.0.2.5") as client:
        assert (await client.get("/console/api/status")).status_code == 403


async def test_console_blocks_cross_site_and_unmarked_mutations():
    async with console_client() as client:
        for headers in [
            {"Host": "attacker.example"},
            {"Origin": "https://attacker.example"},
            {"Sec-Fetch-Site": "cross-site"},
            {"X-Simulator-Console": ""},
        ]:
            r = await client.post(
                "/console/api/runs",
                json={"scenario": "SANDBOX"},
                headers={"Idempotency-Key": str(uuid4()), **headers},
            )
            assert r.status_code == 403, r.text
        assert (
            await client.post("/console/api/runs", json={"scenario": "SANDBOX"})
        ).status_code == 422
        assert (
            await client.get("/console/api/status", headers={"Origin": "https://attacker.example"})
        ).status_code == 403


async def test_backend_create_contract_accepts_sandbox_without_changing_legacy_payload():
    import sys
    from pathlib import Path

    from pydantic import ValidationError

    sys.path.insert(0, str(Path(__file__).parents[2] / "backend"))
    from app.operations.schemas import ScenarioCreate

    assert ScenarioCreate(scenario="SC01").model_dump(exclude_none=True) == {"scenario": "SC01"}
    body = ScenarioCreate(scenario="SANDBOX", parameters={"cash_minor": 50000})
    assert body.parameters.cash_minor == 50000
    with pytest.raises(ValidationError):
        ScenarioCreate(scenario="SC01", parameters={"cash_minor": 50000})
