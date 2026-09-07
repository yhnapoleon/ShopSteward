import asyncio
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from test_missions import environment, settings
from test_operations import event, ingest
from test_planning_jobs import run_check, start

from app.missions.models import ScheduleRow
from app.scheduling.models import Job

pytestmark = pytest.mark.integration


async def source_job(db, seed, key, **kwargs):
    from app.operations.repository import store_for_run
    from app.operations.scheduling import queue_source

    async with db.session() as session, session.begin():
        store = await store_for_run(session, seed["scenario_run_id"])
        return await queue_source(session, store, key=key, **kwargs)


@pytest_asyncio.fixture(autouse=True)
async def clean_queue(db):
    async with db.session() as session, session.begin():
        await session.execute(text("DELETE FROM job_runs"))
        await session.execute(text("UPDATE schedules SET next_run_at=NULL"))
        await session.execute(
            text("UPDATE source_schedules SET next_run_at=clock_timestamp()+interval '1 day'")
        )


async def test_missed_intervals_concurrent_dispatch_keep_anchor_and_one_job(db):
    from app.scheduling.dispatcher import dispatch_due

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        async with db.session() as session, session.begin():
            now = await session.scalar(select(func.clock_timestamp()))
            anchor = now - timedelta(seconds=95)
            schedule = await session.get(ScheduleRow, mission["schedule"]["id"])
            schedule.enabled, schedule.next_run_at = True, anchor
        await asyncio.gather(dispatch_due(db), dispatch_due(db))
        async with db.session() as session:
            schedule = await session.get(ScheduleRow, mission["schedule"]["id"])
            jobs = list(
                await session.scalars(
                    select(Job).where(Job.mission_id == mission["id"], Job.status == "READY")
                )
            )
            assert len(jobs) == 1
            assert jobs[0].scheduled_for == anchor + timedelta(seconds=90)
            assert jobs[0].trigger_source == "INTERVAL"
            assert jobs[0].target_state_version == 1
            assert schedule.next_run_at == anchor + timedelta(seconds=120)


async def test_event_batch_wakes_idle_mission_and_records_target_versions(db):
    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        sale = event(seed, quantity=1)
        await ingest(db, seed, [sale])
        await ingest(db, seed, [sale])
        async with db.session() as session:
            jobs = list(
                await session.scalars(
                    select(Job).where(Job.mission_id == mission["id"], Job.status == "READY")
                )
            )
            assert len(jobs) == 1
            assert jobs[0].trigger_source == "EVENT"
            assert jobs[0].target_state_version == 2
            assert jobs[0].target_mission_version == 1


async def test_source_dispatch_merges_and_never_marks_caught_up_source_as_gapped(db):
    from app.operations.models import SourceSchedule
    from app.scheduling.dispatcher import dispatch_due

    async with environment(db) as (seed, client):
        async with db.session() as session, session.begin():
            now = await session.scalar(select(func.clock_timestamp()))
            sync = await session.get(SourceSchedule, (seed["scenario_run_id"], "sync_events"))
            sync.next_run_at = now - timedelta(seconds=16)
        await asyncio.gather(dispatch_due(db), dispatch_due(db))
        async with db.session() as session:
            jobs = list(
                await session.scalars(
                    select(Job).where(
                        Job.store_id == seed["store_id"],
                        Job.job_type == "sync_events",
                        Job.status == "READY",
                    )
                )
            )
            assert len(jobs) == 1
            assert jobs[0].scheduled_for == now - timedelta(seconds=1)
            assert (
                await session.scalar(
                    text("SELECT last_error FROM source_cursors WHERE store_id=:id"),
                    {"id": seed["store_id"]},
                )
                is None
            )


