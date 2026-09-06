from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.core.errors import AppError
from app.execution.models import ActionRow, ApprovalRow
from app.execution.schemas import DecisionApproved, DecisionRejected, PurchaseRequest
from app.missions.models import PlanRow
from app.missions.repository import command, lock_mission, timeline
from app.operations.models import OfferRow, SourceCursor, StockRow
from app.operations.repository import digest
from app.planning.canonical import canonical
from app.planning.engine import build_plan, proposal_hash
from app.planning.schemas import Plan
from app.planning.snapshot import source_fresh
from app.scheduling.models import Job
from app.scheduling.repository import enqueue

PENDING = {"QUEUED", "EXECUTING", "UNKNOWN"}


def conflict(code, message):
    return AppError(409, code, message)


async def lock_action(session, action_id):
    initial = await session.get(ActionRow, action_id)
    if initial is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Action does not exist")
    store, mission = await lock_mission(session, initial.mission_id)
    plan = await session.get(PlanRow, initial.plan_id, with_for_update=True)
    action = await session.scalar(
        select(ActionRow)
        .where(ActionRow.id == action_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return store, mission, plan, action


async def validate_current(session, store, mission, row, settings):
    plan = Plan.model_validate(row.document)
    snapshot = plan.input_snapshot
    now = await session.scalar(select(func.clock_timestamp()))
    if mission.status != "ACTIVE":
        raise conflict("MISSION_NOT_ACTIVE", "Mission must be active")
    if store.state_version != plan.state_version:
        raise conflict("STATE_VERSION_CONFLICT", "State changed since this proposal")
    if (
        mission.mission_version != snapshot.mission_version
        or mission.policy_version != plan.policy_version
        or mission.policy != snapshot.policy.model_dump(mode="json")
    ):
        raise conflict("MISSION_VERSION_CONFLICT", "Mission policy changed")
    if (
        min(
            row.expires_at,
            plan.expires_at,
            snapshot.forecast.valid_until,
            snapshot.offer.valid_until,
        )
        <= now
    ):
        raise conflict("PLAN_EXPIRED", "Proposal inputs expired")
    cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == store.id))
    if not source_fresh(cursor, now, settings.source_stale_seconds):
        raise conflict("DATA_STALE", "Source must be caught up before approving or sending")
    if proposal_hash(row.document) != plan.proposal_hash:
        raise conflict("PROPOSAL_HASH_CONFLICT", "Stored proposal content changed")
    purchase = plan.proposed_purchase
    if purchase is None:
        raise AppError(422, "NO_PURCHASE_PROPOSED", "This check proposes no purchase")
    expected = build_plan(
        plan.mission_id, plan.plan_version, snapshot, ttl_seconds=settings.plan_ttl_seconds
    )
    if expected.candidates != plan.candidates or expected.proposed_purchase != purchase:
        raise conflict(
            "PROPOSAL_INVALID", "Purchase does not match the deterministic recommendation"
        )
    if purchase.store_id != store.id or purchase.sku_id != mission.sku_id:
        raise conflict("PROPOSAL_INVALID", "Purchase scope does not match Mission")
    offer = await session.get(OfferRow, (store.id, mission.sku_id, purchase.supplier_id))
    stock = await session.get(StockRow, (store.id, mission.sku_id))
    if (
        offer is None
        or canonical(offer.document) != canonical(snapshot.offer.model_dump(mode="json"))
        or stock.forecast_version != plan.forecast_version
    ):
        raise conflict("STATE_VERSION_CONFLICT", "Current offer or forecast differs")
    arrival = store.simulation_time + timedelta(seconds=snapshot.offer.lead_time_seconds)
    if arrival >= snapshot.forecast.horizon_end:
        raise AppError(
            422, "ARRIVAL_WINDOW_MISSED", "Purchase cannot arrive within the forecast horizon"
        )
    if (
        store.cash_minor - store.reserved_cash_minor - purchase.total_minor
        < snapshot.policy.cash_floor_minor
    ):
        raise AppError(422, "CASH_FLOOR_VIOLATION", "Purchase violates the cash floor")
    return plan


