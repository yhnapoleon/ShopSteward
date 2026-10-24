"""Source-scoped coalescing. Callers hold the store lock before touching jobs."""

from datetime import timedelta

from sqlalchemy import func, select

from app.core.hashing import digest
from app.operations.models import SourceSchedule
from app.scheduling.models import Job
from app.scheduling.repository import enqueue


async def initialize_schedules(session, store):
    now = await session.scalar(select(func.clock_timestamp()))
    for kind, interval in (("sync_events", 5), ("check_freshness", 60)):
        session.add(
            SourceSchedule(
                scenario_run_id=store.scenario_run_id,
                job_type=kind,
                interval_seconds=interval,
                next_run_at=now + timedelta(seconds=interval),
                rerun_requested=False,
            )
        )
    await session.flush()


async def queue_source(
    session,
    store,
    *,
    key,
    job_type="sync_events",
    trigger_source="EVENT",
    scheduled_for=None,
):
    receipt = None
    if trigger_source == "MANUAL":
        from app.missions.repository import command

        receipt, replay = await command(
            session,
            "local-operator",
            "source-sync",
            key,
            {"store_id": store.id, "job_type": job_type},
        )
        if replay:
            return await session.get(Job, receipt.response["job_run_id"])
    schedule = await session.get(
        SourceSchedule, (store.scenario_run_id, job_type), with_for_update=True
    )
    # Exact command replay remains stable even when another source request is active.
    dedup_key = digest(["source-job", store.scenario_run_id, job_type, key])
    previous = await session.scalar(select(Job).where(Job.dedup_key == dedup_key))
    if previous is not None:
        if receipt is not None:
            receipt.response = {"job_run_id": previous.id}
        return previous
    active = await session.scalar(
        select(Job)
        .where(
            Job.store_id == store.id,
            Job.job_type == job_type,
            Job.status.in_(["READY", "RUNNING", "RETRY_WAIT"]),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if active is not None:
        if active.status == "RUNNING" and trigger_source != "INTERVAL":
            schedule.rerun_requested = True
        elif active.status != "RUNNING" and trigger_source != "INTERVAL":
            active.available_at = await session.scalar(select(func.clock_timestamp()))
        if receipt is not None:
            receipt.response = {"job_run_id": active.id}
        return active
    schedule.rerun_requested = False
    job = await enqueue(
        session,
        job_type=job_type,
        store_id=store.id,
        dedup_key=dedup_key,
        payload={"scenario_run_id": store.scenario_run_id},
        trigger_source=trigger_source,
        scheduled_for=scheduled_for,
    )
    if receipt is not None:
        receipt.response = {"job_run_id": job.id}
    return job
