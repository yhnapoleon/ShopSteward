from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from test_missions import body, environment, headers, settings
from test_operations import event, ingest

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def clean_jobs(db):
    async with db.session() as session, session.begin():
        await session.execute(text("DELETE FROM job_runs"))


async def start(client, seed):
    response = await client.post("/api/v1/missions", json=body(seed), headers=headers())
    assert response.status_code == 201, response.text
    return response.json()


async def run_check(db, seed):
    from app.planning.jobs import make_handlers
    from app.scheduling.runner import Runner

    runner = Runner(
        db,
        settings(db, seed),
        handlers={"check_mission": make_handlers(settings(db, seed))["check_mission"]},
    )
    assert await runner.run_once()


async def latest_job(db, mission_id):
    from app.scheduling.models import Job

    async with db.session() as session:
        return await session.scalar(
            select(Job)
            .where(Job.mission_id == mission_id)
            .order_by(Job.created_at.desc(), Job.id.desc())
        )


async def test_initial_worker_check_and_unchanged_input_reuses_immutable_plan(db):
    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        current = (
            await client.get(f"/api/v1/missions/{mission['id']}", headers=headers("viewer"))
        ).json()
        plan = (
            await client.get(
                f"/api/v1/plans/{current['current_plan_id']}", headers=headers("viewer")
            )
        ).json()
        assert plan["recommended_candidate_id"] == "candidate_40"
        assert plan["proposed_purchase"]["total_minor"] == 40000
        assert (await latest_job(db, mission["id"])).result["check_status"] == "ANOMALY"
        await client.post(f"/api/v1/missions/{mission['id']}/checks", json={}, headers=headers())
        await run_check(db, seed)
        plans = (
            await client.get(f"/api/v1/missions/{mission['id']}/plans", headers=headers())
        ).json()["items"]
        assert len(plans) == 1 and plans[0] == plan


@pytest.mark.parametrize("failure", ["source", "offer", "horizon", "inbound"])
async def test_invalid_inputs_are_inconclusive_and_never_publish_plan(db, failure):
    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        async with db.session() as session, session.begin():
            if failure == "source":
                await session.execute(
                    text("UPDATE source_cursors SET last_success_at=NULL WHERE store_id=:id"),
                    {"id": seed["store_id"]},
                )
            elif failure == "offer":
                await session.execute(
                    text(
                        "UPDATE supplier_offers SET document=jsonb_set(document,'{valid_until}',"
                        "to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE store_id=:id"
                    ),
                    {"id": seed["store_id"]},
                )
            elif failure == "horizon":
                await session.execute(
                    text(
                        "UPDATE forecasts SET document=jsonb_set(document,'{horizon_end}',"
                        "to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE store_id=:id"
                    ),
                    {"id": seed["store_id"]},
                )
            else:
                await session.execute(
                    text("UPDATE stocks SET in_transit=40 WHERE store_id=:id"),
                    {"id": seed["store_id"]},
                )
        await run_check(db, seed)
        job = await latest_job(db, mission["id"])
        assert job.status == "SUCCEEDED" and job.result["check_status"] == "INCONCLUSIVE"
        result = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        assert result["current_plan_id"] is None


async def test_expired_fixed_forecast_renews_current_remaining_demand_after_sale(db):
    from app.operations.models import StockRow, Store

    async with environment(db) as (seed, client):
        await ingest(db, seed, [event(seed, quantity=10)])
        mission = await start(client, seed)
        async with db.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE forecasts SET document=jsonb_set(document,'{valid_until}',"
                    "to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE store_id=:id"
                ),
                {"id": seed["store_id"]},
            )
        await run_check(db, seed)
        job = await latest_job(db, mission["id"])
        assert job.status == "SUCCEEDED"
        plan_id = next(r["id"] for r in job.result["references"] if r["type"] == "plan")
        plan = (await client.get("/api/v1/plans/" + plan_id, headers=headers())).json()
        assert plan["input_snapshot"]["forecast"]["remaining_demand"] == 50
        assert plan["input_snapshot"]["state"]["stocks"][0]["on_hand"] == 10
        assert plan["state_version"] == 3
        async with db.session() as session:
            stock = await session.get(StockRow, (seed["store_id"], "sku_001"))
            assert stock.forecast_version == plan["forecast_version"]
            assert (await session.get(Store, seed["store_id"])).state_version == 3