async def queue_action(session, action, *, exclude_job=None):
    active = await session.scalar(
        select(Job)
        .where(
            Job.job_type.in_(["execute_purchase", "reconcile_action"]),
            Job.payload["action_id"].astext == action.id,
            Job.status.in_(["READY", "RUNNING", "RETRY_WAIT"]),
            Job.id != exclude_job if exclude_job else True,
        )
        .with_for_update()
    )
    if active:
        return active
    kind = "execute_purchase" if action.status == "QUEUED" else "reconcile_action"
    job = await enqueue(
        session,
        job_type=kind,
        store_id=action.store_id,
        mission_id=action.mission_id,
        dedup_key=digest(["action-job", action.id, str(uuid4())]),
        payload={"action_id": action.id},
    )
    if action.next_attempt_at:
        job.available_at = job.scheduled_for = action.next_attempt_at
    job.trigger_source = "APPROVAL" if kind == "execute_purchase" else "AT"
    return job


async def decide(session, plan_id, body, principal, key, settings):
    initial = await session.get(PlanRow, plan_id)
    if initial is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Plan does not exist")
    store, mission = await lock_mission(session, initial.mission_id)
    row = await session.scalar(
        select(PlanRow)
        .where(PlanRow.id == plan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    receipt, replay = await command(
        session, principal, "decide_plan", key, {"plan_id": plan_id, **body.model_dump()}
    )
    if replay:
        model = DecisionApproved if receipt.response["decision"] == "approve" else DecisionRejected
        return model.model_validate(receipt.response)
    if row.status != "PENDING_APPROVAL" or mission.current_plan_id != plan_id:
        raise conflict("PLAN_ALREADY_DECIDED", "Plan is no longer available for decision")
    if (
        body.expected_plan_version != row.plan_version
        or body.expected_state_version != row.state_version
    ):
        raise conflict("PLAN_VERSION_CONFLICT", "Decision versions do not match the proposal")
    if body.proposal_hash != row.document["proposal_hash"]:
        raise conflict("PROPOSAL_HASH_CONFLICT", "Decision hash does not match the proposal")
    now = await session.scalar(select(func.clock_timestamp()))
    if body.decision == "approve":
        plan = await validate_current(session, store, mission, row, settings)
        if store.active_action_id is not None:
            raise conflict("ACTION_IN_PROGRESS", "Another purchase is unresolved for this store")
    approval = ApprovalRow(
        id=str(uuid4()),
        plan_id=plan_id,
        actor_id=principal,
        decision=body.decision,
        proposal_hash=body.proposal_hash,
        state_version=row.state_version,
        decided_at=now,
    )
    session.add(approval)
    await session.flush()
    if body.decision == "reject":
        row.status = "REJECTED"
        response = DecisionRejected(
            plan_id=plan_id, decision="reject", action_id=None, job_run_id=None
        )
    else:
        identifier = str(uuid4())
        purchase = plan.proposed_purchase
        request = PurchaseRequest(
            action_id=identifier,
            scenario_run_id=store.scenario_run_id,
            store_id=store.id,
            sku_id=purchase.sku_id,
            supplier_id=purchase.supplier_id,
            quantity=purchase.quantity,
            expected_total_minor=purchase.total_minor,
            currency=purchase.currency,
        )
        action = ActionRow(
            id=identifier,
            store_id=store.id,
            mission_id=mission.id,
            plan_id=plan_id,
            approval_id=approval.id,
            status="QUEUED",
            purchase_snapshot=purchase.model_dump(mode="json"),
            request_snapshot=request.model_dump(mode="json"),
            created_at=now,
            updated_at=now,
        )
        session.add(action)
        row.status = "APPROVED"
        store.active_action_id = mission.current_action_id = identifier
        await session.flush()
        job = await queue_action(session, action)
        response = DecisionApproved(
            plan_id=plan_id, decision="approve", action_id=identifier, job_run_id=job.id
        )
    await timeline(
        session,
        mission,
        "PLAN_DECIDED",
        body.decision,
        actor=principal,
        references=[{"type": "plan", "id": plan_id, "version": str(row.plan_version)}],
    )
    receipt.response = response.model_dump(mode="json")
    return response