async def test_source_failure_is_persistent_and_freshness_preserves_business_risk(db):
    from app.alerts.models import AlertRow
    from app.core.errors import AppError
    from app.operations.jobs import make_handlers
    from app.operations.models import SourceCursor
    from app.operations.repository import store_for_run
    from app.operations.scheduling import queue_source
    from app.scheduling.runner import Runner

    class Unreadable:
        async def events(self, run_id, after):
            raise AppError(503, "SOURCE_UNAVAILABLE", "offline", retryable=True)

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        handlers = make_handlers(settings(db, seed), client=Unreadable())
        async with db.session() as session, session.begin():
            store = await store_for_run(session, seed["scenario_run_id"])
            await queue_source(session, store, key="failure-" + store.id)
        await Runner(
            db, settings(db, seed), handlers={"sync_events": handlers["sync_events"]}
        ).run_once()
        async with db.session() as session:
            cursor = await session.get(SourceCursor, seed["scenario_run_id"])
            assert cursor.last_error == "SOURCE_UNAVAILABLE"
        async with db.session() as session, session.begin():
            store = await store_for_run(session, seed["scenario_run_id"])
            await queue_source(session, store, key="fresh-" + store.id, job_type="check_freshness")
        await Runner(
            db, settings(db, seed), handlers={"check_freshness": handlers["check_freshness"]}
        ).run_once()
        async with db.session() as session:
            risks = set(
                await session.scalars(
                    select(AlertRow.type).where(
                        AlertRow.mission_id == mission["id"], AlertRow.status != "RESOLVED"
                    )
                )
            )
            assert risks == {"STOCKOUT_RISK", "DATA_STALE"}


async def test_source_pages_and_request_during_running_fetch_make_one_successor(db):
    from app.operations.jobs import make_handlers
    from app.operations.models import SourceCursor
    from app.operations.schemas import EventPage
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        entered, release = asyncio.Event(), asyncio.Event()
        pages = [event(seed, 1, quantity=1), event(seed, 2, quantity=2)]

        class PagedSource:
            async def events(self, run_id, after):
                assert run_id == seed["scenario_run_id"]
                if after == 0:
                    entered.set()
                    await release.wait()
                return EventPage(
                    events=pages[after : after + 1],
                    last_sequence=min(after + 1, 2),
                    has_more=after == 0,
                    source_head_sequence=2,
                )

        handlers = make_handlers(settings(db, seed), client=PagedSource())
        runner = Runner(db, settings(db, seed), handlers={"sync_events": handlers["sync_events"]})
        first = await source_job(db, seed, "first")
        task = asyncio.create_task(runner.run_once())
        try:
            await asyncio.wait_for(entered.wait(), 3)
            merged = await source_job(db, seed, "advance-during-fetch")
            assert merged.id == first.id
        finally:
            release.set()
            await task
        async with db.session() as session:
            active = list(
                await session.scalars(
                    select(Job).where(Job.store_id == seed["store_id"], Job.status == "READY")
                )
            )
            assert len(active) == 1
            cursor = await session.get(SourceCursor, seed["scenario_run_id"])
            assert cursor.last_sequence == 1 and cursor.last_error == "SOURCE_CATCHING_UP"
        await runner.run_once()
        async with db.session() as session:
            cursor = await session.get(SourceCursor, seed["scenario_run_id"])
            assert cursor.last_sequence == 2 and cursor.last_error is None
            assert (
                await session.scalar(
                    text("SELECT on_hand FROM stocks WHERE store_id=:id"), {"id": seed["store_id"]}
                )
                == 17
            )


async def test_manual_source_command_replay_stays_merged_after_original_completes(db):
    from app.operations.jobs import make_handlers
    from app.operations.schemas import EventPage
    from app.scheduling.runner import Runner

    class EmptySource:
        async def events(self, run_id, after):
            return EventPage(
                events=[], last_sequence=after, has_more=False, source_head_sequence=after
            )

    async with environment(db) as (seed, client):
        first = await source_job(db, seed, "first")
        manual_key = "manual:" + seed["store_id"]
        merged = await source_job(db, seed, manual_key, trigger_source="MANUAL")
        assert merged.id == first.id
        handlers = make_handlers(settings(db, seed), client=EmptySource())
        await Runner(
            db, settings(db, seed), handlers={"sync_events": handlers["sync_events"]}
        ).run_once()
        replay = await source_job(db, seed, manual_key, trigger_source="MANUAL")
        assert replay.id == first.id


