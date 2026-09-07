from sqlalchemy import func, select

from app.core.errors import AppError
from app.missions import repository as missions
from app.missions.models import PlanRow
from app.operations.models import SourceCursor
from app.planning.engine import build_plan, input_hash
from app.planning.schemas import DecisionSnapshot
from app.planning.snapshot import source_fresh


async def evaluate(session, settings, mission, store, args, *, revise=False, actor=None):
    row = await session.get(PlanRow, args.plan_id, with_for_update=revise)
    if row is None or row.mission_id != mission.id:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Plan is not in this mission")
    now = await session.scalar(select(func.clock_timestamp()))
    snapshot = DecisionSnapshot.model_validate(row.document["input_snapshot"])
    cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == store.id))
    if (
        row.expires_at <= now
        or row.state_version != store.state_version
        or snapshot.mission_version != mission.mission_version
        or not source_fresh(cursor, now, settings.source_stale_seconds)
    ):
        raise AppError(
            409, "PLAN_INPUT_STALE", "Request a fresh check before evaluating or revising"
        )
    if mission.status != "ACTIVE" or mission.current_action_id:
        raise AppError(409, "MISSION_NOT_EDITABLE", "Mission is inactive or has a pending action")
    constraints = (
        {} if args.max_purchase_qty is None else {"max_purchase_qty": args.max_purchase_qty}
    )
    if revise:
        if (
            mission.mission_version != args.expected_mission_version
            or mission.current_plan_id != row.id
            or row.status != "PENDING_APPROVAL"
        ):
            raise AppError(
                409, "PLAN_VERSION_CONFLICT", "Only the current pending proposal can be revised"
            )
        mission.task_constraints = constraints
        mission.mission_version += 1
    snapshot = snapshot.model_copy(
        update={
            "task_constraints": constraints,
            "mission_version": mission.mission_version,
            "evaluated_at": now,
        }
    )
    draft = build_plan(
        mission.id, mission.plan_counter + 1, snapshot, ttl_seconds=settings.plan_ttl_seconds
    )
    if not revise:
        return {
            "hypothetical": True,
            "base_plan_id": row.id,
            "task_constraints": constraints,
            "candidates": [c.model_dump() for c in draft.candidates],
            "recommended_candidate_id": draft.recommended_candidate_id,
            "explanation": draft.explanation,
            "state_version": store.state_version,
        }
    row.status = "SUPERSEDED"
    new = PlanRow(
        id=draft.id,
        mission_id=mission.id,
        plan_version=draft.plan_version,
        state_version=draft.state_version,
        input_hash=input_hash(snapshot),
        status=draft.status,
        document=draft.model_dump(mode="json"),
        created_at=draft.created_at,
        expires_at=draft.expires_at,
    )
    session.add(new)
    mission.plan_counter = draft.plan_version
    mission.current_plan_id = draft.id
    mission.updated_at = now
    await missions.timeline(
        session,
        mission,
        "PLAN_REVISED",
        draft.explanation,
        actor=actor,
        references=[{"type": "plan", "id": draft.id, "version": str(draft.plan_version)}],
    )
    return draft.model_dump(mode="json")
