import asyncio
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import func, select, text
from test_alerts import listing, recheck
from test_missions import (
    clean_queue,  # noqa: F401
    environment,
    headers,
)
from test_planning_jobs import run_check, start

pytestmark = pytest.mark.integration


def design(name, value):
    document = json.loads(
        (Path(__file__).parents[3] / "docs/api/backend.openapi.json").read_text("utf-8")
    )
    Draft202012Validator(
        {"$ref": f"#/components/schemas/{name}", "components": document["components"]},
        format_checker=FormatChecker(),
    ).validate(value)


async def dashboard(client, seed):
    response = await client.get(
        "/api/v1/dashboard", params={"store_id": seed["store_id"]}, headers=headers("viewer")
    )
    assert response.status_code == 200, response.text
    value = response.json()
    design("Dashboard", value)
    return value


async def test_dashboard_contract_counts_due_work_and_reads_have_no_writes(db):
    from app.missions.models import TimelineRow
    from app.operations.models import LedgerEntry
    from app.scheduling.models import Job

    async with environment(db) as (seed, client):
        initial = await dashboard(client, seed)
        assert initial["active_mission_count"] == initial["active_alert_count"] == 0
        assert initial["last_check_at"] is initial["next_check_at"] is None
        await start(client, seed)
        before = await dashboard(client, seed)
        assert before["active_mission_count"] == 1 and before["next_check_at"] is not None
        await run_check(db, seed)
        after = await dashboard(client, seed)
        assert after["active_alert_count"] == 1 and after["last_check_at"] is not None
        assert after["next_check_at"] is None and after["freshness"]["status"] == "FRESH"
        alerts = await listing(client, seed)
        design("AlertList", alerts)
        await client.post(
            f"/api/v1/alerts/{alerts['items'][0]['id']}/acknowledgement", headers=headers()
        )
        async with db.session() as session:
            counts = [
                await session.scalar(select(func.count()).select_from(model))
                for model in (TimelineRow, LedgerEntry, Job)
            ]
        for _ in range(3):
            current = await dashboard(client, seed)
            assert current["active_alert_count"] == 1 and current["state"] == after["state"]
        async with db.session() as session:
            assert counts == [
                await session.scalar(select(func.count()).select_from(model))
                for model in (TimelineRow, LedgerEntry, Job)
            ]


async def test_freshness_unknown_stale_and_reads_do_not_resolve_alerts(db):
    from app.operations.repository import mark_caught_up

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        async with db.session() as session, session.begin():
            await session.execute(
                text("UPDATE source_cursors SET last_success_at=NULL WHERE store_id=:id"),
                {"id": seed["store_id"]},
            )
        assert (await dashboard(client, seed))["freshness"]["status"] == "UNKNOWN"
        await recheck(db, seed, client, mission)
        async with db.session() as session, session.begin():
            await mark_caught_up(session, seed["scenario_run_id"], 0)
            await session.flush()
            await session.execute(
                text(
                    "UPDATE source_cursors "
                    "SET last_success_at=clock_timestamp()-interval '31 seconds' "
                    "WHERE store_id=:id"
                ),
                {"id": seed["store_id"]},
            )
        stale = await dashboard(client, seed)
        assert stale["freshness"]["status"] == "STALE" and stale["active_alert_count"] == 2
        async with db.session() as session, session.begin():
            await mark_caught_up(session, seed["scenario_run_id"], 0)
        assert (await dashboard(client, seed))["active_alert_count"] == 2


async def test_timeline_pagination_filters_and_cross_store_permissions(db):
    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        alert = (await listing(client, seed))["items"][0]
        await client.post(f"/api/v1/alerts/{alert['id']}/acknowledgement", headers=headers())
        path = f"/api/v1/missions/{mission['id']}/timeline"
        seen = []
        cursor = None
        first_cursor = None
        while True:
            response = await client.get(
                path,
                params={"limit": 2, **({"cursor": cursor} if cursor else {})},
                headers=headers("viewer"),
            )
            assert response.status_code == 200
            page = response.json()
            design("TimelineEntryList", page)
            seen.extend(page["items"])
            cursor = page["next_cursor"]
            first_cursor = first_cursor or cursor
            if cursor is None:
                break
        assert len(seen) == len({r["id"] for r in seen})
        ack = next(r for r in seen if r["type"] == "ALERT_ACKNOWLEDGED")
        assert ack["actor_type"] == "USER" and ack["actor_id"] == "operator"
        assert {"type": "alert", "id": alert["id"]} in ack["references"]
        assert (
            await client.get(path, params={"cursor": "bad"}, headers=headers())
        ).status_code == 422
        assert (
            await client.get(
                "/api/v1/alerts",
                params={"store_id": seed["store_id"], "cursor": first_cursor},
                headers=headers(),
            )
        ).status_code == 422
        async with environment(db) as (other, other_client):
            assert (await other_client.get(path, headers=headers("viewer"))).status_code == 404
            assert (
                await other_client.post(
                    f"/api/v1/alerts/{alert['id']}/acknowledgement", headers=headers()
                )
            ).status_code == 404
            assert (
                await client.get(
                    "/api/v1/alerts",
                    params={"store_id": other["store_id"], "mission_id": mission["id"]},
                    headers=headers("admin"),
                )
            ).status_code == 404


async def test_dashboard_uses_one_snapshot_across_concurrent_check_commit(db, monkeypatch):
    import app.reporting.repository as repo

    async with environment(db) as (seed, client):
        await start(client, seed)
        read, committed = asyncio.Event(), asyncio.Event()
        original = repo.get_state

        async def paused(session, store_id):
            state = await original(session, store_id)
            read.set()
            await asyncio.wait_for(committed.wait(), 5)
            return state

        monkeypatch.setattr(repo, "get_state", paused)
        request = asyncio.create_task(dashboard(client, seed))
        try:
            await asyncio.wait_for(read.wait(), 5)
            await run_check(db, seed)
        finally:
            committed.set()
        snapshot = await request
        assert snapshot["active_alert_count"] == 0 and snapshot["last_check_at"] is None
        monkeypatch.setattr(repo, "get_state", original)
        assert (await dashboard(client, seed))["active_alert_count"] == 1
