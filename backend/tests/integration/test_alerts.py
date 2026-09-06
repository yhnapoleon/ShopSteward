import asyncio

import pytest
from sqlalchemy import func, select, text
from test_missions import (
    clean_queue,  # noqa: F401
    environment,
    headers,
    settings,
)
from test_operations import event, ingest
from test_planning_jobs import run_check, start

pytestmark = pytest.mark.integration


async def listing(client, seed, **filters):
    response = await client.get(
        "/api/v1/alerts",
        params={"store_id": seed["store_id"], **filters},
        headers=headers("viewer"),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def recheck(db, seed, client, mission):
    response = await client.post(
        f"/api/v1/missions/{mission['id']}/checks", json={}, headers=headers()
    )
    assert response.status_code == 202
    await run_check(db, seed)


async def test_stock_alert_ack_escalation_resolution_and_new_episode(db):
    from app.alerts.models import AlertRow

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        first = (await listing(client, seed))["items"][0]
        assert first["type"] == "STOCKOUT_RISK" and first["facts"]["shortage_qty"] == 40
        ack_headers = headers()
        path = f"/api/v1/alerts/{first['id']}/acknowledgement"
        ack = await client.post(path, headers=ack_headers)
        assert ack.status_code == 200 and ack.json()["status"] == "ACKNOWLEDGED"
        await ingest(db, seed, [event(seed, quantity=20)])
        await recheck(db, seed, client, mission)
        escalated = (await listing(client, seed))["items"][0]
        assert escalated["id"] == first["id"] and escalated["status"] == "OPEN"
        assert escalated["severity"] == "CRITICAL" and escalated["state_version"] == 2
        assert (await client.post(path, headers=ack_headers)).json() == ack.json()
        async with db.session() as session:
            row = await session.get(AlertRow, first["id"])
            assert row.acknowledged_by == "operator" and row.acknowledged_at is not None
        await ingest(db, seed, [event(seed, 2, "DEMAND_REVISED", remaining_demand=0)])
        await recheck(db, seed, client, mission)
        resolved = (await listing(client, seed))["items"][0]
        assert resolved["status"] == "RESOLVED" and resolved["resolved_at"] is not None
        assert resolved["state_version"] == escalated["state_version"]
        assert (await client.post(path, headers=headers())).status_code == 409
        await ingest(db, seed, [event(seed, 3, "DEMAND_REVISED", remaining_demand=40)])
        await recheck(db, seed, client, mission)
        rows = (await listing(client, seed))["items"]
        assert len(rows) == 2 and len({r["id"] for r in rows}) == 2


async def test_one_hundred_checks_deduplicate_risk_transition_and_keep_state(db):
    from app.missions.models import TimelineRow
    from app.operations.repository import get_state, mark_caught_up

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        for _ in range(99):
            async with db.session() as session, session.begin():
                await mark_caught_up(session, seed["scenario_run_id"], 0)
            await recheck(db, seed, client, mission)
        assert len((await listing(client, seed))["items"]) == 1
        async with db.session() as session:
            assert (await get_state(session, seed["store_id"])).state_version == 1
            rows = list(
                await session.scalars(
                    select(TimelineRow).where(TimelineRow.mission_id == mission["id"])
                )
            )
            assert sum(r.type == "ALERT_OPENED" for r in rows) == 1
            assert sum(r.type == "CHECK_COMPLETED" for r in rows) == 100


async def test_stale_input_preserves_business_risk_and_only_fresh_check_resolves_stale(db):
    from app.operations.repository import mark_caught_up

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        async with db.session() as session, session.begin():
            await session.execute(
                text("UPDATE source_cursors SET last_success_at=NULL WHERE store_id=:id"),
                {"id": seed["store_id"]},
            )
        await recheck(db, seed, client, mission)
        active = (await listing(client, seed, status="OPEN"))["items"]
        assert {r["type"] for r in active} == {"DATA_STALE", "STOCKOUT_RISK"}
        await recheck(db, seed, client, mission)
        assert len((await listing(client, seed))["items"]) == 2
        async with db.session() as session, session.begin():
            await mark_caught_up(session, seed["scenario_run_id"], 0)
        await recheck(db, seed, client, mission)
        rows = (await listing(client, seed))["items"]
        assert next(r for r in rows if r["type"] == "DATA_STALE")["status"] == "RESOLVED"
        assert next(r for r in rows if r["type"] == "STOCKOUT_RISK")["status"] == "OPEN"


async def test_ack_permissions_concurrency_and_cross_alert_idempotency(db):
    from app.missions.models import TimelineRow

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        first = (await listing(client, seed))["items"][0]
        path = f"/api/v1/alerts/{first['id']}/acknowledgement"
        assert (await client.post(path, headers=headers("viewer"))).status_code == 403
        command_headers = headers()
        results = await asyncio.gather(
            *[client.post(path, headers=command_headers) for _ in range(3)]
        )
        assert all(r.status_code == 200 and r.json() == results[0].json() for r in results)
        async with db.session() as session, session.begin():
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(TimelineRow)
                    .where(
                        TimelineRow.mission_id == mission["id"],
                        TimelineRow.type == "ALERT_ACKNOWLEDGED",
                    )
                )
                == 1
            )
            await session.execute(
                text("UPDATE source_cursors SET last_success_at=NULL WHERE store_id=:id"),
                {"id": seed["store_id"]},
            )
        await recheck(db, seed, client, mission)
        stale = next(r for r in (await listing(client, seed))["items"] if r["type"] == "DATA_STALE")
        conflict = await client.post(
            f"/api/v1/alerts/{stale['id']}/acknowledgement", headers=command_headers
        )
        assert conflict.status_code == 409


async def test_expired_lease_rolls_back_alert_plan_and_check_timeline(db):
    from app.alerts.models import AlertRow
    from app.missions.models import TimelineRow
    from app.planning.jobs import make_handler
    from app.scheduling.handlers import Handler
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        handler = make_handler(settings(db, seed))

        async def expire(database, job):
            prepared = await handler.run(database, job)
            async with db.session() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE job_runs SET lease_until=clock_timestamp()-interval '1 second' "
                        "WHERE id=:id"
                    ),
                    {"id": job.id},
                )
            return prepared

        runner = Runner(
            db,
            settings(db, seed),
            handlers={
                "check_mission": Handler(
                    expire,
                    retry_safe=True,
                    apply=handler.apply,
                    after_complete=handler.after_complete,
                )
            },
        )
        await runner.run_once()
        async with db.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AlertRow)
                    .where(AlertRow.mission_id == mission["id"])
                )
                == 0
            )
            kinds = list(
                await session.scalars(
                    select(TimelineRow.type).where(TimelineRow.mission_id == mission["id"])
                )
            )
            assert "PLAN_CREATED" not in kinds and "CHECK_COMPLETED" not in kinds
