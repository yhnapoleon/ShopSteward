"""A case after its owner decided: it holds the item, settles, or asks for a new analysis.

Before the decision, any change to the inputs makes the options stale. After it, the
system's own purchase changes the state as well; that is the decision being carried out,
not a reason to analyze again. A decision stands until the case is resolved or ended.
"""

from sqlalchemy import or_, select

from app.execution.models import ActionRow
from app.missions.models import InboundRow, PlanRow
from app.missions.repository import timeline
from app.operations_cases.models import CaseRevisionRow, CaseRow
from app.operations_cases.repository import event
from app.planning.recovery.schemas import RecoveryArrival, RecoveryInput
from app.planning.recovery.solver import trajectory

TERMINAL = {"CANCELLED", "RESOLVED", "CLOSED"}
IN_FLIGHT = {"QUEUED", "EXECUTING", "UNKNOWN"}


async def purchases(session, case):
    """The purchases the case's adopted plans led to, oldest first."""
    return list(
        await session.scalars(
            select(ActionRow)
            .join(PlanRow, PlanRow.id == ActionRow.plan_id)
            .where(
                PlanRow.mission_id == case.mission_id,
                PlanRow.document["recovery_intent"]["case_id"].astext == case.id,
            )
            .order_by(ActionRow.created_at, ActionRow.id)
        )
    )


def short(action):
    """An accepted purchase the supplier filled only in part."""
    accepted = (action.receipt or {}).get("quantity", action.quantity)
    return action.status == "SUCCEEDED" and accepted < action.quantity


async def owning_case(session, mission):
    """The open case whose decision routine checks leave alone, if any.

    The owner has decided once a plan was adopted from the case (approved, rejected or
    still waiting) or waiting was chosen; that holds until the case ends.
    """
    return await session.scalar(
        select(CaseRow)
        .where(
            CaseRow.mission_id == mission.id,
            CaseRow.status.not_in(TERMINAL),
            or_(CaseRow.plan_id.is_not(None), CaseRow.status == "MONITORING"),
        )
        .order_by(CaseRow.updated_at.desc(), CaseRow.id)
        .limit(1)
        .with_for_update()
    )


async def recheck(session, case, mission, reason, said=None):
    """Ask the owner to analyze again and record why; `said` also goes on the timeline."""
    if case.status in TERMINAL:
        return
    if case.status != "RECHECK_REQUIRED":
        case.status = "RECHECK_REQUIRED"
        await event(session, case, "RECOVERY_RECHECK_REQUIRED", {"reason": reason})
    if said:
        await timeline(
            session,
            mission,
            "CASE_RECHECK_REQUIRED",
            said,
            references=[{"type": "artifact", "id": case.id}],
        )


async def rejected(session, mission, plan):
    """The owner turned down an adopted emergency plan; the case, not routine checks, goes on."""
    if (mission.planning_context or {}).get("plan_id") == plan.id:
        mission.planning_context = None
    case = await session.get(
        CaseRow, plan.document["recovery_intent"]["case_id"], with_for_update=True
    )
    if case is None or case.status in TERMINAL:
        return
    await event(session, case, "RECOVERY_PLAN_REJECTED", {"plan_id": plan.id})
    await timeline(
        session,
        mission,
        "CASE_DECISION",
        "应急方案未采用；应急事项结束前，例行检查不会另外建议下单。可以在事项里改选其他方案，或结束事项。",
        references=[{"type": "artifact", "id": case.id}],
    )


def lost(recovery):
    return sum(day.lost_qty for day in trajectory(recovery, 0, None))


async def settle(session, case, mission):
    """Resolve a case whose decision has played out, and record what it achieved."""
    if case.status != "MONITORING":
        return False
    actions = await purchases(session, case)
    if any(a.status in IN_FLIGHT for a in actions):
        return False
    bought = [a for a in actions if a.status == "SUCCEEDED"]
    inbound = [await session.get(InboundRow, (a.id, case.sku_id)) for a in bought]
    if bought:
        if any(row is None or row.received_qty < row.ordered_qty for row in inbound):
            return False
        # The problem as first analyzed, before any emergency purchase existed.
        plan = await session.get(PlanRow, bought[0].plan_id)
        base = RecoveryInput.model_validate(plan.document["input_snapshot"]["recovery"])
    else:
        # Waiting: the case waits for the original orders frozen in its analysis.
        revision = await session.get(CaseRevisionRow, (case.id, case.current_revision))
        if not revision.snapshot:
            return False
        base = RecoveryInput.model_validate(revision.snapshot["recovery"])
        if not base.arrivals:
            return False
        for arrival in base.arrivals:
            row = await session.get(InboundRow, (arrival.action_id, arrival.sku_id))
            if row is not None and row.received_qty < row.ordered_qty:
                return False
    # What was bought, at the dates the suppliers gave, against the same seven days.
    after = base.model_copy(
        update={
            "arrivals": [
                *base.arrivals,
                *[
                    RecoveryArrival(
                        action_id=row.action_id,
                        sku_id=row.sku_id,
                        ordered_qty=row.ordered_qty,
                        received_qty=0,
                        expected_arrival_at=row.expected_arrival_at,
                    )
                    for row in inbound
                ],
            ]
        }
    )
    outcome = {
        "path": "purchase" if bought else "waiting",
        "planned_qty": sum(a.quantity for a in bought),
        "purchased_qty": sum(row.ordered_qty for row in inbound),
        "received_qty": sum(row.received_qty for row in inbound),
        "spend_minor": sum(a.receipt["total_minor"] for a in bought),
        "lost_qty_before": lost(base),
        "lost_qty_after": lost(after),
        "action_ids": [a.id for a in bought],
    }
    case.status, case.followup_enabled = "RESOLVED", False
    await event(session, case, "CASE_RESOLVED", outcome)
    from app.operations_cases.jobs import cancel_followup

    await cancel_followup(session, case)
    spent, change = (
        f"花费 {outcome['spend_minor'] / 100:.2f} 元",
        f"七日预计缺货从 {outcome['lost_qty_before']} 件降到 {outcome['lost_qty_after']} 件。",
    )
    if bought and outcome["purchased_qty"] < outcome["planned_qty"]:
        said = (
            f"应急事项已解决：供应商确认的 {outcome['purchased_qty']} 件已全部到货"
            f"（订单 {outcome['planned_qty']} 件），{spent}；{change}"
        )
    elif bought:
        said = (
            f"应急事项已解决：应急补货 {outcome['purchased_qty']} 件已全部到货，{spent}；{change}"
        )
    else:
        said = (
            "应急事项已解决：原订单已全部到货，没有追加采购；"
            f"七日预计缺货 {outcome['lost_qty_before']} 件。"
        )
    await timeline(
        session,
        mission,
        "CASE_RESOLVED",
        said,
        references=[{"type": "artifact", "id": case.id}],
    )
    return True


async def settle_mission(session, mission):
    """After goods arrive: resolve this item's cases that were waiting for them."""
    cases = await session.scalars(
        select(CaseRow)
        .where(CaseRow.mission_id == mission.id, CaseRow.status == "MONITORING")
        .order_by(CaseRow.id)
        .with_for_update()
    )
    for case in list(cases):
        await settle(session, case, mission)