async def test_state_change_between_prepare_and_publish_discards_plan_and_queues_followup(db):
    from app.planning.jobs import make_handlers
    from app.scheduling.handlers import Handler
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        handler = make_handlers(settings(db, seed))["check_mission"]

        async def changing(database, job):
            prepared = await handler.run(database, job)
            await ingest(db, seed, [event(seed, quantity=1)])
            return prepared

        runner = Runner(
            db,
            settings(db, seed),
            handlers={
                "check_mission": Handler(
                    changing,
                    retry_safe=True,
                    apply=handler.apply,
                    after_complete=handler.after_complete,
                )
            },
        )
        await runner.run_once()
        async with db.session() as session:
            jobs = list(await session.scalars(select(Job).where(Job.mission_id == mission["id"])))
            assert sorted(j.status for j in jobs) == ["READY", "SUCCEEDED"]
            assert (
                next(j for j in jobs if j.status == "SUCCEEDED").result["check_status"] == "SKIPPED"
            )
        await run_check(db, seed)
        plans = (
            await client.get(f"/api/v1/missions/{mission['id']}/plans", headers=headers())
        ).json()["items"]
        assert len(plans) == 1 and plans[0]["state_version"] == 2


async def test_pause_during_calculation_and_expired_lease_cannot_publish(db):
    from app.planning.jobs import make_handlers
    from app.scheduling.handlers import Handler
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        handler = make_handlers(settings(db, seed))["check_mission"]

        async def pausing(database, job):
            prepared = await handler.run(database, job)
            await client.post(
                f"/api/v1/missions/{mission['id']}/control",
                json={"operation": "pause", "expected_mission_version": 1},
                headers=headers(),
            )
            return prepared

        runner = Runner(
            db,
            settings(db, seed),
            handlers={
                "check_mission": Handler(
                    pausing,
                    retry_safe=True,
                    apply=handler.apply,
                    after_complete=handler.after_complete,
                )
            },
        )
        await runner.run_once()
        assert (await latest_job(db, mission["id"])).result["check_status"] == "SKIPPED"
        await client.post(
            f"/api/v1/missions/{mission['id']}/control",
            json={"operation": "resume", "expected_mission_version": 2},
            headers=headers(),
        )

        async def expiring(database, job):
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
                    expiring,
                    retry_safe=True,
                    apply=handler.apply,
                    after_complete=handler.after_complete,
                )
            },
        )
        await runner.run_once()
        plans = (
            await client.get(f"/api/v1/missions/{mission['id']}/plans", headers=headers())
        ).json()["items"]
        assert plans == []


async def test_expired_plan_replaced_and_unknown_inbound_eta_not_counted(db):
    from app.missions.models import InboundRow, PlanRow

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        async with db.session() as session, session.begin():
            await session.execute(
                text("UPDATE stocks SET in_transit=40 WHERE store_id=:id"), {"id": seed["store_id"]}
            )
            session.add(
                InboundRow(
                    action_id=str(uuid4()),
                    store_id=seed["store_id"],
                    sku_id="sku_001",
                    ordered_qty=40,
                    received_qty=0,
                )
            )
        await run_check(db, seed)
        async with db.session() as session, session.begin():
            first = await session.scalar(select(PlanRow).where(PlanRow.mission_id == mission["id"]))
            assert first.document["input_snapshot"]["eligible_inbound_qty"] == 0
            assert first.document["proposed_purchase"]["quantity"] == 40
            old_document = first.document
            first.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await client.post(f"/api/v1/missions/{mission['id']}/checks", json={}, headers=headers())
        await run_check(db, seed)
        async with db.session() as session:
            rows = list(
                await session.scalars(
                    select(PlanRow)
                    .where(PlanRow.mission_id == mission["id"])
                    .order_by(PlanRow.plan_version)
                )
            )
            assert len(rows) == 2 and rows[0].status == "EXPIRED"
            assert rows[0].document == old_document
            assert rows[0].document["proposal_hash"] != rows[1].document["proposal_hash"]


