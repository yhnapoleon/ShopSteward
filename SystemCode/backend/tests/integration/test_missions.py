import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from test_operations import initial_snapshot, initialize

pytestmark = pytest.mark.integration
TOKENS = {
    role: f"mission-test-{role}-credential-0000000001"
    for role in ["admin", "operator", "viewer", "approver"]
}


def fresh_seed():
    seed = initial_snapshot()
    now = datetime.now(UTC)
    seed["simulation_time"] = now.isoformat()
    seed["initial_state"].update(data_as_of=now.isoformat(), simulation_time=now.isoformat())
    seed["initial_forecast"].update(
        data_as_of=now.isoformat(),
        horizon_start=now.isoformat(),
        horizon_end=(now + timedelta(days=7)).isoformat(),
        valid_until=(now + timedelta(hours=1)).isoformat(),
    )
    for offer in seed["initial_catalog"]["offers"]:
        offer.update(
            valid_from=(now - timedelta(minutes=1)).isoformat(),
            valid_until=(now + timedelta(days=1)).isoformat(),
        )
    return seed


def body(seed):
    return {
        "store_id": seed["store_id"],
        "sku_id": "sku_001",
        "objective": "Cash floor and demand coverage",
        "policy": {
            "cash_floor_minor": 30000,
            "candidate_quantities": [0, 20, 40, 80],
            "supplier_id": "supplier_001",
        },
        "check_interval_seconds": 30,
    }


def headers(role="operator", key=None):
    return {"Authorization": "Bearer " + TOKENS[role], "Idempotency-Key": key or str(uuid4())}


def settings(db, seed, **overrides):
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        app_env="test",
        database_url=db.engine.url.render_as_string(hide_password=False),
        auth_tokens=[
            {"token": token, "principal_id": role, "roles": [role], "store_ids": [seed["store_id"]]}
            for role, token in TOKENS.items()
        ],
        **overrides,
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_queue(db):
    async with db.session() as session, session.begin():
        await session.execute(text("DELETE FROM job_runs"))


@asynccontextmanager
async def environment(db):
    from app.main import create_app
    from app.operations.repository import mark_caught_up

    seed = fresh_seed()
    await initialize(db, seed)
    async with db.session() as session, session.begin():
        await mark_caught_up(session, seed["scenario_run_id"], 0)
    app = create_app(settings(db, seed))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield seed, client


async def test_create_replay_unique_active_scope_and_persistent_initial_check(db):
    async with environment(db) as (seed, client):
        key = str(uuid4())
        first = await client.post("/api/v1/missions", json=body(seed), headers=headers(key=key))
        assert first.status_code == 201, first.text
        mission = first.json()
        assert mission["status"] == "ACTIVE" and mission["mission_version"] == 1
        assert (
            mission["schedule"]["enabled"] is True
            and mission["schedule"]["next_run_at"] is not None
        )
        replay = await client.post("/api/v1/missions", json=body(seed), headers=headers(key=key))
        assert replay.json() == mission
        altered = body(seed)
        altered["objective"] = "changed"
        assert (
            await client.post("/api/v1/missions", json=altered, headers=headers(key=key))
        ).status_code == 409
        assert (
            await client.post("/api/v1/missions", json=body(seed), headers=headers())
        ).status_code == 409
        async with db.session() as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM job_runs WHERE mission_id=:id"),
                    {"id": mission["id"]},
                )
                == 1
            )


async def test_roles_store_visibility_and_control_version_lifecycle(db):
    async with environment(db) as (seed, client):
        assert (
            await client.post("/api/v1/missions", json=body(seed), headers=headers("viewer"))
        ).status_code == 403
        wrong = body(seed)
        wrong["store_id"] = "another-store"
        assert (
            await client.post("/api/v1/missions", json=wrong, headers=headers())
        ).status_code == 404
        mission = (await client.post("/api/v1/missions", json=body(seed), headers=headers())).json()
        url = f"/api/v1/missions/{mission['id']}/control"
        pause = {"operation": "pause", "expected_mission_version": 1}
        paused = await client.post(url, json=pause, headers=headers())
        assert paused.status_code == 200 and paused.json()["status"] == "PAUSED"
        assert (await client.post(url, json=pause, headers=headers())).status_code == 409
        assert (
            await client.post(
                f"/api/v1/missions/{mission['id']}/checks", json={}, headers=headers()
            )
        ).status_code == 409
        resumed = await client.post(
            url, json={"operation": "resume", "expected_mission_version": 2}, headers=headers()
        )
        assert resumed.json()["mission_version"] == 3
        complete = {"operation": "complete", "expected_mission_version": 3}
        assert (await client.post(url, json=complete, headers=headers())).status_code == 403
        assert (await client.post(url, json=complete, headers=headers("approver"))).json()[
            "status"
        ] == "COMPLETED"
        assert (
            await client.post(
                url, json={"operation": "resume", "expected_mission_version": 4}, headers=headers()
            )
        ).status_code == 409


async def test_concurrent_create_and_manual_check_merge(db):
    async with environment(db) as (seed, client):
        responses = await asyncio.gather(
            *(client.post("/api/v1/missions", json=body(seed), headers=headers()) for _ in range(3))
        )
        assert sorted(r.status_code for r in responses) == [201, 409, 409]
        mission = next(r.json() for r in responses if r.status_code == 201)
        url = f"/api/v1/missions/{mission['id']}/checks"
        checks = await asyncio.gather(
            *(client.post(url, json={"reason": "manual"}, headers=headers()) for _ in range(3))
        )
        assert all(r.status_code == 202 for r in checks)
        assert len({r.json()["job_run_id"] for r in checks}) == 1
        assert all(r.json()["merged"] for r in checks)


async def test_mission_cursor_is_bound_to_filters_and_pagination_is_stable(db):
    async with environment(db) as (seed, client):
        for _ in range(3):
            mission = (
                await client.post("/api/v1/missions", json=body(seed), headers=headers())
            ).json()
            await client.post(
                f"/api/v1/missions/{mission['id']}/control",
                json={"operation": "cancel", "expected_mission_version": 1},
                headers=headers("approver"),
            )
        params = {"store_id": seed["store_id"], "limit": 2}
        page = (
            await client.get("/api/v1/missions", params=params, headers=headers("viewer"))
        ).json()
        assert len(page["items"]) == 2 and page["next_cursor"]
        second = (
            await client.get(
                "/api/v1/missions",
                params=params | {"cursor": page["next_cursor"]},
                headers=headers("viewer"),
            )
        ).json()
        assert len(second["items"]) == 1 and second["next_cursor"] is None
        assert not {m["id"] for m in page["items"]} & {m["id"] for m in second["items"]}
        invalid = await client.get(
            "/api/v1/missions",
            params=params | {"status": "ACTIVE", "cursor": page["next_cursor"]},
            headers=headers("viewer"),
        )
        assert invalid.status_code == 422
