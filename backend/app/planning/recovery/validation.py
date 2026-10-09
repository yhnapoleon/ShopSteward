from datetime import timedelta

from sqlalchemy import func, select

from app.core.errors import AppError
from app.forecast_v6.repository import read_current
from app.missions.models import InboundRow
from app.operations.models import OfferRow, SourceCursor, StockRow
from app.operations.schemas import Offer
from app.operations_cases.models import CaseRevisionRow, CaseRow
from app.planning.recovery.materialize import recovery_hash
from app.planning.recovery.schemas import RecoveryArrival
from app.planning.recovery.solver import solve
from app.planning.snapshot import source_fresh


def changed(code, message):
    raise AppError(409, code, message)


async def validate_sources(session, store, mission, snapshot, settings, now):
    if mission.status != "ACTIVE":
        changed("MISSION_NOT_ACTIVE", "Mission is not active")
    if (
        store.state_version != snapshot.state.state_version
        or store.simulation_time != snapshot.recovery.business_time
    ):
        changed("STATE_VERSION_CONFLICT", "Business state or clock changed; analyze a new revision")
    if (
        mission.mission_version != snapshot.mission_version
        or mission.policy_version != snapshot.policy_version
        or mission.policy != snapshot.policy.model_dump(mode="json")
        or mission.task_constraints != snapshot.task_constraints
    ):
        changed("MISSION_VERSION_CONFLICT", "Mission policy or constraints changed")
    cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == store.id))
    if not source_fresh(cursor, now, settings.source_stale_seconds):
        changed("DATA_STALE", "Source must be current before adopting, approving or sending")
    if snapshot.forecast.valid_until <= now:
        changed("PLAN_EXPIRED", "Daily demand evidence expired")
    stock = await session.get(StockRow, (store.id, mission.sku_id))
    if (
        stock.forecast_version != snapshot.forecast.forecast_version
        or stock.on_hand != snapshot.recovery.on_hand
        or store.cash_minor - store.reserved_cash_minor != snapshot.recovery.available_cash_minor
    ):
        changed("STATE_VERSION_CONFLICT", "Current cash, inventory or forecast differs")
    for expected in snapshot.recovery.offers:
        row = await session.get(OfferRow, (store.id, mission.sku_id, expected.supplier_id))
        if row is None or Offer.model_validate(row.document) != expected:
            changed("OFFER_VERSION_CONFLICT", "Supplier offer changed")
    arrivals = list(
        await session.scalars(
            select(InboundRow)
            .where(
                InboundRow.store_id == store.id,
                InboundRow.sku_id == mission.sku_id,
                InboundRow.ordered_qty > InboundRow.received_qty,
            )
            .order_by(InboundRow.action_id)
        )
    )
    if [RecoveryArrival.model_validate(a) for a in arrivals] != snapshot.recovery.arrivals:
        changed("INBOUND_VERSION_CONFLICT", "Original order remaining quantity or ETA changed")
    if snapshot.recovery.demand_source == "forecast_v6":
        current = await read_current(session, store.id, mission.sku_id, settings, now)
        if (
            not current["usable_for_planning"]
            or current["forecast"]["forecast_id"] != snapshot.recovery.demand_source_id
        ):
            changed("FORECAST_VERSION_CONFLICT", "Daily forecast is no longer eligible")


async def validate_recovery(session, store, mission, row, plan, settings):
    now = await session.scalar(select(func.clock_timestamp()))
    intent = plan.recovery_intent
    case = await session.get(CaseRow, intent.case_id)
    if (
        case is None
        or case.mission_id != mission.id
        or case.current_revision != intent.revision
        or case.status == "CANCELLED"
    ):
        changed("CASE_REVISION_CONFLICT", "Recovery intention changed")
    if (
        case.plan_id != row.id
        or not mission.planning_context
        or mission.planning_context.get("plan_id") != row.id
    ):
        changed("RECOVERY_INTENT_STALE", "This is no longer the active recovery plan")
    revision = await session.get(CaseRevisionRow, (case.id, case.current_revision))
    if revision.snapshot["recovery"] != plan.input_snapshot.recovery.model_dump(mode="json"):
        changed("PROPOSAL_INVALID", "Recovery input does not match the frozen revision")
    if min(row.expires_at, plan.expires_at) <= now:
        changed("PLAN_EXPIRED", "Recovery plan expired")
    if recovery_hash(row.document) != plan.proposal_hash:
        changed("PROPOSAL_HASH_CONFLICT", "Recovery proposal content changed")
    await validate_sources(session, store, mission, plan.input_snapshot, settings, now)
    result = solve(plan.input_snapshot.recovery)
    chosen = next((c for c in result.candidates if c.id == plan.selected_candidate_id), None)
    if (
        chosen is None
        or not chosen.feasible
        or not chosen.executable
        or chosen.quantity == 0
        or result.candidates != plan.candidates
    ):
        changed("PROPOSAL_INVALID", "Selected recovery candidate is not executable")
    offer = next(
        o for o in plan.input_snapshot.recovery.offers if o.supplier_id == chosen.supplier_id
    )
    if not offer.valid_from <= now < offer.valid_until:
        changed("OFFER_EXPIRED", "Selected supplier offer expired")
    purchase = plan.proposed_purchase
    if (
        purchase is None
        or purchase.store_id != store.id
        or purchase.sku_id != mission.sku_id
        or purchase.quantity != chosen.quantity
        or purchase.total_minor != chosen.spend_minor
        or purchase.supplier_id != chosen.supplier_id
        or purchase.unit_price_minor != offer.unit_price_minor
        or purchase.expected_arrival_at
        != store.simulation_time + timedelta(seconds=offer.lead_time_seconds)
        or intent.selected_candidate_id != chosen.id
        or intent.supplier_override != chosen.supplier_id
    ):
        changed("PROPOSAL_INVALID", "Purchase does not match the selected recovery candidate")
    return plan
