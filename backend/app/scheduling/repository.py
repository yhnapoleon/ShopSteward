import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.api.schemas import JobResult, JobType
from app.core.errors import AppError
from app.scheduling.models import Job, WorkerHeartbeat


async def enqueue(
    session,
    *,
    job_type,
    dedup_key,
    store_id=None,
    mission_id=None,
    payload=None,
    trigger_source="MANUAL",
    scheduled_for=None,
    target_state_version=None,
    target_mission_version=None,
):
    """Caller owns the transaction, including any business mutation associated with enqueue."""
    TypeAdapter(JobType).validate_python(job_type)
    content = {
        "job_type": job_type,
        "store_id": store_id,
        "mission_id": mission_id,
        "payload": payload or {},
    }
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    now = await session.scalar(select(func.clock_timestamp()))
    await session.execute(
        insert(Job)
        .values(
            id=str(uuid4()),
            dedup_key=dedup_key,
            request_hash=digest,
            **content,
            status="READY",
            trigger_source=trigger_source,
            attempt_count=0,
            scheduled_for=scheduled_for or now,
            available_at=now,
            target_state_version=target_state_version,
            target_mission_version=target_mission_version,
        )
        .on_conflict_do_nothing(index_elements=[Job.dedup_key])
    )
    job = await session.scalar(select(Job).where(Job.dedup_key == dedup_key))
    if job.request_hash != digest:
        raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Job key was used for different content")
    return job


async def claim(session, *, lease_seconds, job_types):
    job = await session.scalar(
        select(Job)
        .where(
            Job.status.in_(["READY", "RETRY_WAIT"]),
            Job.available_at <= func.clock_timestamp(),
            Job.job_type.in_(job_types),
        )
        .order_by(Job.available_at, Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    now = await session.scalar(select(func.clock_timestamp()))
    job.status = "RUNNING"
    job.lease_token = str(uuid4())
    job.lease_until = now + timedelta(seconds=lease_seconds)
    job.started_at = now
    job.attempt_count += 1
    await session.flush()
    return job


def owned(job_id, token):
    return (
        Job.id == job_id,
        Job.status == "RUNNING",
        Job.lease_token == token,
        Job.lease_until > func.clock_timestamp(),
    )


async def complete(session, job_id, token, result):
    checked = JobResult.model_validate(result).model_dump(mode="json", exclude_unset=True)
    changed = await session.execute(
        update(Job)
        .where(*owned(job_id, token))
        .values(
            status="SUCCEEDED",
            result=checked,
            finished_at=func.clock_timestamp(),
            lease_token=None,
            lease_until=None,
            error_code=None,
            last_error=None,
        )
    )
    return changed.rowcount == 1


async def fail(session, job_id, token, error_code, *, retryable=False):
    if retryable:
        job = await session.scalar(select(Job).where(*owned(job_id, token)).with_for_update())
        if job is None:
            return False
        if job.attempt_count < 3:
            job.status = "RETRY_WAIT"
            job.available_at = await session.scalar(select(func.clock_timestamp())) + timedelta(
                seconds=2**job.attempt_count
            )
            job.error_code = error_code
            job.last_error = "Dependency request will be retried with the original command"
            job.lease_token = job.lease_until = None
            await session.flush()
            return True
    changed = await session.execute(
        update(Job)
        .where(*owned(job_id, token))
        .values(
            status="FAILED",
            error_code=error_code,
            last_error="Worker handler did not complete",
            finished_at=func.clock_timestamp(),
            lease_token=None,
            lease_until=None,
        )
    )
    return changed.rowcount == 1


async def renew(session, job_id, token, lease_seconds):
    changed = await session.execute(
        update(Job)
        .where(*owned(job_id, token))
        .values(
            lease_until=func.clock_timestamp() + timedelta(seconds=lease_seconds),
        )
    )
    return changed.rowcount == 1


async def recover_expired(session, *, retry_safe_types):
    # External-write jobs are deliberately not eligible; their future handler must reconcile.
    jobs = (
        await session.scalars(
            select(Job)
            .where(
                Job.status == "RUNNING",
                Job.lease_until <= func.clock_timestamp(),
                Job.job_type.in_(retry_safe_types),
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        )
    ).all()
    now = await session.scalar(select(func.clock_timestamp()))
    for job in jobs:
        job.status = "RETRY_WAIT" if job.attempt_count < 3 else "FAILED"
        job.error_code = "LEASE_EXPIRED"
        job.last_error = "Worker lease expired"
        job.lease_token = job.lease_until = None
        job.available_at = now
        if job.status == "FAILED":
            job.finished_at = now
    await session.flush()
    return len(jobs)


async def heartbeat(session, worker_id, status="RUNNING"):
    await session.execute(
        insert(WorkerHeartbeat)
        .values(
            worker_id=worker_id,
            status=status,
            heartbeat_at=func.clock_timestamp(),
        )
        .on_conflict_do_update(
            index_elements=[WorkerHeartbeat.worker_id],
            set_={
                "status": status,
                "heartbeat_at": func.clock_timestamp(),
            },
        )
    )


async def monitoring_status(
    session, stale_seconds, source_stale_seconds=30, *, agent_enabled=False
):
    from app.operations.models import SourceCursor

    now = await session.scalar(select(func.clock_timestamp()))
    workers = (await session.scalars(select(WorkerHeartbeat))).all()
    running = [w for w in workers if w.status == "RUNNING"]
    fresh = [w for w in running if (now - w.heartbeat_at).total_seconds() < stale_seconds]
    status = "RUNNING" if fresh else "STALE" if running else "STOPPED" if workers else "UNKNOWN"
    count, oldest = (
        await session.execute(
            select(func.count(), func.min(Job.available_at)).where(
                Job.status.in_(["READY", "RETRY_WAIT"]),
                Job.available_at <= now,
            )
        )
    ).one()
    cursors = list(
        await session.scalars(select(SourceCursor).order_by(SourceCursor.scenario_run_id))
    )
    return {
        "worker_status": status,
        "worker_heartbeat_at": max((w.heartbeat_at for w in workers), default=None),
        "due_job_count": count,
        "oldest_due_seconds": max(0, int((now - oldest).total_seconds())) if oldest else 0,
        "sources": [
            {
                "source": f"{cursor.source}:{cursor.scenario_run_id}",
                "last_success_at": cursor.last_success_at,
                "last_sequence": cursor.last_sequence,
                "status": (
                    "UNKNOWN"
                    if cursor.last_success_at is None
                    else "FRESH"
                    if cursor.last_error is None
                    and (now - cursor.last_success_at).total_seconds() < source_stale_seconds
                    else "STALE"
                ),
                "last_error": cursor.last_error,
            }
            for cursor in cursors
        ],
        "agent_enabled": agent_enabled,
        "forecast_provider": "fixed",
    }
