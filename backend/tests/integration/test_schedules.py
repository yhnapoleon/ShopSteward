import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_missions import body, environment, headers

from app.scheduling.models import Job

pytestmark = pytest.mark.integration


async def database_time(db):
    async with db.session() as session:
        return await session.scalar(select(func.clock_timestamp()))


async def create(client, seed):
    response = await client.post("/api/v1/missions", json=body(seed), headers=headers())
    assert response.status_code == 201, response.text
    return response.json()


def patch_body(version=1, interval=60, enabled=True):
    return {
        "interval_seconds": interval,
        "enabled": enabled,
        "expected_schedule_version": version,
    }


async def test_new_mission_schedule_is_due_one_interval_after_creation(db):
    async with environment(db) as (seed, client):
        before = await database_time(db)
        mission = await create(client, seed)
        after = await database_time(db)
        schedule = mission["schedule"]
        assert schedule["enabled"] is True
        assert schedule["version"] == 1
        due = datetime.fromisoformat(schedule["next_run_at"])
        assert before + timedelta(seconds=30) <= due <= after + timedelta(seconds=30)


async def test_schedule_patch_reanchors_without_mutating_running_check_and_replays_exactly(db):
    async with environment(db) as (seed, client):
        mission = await create(client, seed)
        url = f"/api/v1/missions/{mission['id']}/schedule"
        async with db.session() as session, session.begin():
            job = await session.scalar(select(Job).where(Job.mission_id == mission["id"]))
            job.status = "RUNNING"
            job.lease_token = str(uuid4())
            job.lease_until = await database_time(db) + timedelta(seconds=30)
            running = {
                field: getattr(job, field)
                for field in (
                    "id",
                    "status",
                    "lease_token",
                    "lease_until",
                    "scheduled_for",
                    "payload",
                )
            }
        key = str(uuid4())
        before = await database_time(db)
        first = await client.patch(url, json=patch_body(), headers=headers(key=key))
        after = await database_time(db)
        assert first.status_code == 200, first.text
        schedule = first.json()
        assert schedule["mission_id"] == mission["id"] and schedule["version"] == 2
        assert schedule["interval_seconds"] == 60 and schedule["enabled"] is True
        due = datetime.fromisoformat(schedule["next_run_at"])
        assert before + timedelta(seconds=60) <= due <= after + timedelta(seconds=60)
        changed = await client.patch(url, json=patch_body(2, 5, False), headers=headers())
        assert changed.status_code == 200, changed.text
        assert changed.json()["next_run_at"] is None
        replay = await client.patch(url, json=patch_body(), headers=headers(key=key))
        assert replay.status_code == 200 and replay.json() == schedule
        assert (
            await client.patch(url, json=patch_body(interval=90), headers=headers(key=key))
        ).status_code == 409
        stale = await client.patch(url, json=patch_body(), headers=headers())
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "SCHEDULE_VERSION_CONFLICT"
        current = (await client.get(url.removesuffix("/schedule"), headers=headers())).json()
        assert current["schedule"] == changed.json()
        assert current["mission_version"] == 1
        async with db.session() as session:
            job = await session.get(Job, running["id"])
            assert {field: getattr(job, field) for field in running} == running


async def test_schedule_patch_requires_operator_and_current_store_visibility_on_replay(db):
    async with environment(db) as (seed, client):
        mission = await create(client, seed)
        url = f"/api/v1/missions/{mission['id']}/schedule"
        assert (await client.patch(url, json=patch_body())).status_code == 401
        for role in ("viewer", "approver"):
            assert (
                await client.patch(url, json=patch_body(), headers=headers(role))
            ).status_code == 403
        assert (
            await client.patch(
                "/api/v1/missions/missing/schedule", json=patch_body(), headers=headers()
            )
        ).status_code == 404
        key = str(uuid4())
        assert (
            await client.patch(url, json=patch_body(), headers=headers(key=key))
        ).status_code == 200
        app = client._transport.app
        operator = next(g for g in app.state.settings.auth_tokens if g.principal_id == "operator")
        operator.store_ids = []
        assert (
            await client.patch(url, json=patch_body(), headers=headers(key=key))
        ).status_code == 404


