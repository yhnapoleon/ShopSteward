import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from jsonschema import Draft202012Validator
from sqlalchemy.engine import make_url

TOKEN = "simulator-test-credential-00000001"
pytestmark = pytest.mark.asyncio


def settings():
    from simulator.config import Settings

    url = os.environ.get("TEST_SIM_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_SIM_DATABASE_URL to the migrated simulator test database")
    assert make_url(url).database == "shopsteward_sim_test"
    return Settings(_env_file=None, sim_database_url=url, sim_service_token=TOKEN)


def validate_response(value, path, method, code):
    doc = json.loads(
        (Path(__file__).parents[2] / "docs/api/services.openapi.json").read_text(encoding="utf-8")
    )
    schema = doc["paths"][path][method]["responses"][str(code)]["content"]["application/json"][
        "schema"
    ]
    Draft202012Validator(schema | {"components": doc["components"]}).validate(value)


async def test_create_replays_original_snapshot_across_app_instances_and_checks_auth():
    from simulator.main import create_app

    configured = settings()
    key = str(uuid4())
    bodies = []
    for _ in range(2):
        app = create_app(configured)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://sim"
            ) as client,
        ):
            assert (await client.post("/sim/v1/runs", json={"scenario": "SC01"})).status_code == 401
            response = await client.post(
                "/sim/v1/runs",
                json={"scenario": "SC01"},
                headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key},
            )
            assert response.status_code == 201, response.text
            validate_response(response.json(), "/sim/v1/runs", "post", 201)
            bodies.append(response.json())
            paths = (await client.get("/openapi.json")).json()["paths"]
            assert "/sim/v1/purchases" in paths
    assert bodies[0] == bodies[1]
    assert bodies[0]["initial_state"]["cash_minor"] == 100000


async def test_event_page_empty_ahead_cursor_and_pagination():
    from simulator.main import create_app
    from simulator.models import EventRow, Run

    app = create_app(settings())
    headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": str(uuid4())}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://sim", headers=headers
        ) as client,
    ):
        seed = (await client.post("/sim/v1/runs", json={"scenario": "SC01"})).json()
        run_id = seed["scenario_run_id"]
        path = f"/sim/v1/runs/{run_id}/events"
        empty = await client.get(path, params={"after_sequence": 0})
        assert empty.json() == {
            "events": [],
            "last_sequence": 0,
            "source_head_sequence": 0,
            "has_more": False,
        }
        assert (await client.get(path, params={"after_sequence": 1})).status_code == 409
        assert (await client.get(path, params={"after_sequence": 1})).json()["error"][
            "code"
        ] == "EVENT_CURSOR_AHEAD"
        # Seed source facts in the isolated test DB; this is not an exposed simulator mutation API.
        async with app.state.db.session() as session, session.begin():
            run = await session.get(Run, run_id, with_for_update=True)
            run.last_sequence = 2
            for sequence in [1, 2]:
                session.add(
                    EventRow(
                        run_id=run_id,
                        sequence=sequence,
                        event_id=str(uuid4()),
                        document={
                            "event_id": f"test-{sequence}",
                            "sequence": sequence,
                            "schema_version": "1.0",
                            "event_type": "SALE_RECORDED",
                            "store_id": seed["store_id"],
                            "occurred_at": seed["simulation_time"],
                            "simulation_time": seed["simulation_time"],
                            "payload": {
                                "sku_id": "sku_001",
                                "quantity": 1,
                                "unit_price_minor": 2000,
                            },
                        },
                    )
                )
        page = (await client.get(path, params={"after_sequence": 0, "limit": 1})).json()
        validate_response(page, "/sim/v1/runs/{run_id}/events", "get", 200)
        assert (page["last_sequence"], page["source_head_sequence"], page["has_more"]) == (
            1,
            2,
            True,
        )
        final = (await client.get(path, params={"after_sequence": 1})).json()
        assert final["last_sequence"] == 2 and final["has_more"] is False
        replay = await client.post("/sim/v1/runs", json={"scenario": "SC01"})
        assert replay.json() == seed
