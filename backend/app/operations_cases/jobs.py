"""Opt-in durable follow-up. Observe authoritative facts; never adopt, approve or purchase."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import exists, func, select, update

from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.core.hashing import digest
from app.missions.models import InboundRow
from app.missions.repository import lock_mission
from app.operations.models import SourceCursor, Store
from app.operations_cases.models import CaseEventRow, CaseRevisionRow, CaseRow
from app.operations_cases.repository import detail, event
from app.planning.snapshot import source_fresh
from app.scheduling.handlers import Handler
from app.scheduling.models import Job
from app.scheduling.repository import enqueue

TERMINAL = {"CANCELLED", "RESOLVED", "CLOSED"}
ACTIVE_JOBS = {"READY", "RUNNING", "RETRY_WAIT"}


async def cancel_followup(session, case):
    await session.execute(
        update(Job)
        .where(
            Job.job_type == "operations_case_followup",
            Job.payload["case_id"].astext == case.id,
            Job.status.in_(["READY", "RETRY_WAIT"]),
        )
        .values(status="CANCELLED", finished_at=func.clock_timestamp())
    )


async def queue_followup(session, case, *, delay_seconds=0, exclude_job=None):
    if not case.followup_enabled or case.status in TERMINAL:
        return None
    active = await session.scalar(
        select(Job).where(
            Job.job_type == "operations_case_followup",
            Job.payload["case_id"].astext == case.id,
            Job.status.in_(ACTIVE_JOBS),
            Job.id != exclude_job if exclude_job else True,
        )
    )
    if active:
        return active
    now = await session.scalar(select(func.clock_timestamp()))
    job = await enqueue(
        session,
        job_type="operations_case_followup",
        store_id=case.store_id,
        mission_id=case.mission_id,
        dedup_key=digest(["case-followup", case.id, str(uuid4())]),
        payload={"case_id": case.id},
        trigger_source="AT",
    )
    job.available_at = job.scheduled_for = now + timedelta(seconds=delay_seconds)
    return job


def owner_authorized(settings, case):
    for grant in settings.auth_tokens:
        if grant.kind == "user" and grant.principal_id == case.owner_id:
            try:
                authorize_store(grant, case.store_id)
                return True
            except AppError:
                continue
    return False


def make_handlers(settings):
    async def recover(db):
        async with db.session() as session:
            ids = list(
                await session.scalars(
                    select(CaseRow.id)
                    .where(
                        CaseRow.followup_enabled.is_(True),
                        CaseRow.status.not_in(TERMINAL),
                        ~exists(
                            select(Job.id).where(
                                Job.job_type == "operations_case_followup",
                                Job.payload["case_id"].astext == CaseRow.id,
                                Job.status.in_(ACTIVE_JOBS),
                            )
                        ),
                    )
                    .limit(100)
                )
            )
        for identifier in ids:
            async with db.session() as session, session.begin():
                case = await session.get(CaseRow, identifier)
                available = await session.scalar(
                    select(Store.id)
                    .where(Store.id == case.store_id)
                    .with_for_update(skip_locked=True)
                )
                if available is None:
                    continue
                await lock_mission(session, case.mission_id)
                await session.refresh(case, with_for_update=True)
                await queue_followup(session, case)

    async def run(db, job):
        # Publication and reads happen together under the same short transaction and lease fence.
        return None

    async def apply(session, job, _):
        case = await session.get(CaseRow, job.payload["case_id"])
        store, mission = await lock_mission(session, case.mission_id)
        await session.refresh(case, with_for_update=True)
        outcome = {
            "summary": "Case follow-up checked",
            "references": [
                {"type": "artifact", "id": case.id},
                {"type": "mission", "id": mission.id},
            ],
        }
        if not case.followup_enabled or case.status in TERMINAL:
            return outcome
        if not owner_authorized(settings, case):
            case.followup_enabled = False
            await event(session, case, "FOLLOWUP_STOPPED", {"reason": "OWNER_ACCESS_REVOKED"})
            return outcome
        view = await detail(session, case)
        now = await session.scalar(select(func.clock_timestamp()))
        cursor = await session.scalar(
            select(SourceCursor).where(SourceCursor.store_id == case.store_id)
        )
        inbound = list(
            await session.scalars(
                select(InboundRow)
                .where(InboundRow.store_id == case.store_id, InboundRow.sku_id == case.sku_id)
                .order_by(InboundRow.action_id)
            )
        )
        observation = {
            "revision": case.current_revision,
            "state_version": store.state_version,
            "mission_version": mission.mission_version,
            "execution_status": view.execution_status,
            "action_id": view.action_id,
            "plan_id": view.plan_id,
            "stale": view.stale,
            "source_fresh": source_fresh(cursor, now, settings.source_stale_seconds),
            "inbound": [
                {
                    "action_id": a.action_id,
                    "ordered_qty": a.ordered_qty,
                    "received_qty": a.received_qty,
                    "expected_arrival_at": a.expected_arrival_at.isoformat()
                    if a.expected_arrival_at
                    else None,
                }
                for a in inbound
            ],
        }
        fingerprint = digest(observation)
        last = await session.scalar(
            select(CaseEventRow)
            .where(CaseEventRow.case_id == case.id, CaseEventRow.kind == "FOLLOWUP_OBSERVED")
            .order_by(CaseEventRow.seq.desc())
            .limit(1)
        )
        if last is None or last.payload.get("fingerprint") != fingerprint:
            await event(
                session, case, "FOLLOWUP_OBSERVED", {"fingerprint": fingerprint, **observation}
            )
        revision = await session.get(CaseRevisionRow, (case.id, case.current_revision))
        horizon_end = (
            datetime.fromisoformat(revision.snapshot["forecast"]["horizon_end"])
            if revision.snapshot
            else None
        )
        if mission.status in {"COMPLETED", "CANCELLED"} or (
            horizon_end and store.simulation_time >= horizon_end
        ):
            case.status, case.followup_enabled = "CLOSED", False
            await event(
                session,
                case,
                "CASE_CLOSED",
                {"outcome": "unknown", "reason": "ACTUAL_DEMAND_OUTCOME_UNAVAILABLE"},
            )
        elif view.execution_status in {"EXECUTING", "UNKNOWN"}:
            case.status = "MONITORING"
        elif view.stale or not observation["source_fresh"]:
            case.status = "RECHECK_REQUIRED"
        return outcome

    async def after_complete(session, job, _):
        case = await session.get(CaseRow, job.payload["case_id"])
        await queue_followup(session, case, delay_seconds=30, exclude_job=job.id)

    return {
        "operations_case_followup": Handler(
            run, retry_safe=True, apply=apply, after_complete=after_complete, before_claim=recover
        )
    }
