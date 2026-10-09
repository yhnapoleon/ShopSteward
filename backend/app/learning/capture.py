"""Business-owned projections, captured in the caller's transaction."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.learning.outbox import append
from app.learning.schemas import LearningEvent, LearningScope
from app.operations.models import Store


async def case_event(session, row, kind):
    if not session.info.get("learning_enabled"):
        return
    from app.operations_cases.models import CaseRevisionRow

    revision = await session.get(CaseRevisionRow, (row.id, row.current_revision))
    store = await session.get(Store, row.store_id)
    now = row.updated_at
    # Business date uses simulation clock; evidence availability always uses wall clock.
    observed = store.simulation_time or now
    payload = {
        "case_id": row.id,
        "mission_id": row.mission_id,
        "case_revision": row.current_revision,
        "business_date": observed.date().isoformat(),
        "status": row.status,
        "plan_id": row.plan_id,
        "proposal_id": row.proposal_id,
        "business_status": "pending",
        "inputs": {
            k: v
            for k, v in (revision.inputs if revision else {}).items()
            if k in {"budget_minor", "max_purchase_qty", "supplier_ids", "daily_demand"}
        },
    }
    return await append(
        session,
        scope=LearningScope(principal_id=row.owner_id, store_id=row.store_id),
        event=LearningEvent(
            source_kind="case",
            source_id=row.id,
            source_version=row.event_seq,
            event_type=kind,
            intent_key="case:" + row.id,
            task_family="supply_delay_recovery",
            observed_at=min(observed, now),
            available_at=now,
            payload=payload,
        ),
    )


async def explicit_memory_change(session, principal_id, store_id):
    if not session.info.get("learning_enabled"):
        return
    from app.learning.lifecycle import suspend_scope
    from app.learning.repository import policy

    scope = LearningScope(principal_id=principal_id, store_id=store_id)
    pol = await policy(session, scope, lock=True)
    # Revoking inferred advice is conservative when semantic dependency is not yet proven.
    pol.version += 1
    pol.enabled_at = datetime.now(UTC) if pol.mode != "off" else None
    await suspend_scope(session, pol.id, "explicit_preference_changed")


async def mission_event(session, mission, kind, event_id, actor, references):
    if not session.info.get("learning_enabled"):
        return
    from app.execution.models import ActionRow
    from app.learning.policy import business_outcome
    from app.missions.models import InboundRow, PlanRow, TimelineRow
    from app.operations_cases.models import CaseRow

    now = datetime.now(UTC)
    store = await session.get(Store, mission.store_id)
    observed = store.simulation_time or now
    owner = await session.scalar(
        select(TimelineRow.actor_id).where(
            TimelineRow.mission_id == mission.id, TimelineRow.type == "MISSION_CREATED"
        )
    )
    if not owner and kind == "MISSION_CREATED":
        owner = actor
    intent = "mission:" + mission.id
    family = "replenishment"
    payload = {
        "mission_id": mission.id,
        "business_date": observed.date().isoformat(),
        "state_version": store.state_version,
        "mission_version": mission.mission_version,
        "business_status": "pending",
        "actor_id": actor,
    }
    event_type = {
        "PLAN_CREATED": "PLAN_READY",
        "PLAN_REVISED": "PLAN_READY",
        "MISSION_CANCELLED": "CANCELLED",
    }.get(kind, kind)
    if kind == "MISSION_CONTROLLED" and mission.status == "CANCELLED":
        event_type = "CANCELLED"
    if kind in {"PLAN_CREATED", "PLAN_REVISED"}:
        plan = (
            await session.get(PlanRow, mission.current_plan_id) if mission.current_plan_id else None
        )
        if plan and plan.document.get("recovery_intent"):
            return  # Recovery Case owns this intent; do not count the same proposal twice.
        payload["plan_id"] = mission.current_plan_id
    if kind.startswith("ACTION_") or kind == "PURCHASE_RECEIVED":
        action_id = next(
            (r["id"] for r in references if r.get("type") == "action"), mission.current_action_id
        )
        action = await session.get(ActionRow, action_id) if action_id else None
        if not action:
            return
        case = await session.scalar(select(CaseRow).where(CaseRow.plan_id == action.plan_id))
        if case:
            owner, intent, family = case.owner_id, "case:" + case.id, "supply_delay_recovery"
        inbound = await session.get(InboundRow, (action.id, mission.sku_id))
        received = inbound.received_qty if inbound else 0
        ordered = inbound.ordered_qty if inbound else action.quantity
        payload.update(
            action_id=action.id,
            execution_status=action.status,
            business_status=business_outcome(action.status, received=received, ordered=ordered),
            metrics={"received_qty": received, "ordered_qty": ordered},
        )
        event_type = "EXECUTION_OBSERVED"
    if not owner:
        return
    return await append(
        session,
        scope=LearningScope(principal_id=owner, store_id=mission.store_id),
        event=LearningEvent(
            source_kind="mission",
            source_id=event_id,
            source_version=1,
            event_type=event_type,
            intent_key=intent,
            task_family=family,
            observed_at=min(observed, now),
            available_at=now,
            payload=payload,
        ),
    )


async def work_result(session, row, result, demonstration):
    if (
        not session.info.get("learning_enabled")
        or demonstration
        or row.demonstration
        or row.mission_id
    ):
        return
    if not result or not result.get("references"):
        return
    family = {"quotation": "quotation", "brief": "business_review"}.get(
        result.get("kind"), "unclassified"
    )
    now = datetime.now(UTC)
    return await append(
        session,
        scope=LearningScope(principal_id=row.principal_id, store_id=row.store_id),
        event=LearningEvent(
            source_kind="work_item",
            source_id=row.id,
            source_version=row.version,
            event_type="RESULT_READY",
            intent_key="work:" + row.id,
            task_family=family,
            observed_at=now,
            available_at=now,
            payload={
                "kind": result.get("kind"),
                "references": result["references"],
                "business_status": "pending",
            },
        ),
    )