async def test_dispatch_transaction_rolls_back_occurrence_on_enqueue_failure(db, monkeypatch):
    import app.scheduling.dispatcher as dispatcher

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        async with db.session() as session, session.begin():
            anchor = await session.scalar(select(func.clock_timestamp())) - timedelta(seconds=1)
            schedule = await session.get(ScheduleRow, mission["schedule"]["id"])
            schedule.enabled, schedule.next_run_at = True, anchor
        real = dispatcher.queue_check

        async def fail_after_enqueue(*args, **kwargs):
            await real(*args, **kwargs)
            raise RuntimeError("publication failed")

        monkeypatch.setattr(dispatcher, "queue_check", fail_after_enqueue)
        with pytest.raises(RuntimeError, match="publication failed"):
            await dispatcher.dispatch_due(db)
        async with db.session() as session:
            assert (await session.get(ScheduleRow, mission["schedule"]["id"])).next_run_at == anchor
            assert not list(
                await session.scalars(
                    select(Job).where(Job.mission_id == mission["id"], Job.status == "READY")
                )
            )


async def test_saturated_worker_still_dispatches_while_other_worker_checks(db):
    from app.operations.jobs import make_handlers
    from app.operations.schemas import EventPage
    from app.planning.jobs import make_handlers as planning_handlers
    from app.scheduling.dispatcher import dispatch_due
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        entered, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class SlowSource:
            async def events(self, run_id, after):
                entered.set()
                await release.wait()
                return EventPage(
                    events=[], last_sequence=after, has_more=False, source_head_sequence=after
                )

        cfg = settings(db, seed, worker_concurrency=1, worker_poll_seconds=0.05)
        handler = make_handlers(cfg, client=SlowSource())["sync_events"]
        await source_job(db, seed, "slow")
        runner = Runner(db, cfg, handlers={"sync_events": handler}, dispatcher=dispatch_due)
        serving = asyncio.create_task(runner.serve(stop))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            async with db.session() as session, session.begin():
                schedule = await session.get(ScheduleRow, mission["schedule"]["id"])
                schedule.enabled = True
                schedule.next_run_at = await session.scalar(
                    select(func.clock_timestamp())
                ) - timedelta(seconds=1)
            async with asyncio.timeout(4):
                while True:
                    async with db.session() as session:
                        check = await session.scalar(
                            select(Job).where(
                                Job.mission_id == mission["id"], Job.status == "READY"
                            )
                        )
                    if check:
                        break
                    await asyncio.sleep(0.05)
            other = Runner(db, cfg, handlers=planning_handlers(cfg))
            assert await other.run_once()
            async with db.session() as session:
                assert (await session.get(Job, check.id)).status == "SUCCEEDED"
        finally:
            stop.set()
            release.set()
            await serving


async def test_expired_source_lease_cannot_publish_cursor_error_or_freshness_alert(db):
    from app.alerts.models import AlertRow
    from app.core.errors import AppError
    from app.operations.jobs import make_handlers
    from app.operations.models import SourceCursor
    from app.scheduling.handlers import Handler
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        handlers = make_handlers(settings(db, seed))
        for kind in ("sync_events", "check_freshness"):
            queued = await source_job(db, seed, kind, job_type=kind)

            async def expire(database, job):
                async with database.session() as session, session.begin():
                    await session.execute(
                        text(
                            "UPDATE job_runs SET lease_until=clock_timestamp()-interval '1 second' "
                            "WHERE id=:id"
                        ),
                        {"id": job.id},
                    )
                    await session.execute(
                        text("UPDATE source_cursors SET last_success_at=NULL WHERE store_id=:id"),
                        {"id": seed["store_id"]},
                    )
                if job.job_type == "sync_events":
                    raise AppError(503, "SOURCE_UNAVAILABLE", "offline", retryable=True)

            handler = handlers[kind]
            await Runner(
                db,
                settings(db, seed),
                handlers={
                    kind: Handler(
                        expire,
                        retry_safe=True,
                        apply=handler.apply,
                        on_error=handler.on_error,
                        after_complete=handler.after_complete,
                    )
                },
            ).run_once()
            async with db.session() as session:
                assert (await session.get(Job, queued.id)).status == "RUNNING"
                assert (await session.get(SourceCursor, seed["scenario_run_id"])).last_error is None
                assert not list(
                    await session.scalars(
                        select(AlertRow).where(
                            AlertRow.mission_id == mission["id"], AlertRow.type == "DATA_STALE"
                        )
                    )
                )