async def test_schedule_patch_rejects_invalid_contract_and_serializes_versions(db):
    async with environment(db) as (seed, client):
        mission = await create(client, seed)
        url = f"/api/v1/missions/{mission['id']}/schedule"
        invalid = [patch_body(interval=x) for x in (4, 3601, 5.5, True, "30")]
        invalid += [patch_body() | {"enabled": "false"}, patch_body(0)]
        invalid += [{k: v for k, v in patch_body().items() if k != field} for field in patch_body()]
        for payload in invalid:
            response = await client.patch(url, json=payload, headers=headers())
            assert response.status_code == 422, response.text
        responses = await asyncio.gather(
            client.patch(url, json=patch_body(interval=5), headers=headers()),
            client.patch(url, json=patch_body(interval=3600), headers=headers()),
        )
        assert sorted(r.status_code for r in responses) == [200, 409]


@pytest.mark.parametrize("terminal", ["complete", "cancel"])
async def test_pause_preserves_schedule_preference_resume_reanchors_and_terminal_disables(
    db, terminal
):
    async with environment(db) as (seed, client):
        mission = await create(client, seed)
        url = f"/api/v1/missions/{mission['id']}"
        paused = await client.post(
            url + "/control",
            json={"operation": "pause", "expected_mission_version": 1},
            headers=headers(),
        )
        assert paused.status_code == 200
        schedule = paused.json()["schedule"]
        assert schedule["enabled"] is True and schedule["next_run_at"] is None
        assert schedule["version"] == 2
        stale = await client.patch(url + "/schedule", json=patch_body(), headers=headers())
        assert stale.status_code == 409
        configured = await client.patch(url + "/schedule", json=patch_body(2, 5), headers=headers())
        assert configured.status_code == 200
        assert configured.json()["enabled"] is True and configured.json()["next_run_at"] is None
        before = await database_time(db)
        resumed = await client.post(
            url + "/control",
            json={"operation": "resume", "expected_mission_version": 2},
            headers=headers(),
        )
        after = await database_time(db)
        assert resumed.status_code == 200
        schedule = resumed.json()["schedule"]
        assert schedule["version"] == 4 and schedule["enabled"] is True
        due = datetime.fromisoformat(schedule["next_run_at"])
        assert before + timedelta(seconds=5) <= due <= after + timedelta(seconds=5)
        ended = await client.post(
            url + "/control",
            json={"operation": terminal, "expected_mission_version": 3},
            headers=headers("approver"),
        )
        assert ended.status_code == 200
        schedule = ended.json()["schedule"]
        assert schedule["enabled"] is False and schedule["next_run_at"] is None
        assert schedule["version"] == 5
        assert (
            await client.patch(url + "/schedule", json=patch_body(5), headers=headers())
        ).status_code == 409


async def test_disabling_schedule_while_paused_survives_resume(db):
    async with environment(db) as (seed, client):
        mission = await create(client, seed)
        url = f"/api/v1/missions/{mission['id']}"
        await client.post(
            url + "/control",
            json={"operation": "pause", "expected_mission_version": 1},
            headers=headers(),
        )
        patched = await client.patch(
            url + "/schedule", json=patch_body(2, 30, False), headers=headers()
        )
        assert patched.status_code == 200
        resumed = await client.post(
            url + "/control",
            json={"operation": "resume", "expected_mission_version": 2},
            headers=headers(),
        )
        assert resumed.status_code == 200
        assert resumed.json()["schedule"]["enabled"] is False
        assert resumed.json()["schedule"]["next_run_at"] is None
        assert resumed.json()["schedule"]["version"] == 4
