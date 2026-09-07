from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.core.hashing import digest
from app.core.pagination import decode_cursor, encode_cursor
from app.missions.models import MissionRow, PlanRow, ScheduleRow, TimelineRow
from app.missions.schemas import JobAccepted, Mission, MissionList, Schedule
from app.operations.models import Command, OfferRow, StockRow, Store
from app.planning.schemas import Plan, PlanList
from app.scheduling.models import Job
from app.scheduling.repository import enqueue


async def command(session, principal, operation, key, content):
    identifier = digest([operation, principal, key])
    content_hash = digest(content)
    fresh = await session.scalar(
        insert(Command)
        .values(id=identifier, content_hash=content_hash, response={})
        .on_conflict_do_nothing()
        .returning(Command.id)
    )
    receipt = await session.get(Command, identifier)
    if receipt.content_hash != content_hash:
        raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Command key has different content")
    return receipt, fresh is None


async def lock_store(session, store_id):
    store = await session.scalar(
        select(Store)
        .where(Store.id == store_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if store is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Store does not exist")
    return store


async def lock_mission(session, mission_id):
    row = await session.get(MissionRow, mission_id)
    if row is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Mission does not exist")
    store = await lock_store(session, row.store_id)
    mission = await session.scalar(
        select(MissionRow)
        .where(MissionRow.id == mission_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return store, mission


async def timeline(session, mission, kind, summary, *, actor=None, references=None):
    event_id = str(uuid4())
    session.add(
        TimelineRow(
            id=event_id,
            mission_id=mission.id,
            type=kind,
            summary=summary,
            actor_type="USER" if actor else "SYSTEM",
            actor_id=actor,
            references=references or [],
            created_at=await session.scalar(select(func.clock_timestamp())),
        )
    )
    if kind in {
        "PLAN_CREATED",
        "PLAN_REVISED",
        "ACTION_SUCCEEDED",
        "ACTION_FAILED",
        "PURCHASE_RECEIVED",
        "MISSION_COMPLETED",
        "MISSION_CANCELLED",
        "ALERT_OPENED",
        "ALERT_ESCALATED",
        "ALERT_RESOLVED",
    }:
        from app.agent_bridge.triggers import record_event

        await record_event(session, mission.id, event_id, references or [])


def mission_dto(row, schedule):
    fields = {key: getattr(row, key) for key in Mission.model_fields if key != "schedule"}
    return Mission(**fields, schedule=Schedule.model_validate(schedule))


async def read_mission(session, mission_id):
    pair = (
        await session.execute(
            select(MissionRow, ScheduleRow)
            .join(ScheduleRow, ScheduleRow.mission_id == MissionRow.id)
            .where(MissionRow.id == mission_id)
            .execution_options(populate_existing=True)
        )
    ).first()
    if pair is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Mission does not exist")
    return mission_dto(*pair)


async def queue_check(
    session,
    store,
    mission,
    *,
    key,
    manual=False,
    trigger_source="EVENT",
    scheduled_for=None,
):
    active = await session.scalar(
        select(Job)
        .where(
            Job.mission_id == mission.id,
            Job.job_type == "check_mission",
            Job.status.in_(["READY", "RUNNING", "RETRY_WAIT"]),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if manual:
        mission.manual_check_requested = True
    if active:
        active.target_state_version = max(active.target_state_version or 0, store.state_version)
        active.target_mission_version = max(
            active.target_mission_version or 0, mission.mission_version
        )
        if active.status == "RUNNING":
            mission.recheck_required = True
        elif manual or trigger_source == "EVENT":
            active.available_at = await session.scalar(select(func.clock_timestamp()))
        return JobAccepted(job_run_id=active.id, status=active.status, merged=True)
    job = await enqueue(
        session,
        job_type="check_mission",
        dedup_key=digest(["check", key]),
        store_id=store.id,
        mission_id=mission.id,
        payload={"mission_id": mission.id},
        trigger_source="MANUAL" if manual else trigger_source,
        scheduled_for=scheduled_for,
        target_state_version=store.state_version,
        target_mission_version=mission.mission_version,
    )
    return JobAccepted(job_run_id=job.id, status=job.status, merged=False)


async def wake_store_missions(session, store, *, key):
    """Caller holds the store lock; all Missions consume store-level cash/version."""
    missions = list(
        await session.scalars(
            select(MissionRow)
            .where(MissionRow.store_id == store.id, MissionRow.status == "ACTIVE")
            .order_by(MissionRow.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for mission in missions:
        await queue_check(session, store, mission, key=f"{key}:{mission.id}")


async def create_mission(session, body, principal, key):
    store = await lock_store(session, body.store_id)
    receipt, replay = await command(session, principal, "create_mission", key, body.model_dump())
    if replay:
        return Mission.model_validate(receipt.response)
    if (
        await session.get(StockRow, (body.store_id, body.sku_id)) is None
        or await session.get(OfferRow, (body.store_id, body.sku_id, body.policy.supplier_id))
        is None
    ):
        raise AppError(404, "RESOURCE_NOT_FOUND", "SKU or supplier offer does not exist")
    if await session.scalar(
        select(MissionRow.id).where(
            MissionRow.store_id == store.id,
            MissionRow.sku_id == body.sku_id,
            MissionRow.status.in_(["ACTIVE", "PAUSED"]),
        )
    ):
        raise AppError(409, "MISSION_ALREADY_EXISTS", "An open Mission already exists for this SKU")
    now = await session.scalar(select(func.clock_timestamp()))
    mission = MissionRow(
        id=str(uuid4()),
        store_id=store.id,
        sku_id=body.sku_id,
        objective=body.objective,
        status="ACTIVE",
        mission_version=1,
        policy=body.policy.model_dump(),
        policy_version="policy-1",
        completion_criteria="用户明确请求结束且无未决采购动作",
        created_at=now,
        updated_at=now,
    )
    session.add(mission)
    await session.flush()
    schedule = ScheduleRow(
        id=str(uuid4()),
        mission_id=mission.id,
        job_type="check_mission",
        trigger="INTERVAL",
        interval_seconds=body.check_interval_seconds,
        enabled=True,
        version=1,
        next_run_at=now + timedelta(seconds=body.check_interval_seconds),
    )
    session.add(schedule)
    await session.flush()
    await timeline(session, mission, "MISSION_CREATED", "Mission created", actor=principal)
    await queue_check(session, store, mission, key=mission.id)
    result = mission_dto(mission, schedule)
    receipt.response = result.model_dump(mode="json")
    return result


async def control_mission(session, mission_id, body, principal, key):
    store, mission = await lock_mission(session, mission_id)
    receipt, replay = await command(
        session, principal, "control_mission", key, {"mission_id": mission_id, **body.model_dump()}
    )
    if replay:
        return Mission.model_validate(receipt.response)
    if mission.mission_version != body.expected_mission_version:
        raise AppError(409, "MISSION_VERSION_CONFLICT", "Mission version has changed")
    allowed = {
        "pause": {"ACTIVE"},
        "resume": {"PAUSED"},
        "complete": {"ACTIVE", "PAUSED"},
        "cancel": {"ACTIVE", "PAUSED"},
    }
    if mission.status not in allowed[body.operation]:
        raise AppError(409, "INVALID_MISSION_TRANSITION", "Mission cannot perform this transition")
    if body.operation == "complete" and mission.current_action_id:
        raise AppError(
            409, "ACTION_IN_PROGRESS", "Resolve the outstanding action before this transition"
        )
    if body.operation == "cancel" and mission.current_action_id:
        from app.execution.accounting import close_action
        from app.execution.repository import lock_action

        _, _, _, action = await lock_action(session, mission.current_action_id)
        if action.status == "QUEUED":
            await close_action(
                session, store, mission, action, "CANCELLED", reason="MISSION_CANCELLED"
            )
        # A sent purchase is still reconciled even after the Mission is cancelled.
    mission.status = {
        "pause": "PAUSED",
        "resume": "ACTIVE",
        "complete": "COMPLETED",
        "cancel": "CANCELLED",
    }[body.operation]
    mission.mission_version += 1
    mission.updated_at = await session.scalar(select(func.clock_timestamp()))
    mission.recheck_required = mission.manual_check_requested = False
    if mission.current_plan_id:
        plan = await session.get(PlanRow, mission.current_plan_id, with_for_update=True)
        if plan and plan.status == "PENDING_APPROVAL":
            plan.status = "SUPERSEDED"
        mission.current_plan_id = None
    schedule = await session.scalar(
        select(ScheduleRow)
        .where(ScheduleRow.mission_id == mission.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    schedule.version += 1
    if mission.status in {"COMPLETED", "CANCELLED"}:
        schedule.enabled = False
    schedule.next_run_at = (
        mission.updated_at + timedelta(seconds=schedule.interval_seconds)
        if mission.status == "ACTIVE" and schedule.enabled
        else None
    )
    await timeline(session, mission, "MISSION_CONTROLLED", body.operation, actor=principal)
    if body.operation == "resume":
        await queue_check(session, store, mission, key=str(uuid4()), manual=True)
    else:
        await session.execute(
            update(Job)
            .where(
                Job.mission_id == mission.id,
                Job.job_type == "check_mission",
                Job.status.in_(["READY", "RETRY_WAIT"]),
            )
            .values(status="CANCELLED", finished_at=func.clock_timestamp())
        )
    await session.flush()
    result = await read_mission(session, mission.id)
    receipt.response = result.model_dump(mode="json")
    return result


async def update_schedule(session, mission_id, body, principal, key):
    _, mission = await lock_mission(session, mission_id)
    receipt, replay = await command(
        session,
        principal,
        "update_mission_schedule",
        key,
        {"mission_id": mission_id, **body.model_dump()},
    )
    if replay:
        return Schedule.model_validate(receipt.response)
    if mission.status in {"COMPLETED", "CANCELLED"}:
        raise AppError(409, "MISSION_TERMINAL", "A terminal Mission schedule cannot be changed")
    schedule = await session.scalar(
        select(ScheduleRow)
        .where(ScheduleRow.mission_id == mission.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if schedule.version != body.expected_schedule_version:
        raise AppError(409, "SCHEDULE_VERSION_CONFLICT", "Schedule version has changed")
    now = await session.scalar(select(func.clock_timestamp()))
    schedule.interval_seconds = body.interval_seconds
    schedule.enabled = body.enabled
    schedule.version += 1
    schedule.next_run_at = (
        now + timedelta(seconds=body.interval_seconds)
        if mission.status == "ACTIVE" and body.enabled
        else None
    )
    await session.flush()
    result = Schedule.model_validate(schedule)
    receipt.response = result.model_dump(mode="json")
    return result


async def request_check(session, mission_id, body, principal, key):
    store, mission = await lock_mission(session, mission_id)
    receipt, replay = await command(
        session,
        principal,
        "request_mission_check",
        key,
        {"mission_id": mission_id, **body.model_dump()},
    )
    if replay:
        return JobAccepted.model_validate(receipt.response)
    if mission.status != "ACTIVE":
        raise AppError(409, "MISSION_NOT_ACTIVE", "Mission must be active to request a check")
    result = await queue_check(session, store, mission, key=receipt.id, manual=True)
    await timeline(
        session,
        mission,
        "CHECK_REQUESTED",
        f"{body.reason or 'Manual check'}（任务{result.job_run_id}）",
        actor=principal,
        references=[{"type": "mission", "id": mission.id, "version": str(mission.mission_version)}],
    )
    receipt.response = result.model_dump(mode="json")
    return result


async def list_missions(session, store_id, status, cursor, limit):
    scope = ["missions", store_id, status]
    anchor = decode_cursor(cursor, scope)
    query = (
        select(MissionRow, ScheduleRow)
        .join(ScheduleRow, ScheduleRow.mission_id == MissionRow.id)
        .where(MissionRow.store_id == store_id)
    )
    if status:
        query = query.where(MissionRow.status == status)
    if anchor:
        query = query.where(tuple_(MissionRow.created_at, MissionRow.id) < anchor)
    rows = (
        await session.execute(
            query.order_by(MissionRow.created_at.desc(), MissionRow.id.desc()).limit(limit + 1)
        )
    ).all()
    return MissionList(
        items=[mission_dto(*row) for row in rows[:limit]],
        next_cursor=encode_cursor(scope, rows[limit - 1][0]) if len(rows) > limit else None,
    )


def plan_dto(row, now):
    status = "EXPIRED" if row.status == "PENDING_APPROVAL" and row.expires_at <= now else row.status
    return Plan.model_validate(row.document | {"status": status})


async def list_plans(session, mission_id, cursor, limit):
    scope = ["plans", mission_id]
    anchor = decode_cursor(cursor, scope)
    query = select(PlanRow).where(PlanRow.mission_id == mission_id)
    if anchor:
        query = query.where(tuple_(PlanRow.created_at, PlanRow.id) < anchor)
    rows = list(
        await session.scalars(
            query.order_by(PlanRow.created_at.desc(), PlanRow.id.desc()).limit(limit + 1)
        )
    )
    now = await session.scalar(select(func.clock_timestamp()))
    return PlanList(
        items=[plan_dto(row, now) for row in rows[:limit]],
        next_cursor=encode_cursor(scope, rows[limit - 1]) if len(rows) > limit else None,
    )