async def test_demand_event_forecast_identity_stays_stable_across_checks(db):
    async with environment(db) as (seed, client):
        await ingest(db, seed, [event(seed, 1, "DEMAND_REVISED")])
        mission = await start(client, seed)
        await run_check(db, seed)
        await client.post(f"/api/v1/missions/{mission['id']}/checks", json={}, headers=headers())
        await run_check(db, seed)
        plans = (
            await client.get(f"/api/v1/missions/{mission['id']}/plans", headers=headers())
        ).json()["items"]
        assert len(plans) == 1


async def test_sale_versions_forecast_and_keeps_old_plan_unchanged(db):
    from app.operations.models import ForecastRow

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        sale = event(seed, quantity=10)
        sale["occurred_at"] = datetime.now(UTC).isoformat()
        await ingest(db, seed, [sale])
        await ingest(db, seed, [sale])
        await client.post(f"/api/v1/missions/{mission['id']}/checks", json={}, headers=headers())
        await run_check(db, seed)
        plans = (
            await client.get(f"/api/v1/missions/{mission['id']}/plans", headers=headers())
        ).json()["items"]
        # Same-second creation times use opaque IDs as the pagination tie-breaker.
        old, new = sorted(plans, key=lambda plan: plan["plan_version"])
        assert new["forecast_version"] != old["forecast_version"]
        assert old["input_snapshot"]["forecast"]["remaining_demand"] == 60
        assert new["input_snapshot"]["forecast"]["remaining_demand"] == 50
        assert new["input_snapshot"]["forecast"]["source_sequence"] == 1
        async with db.session() as session:
            row = await session.get(
                ForecastRow, (seed["store_id"], "sku_001", new["forecast_version"])
            )
            assert datetime.fromisoformat(row.document["data_as_of"]) == datetime.fromisoformat(
                sale["occurred_at"]
            )
            assert datetime.fromisoformat(row.document["data_as_of"]) > datetime.fromisoformat(
                seed["initial_forecast"]["data_as_of"]
            )
            rows = list(
                await session.scalars(
                    select(ForecastRow).where(ForecastRow.store_id == seed["store_id"])
                )
            )
            assert len(rows) == 2


async def test_rejected_intent_suppressed_on_automatic_revalidation_but_manual_can_replan(db):
    from app.missions.models import MissionRow, PlanRow
    from app.missions.repository import lock_mission, queue_check

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        async with db.session() as session, session.begin():
            store, row = await lock_mission(session, mission["id"])
            first = await session.get(PlanRow, row.current_plan_id)
            first.status = "REJECTED"
            # Simulates B0-05 rejection state; approval endpoint intentionally not registered yet.
            await session.execute(
                text(
                    "UPDATE forecasts SET document=jsonb_set(document,'{valid_until}',"
                    "to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE store_id=:id"
                ),
                {"id": store.id},
            )
            await queue_check(session, store, row, key=str(uuid4()))
        await run_check(db, seed)
        async with db.session() as session:
            rows = list(
                await session.scalars(select(PlanRow).where(PlanRow.mission_id == mission["id"]))
            )
            assert len(rows) == 1 and rows[0].status == "REJECTED"
        await client.post(
            f"/api/v1/missions/{mission['id']}/checks",
            json={"reason": "reconsider"},
            headers=headers(),
        )
        await run_check(db, seed)
        async with db.session() as session:
            rows = list(
                await session.scalars(select(PlanRow).where(PlanRow.mission_id == mission["id"]))
            )
            assert len(rows) == 2
            assert (await session.get(MissionRow, mission["id"])).current_plan_id != first.id
