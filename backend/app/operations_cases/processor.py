"""Actual source producer. Reads under the caller's store/Mission transaction lock."""

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.core.errors import AppError
from app.execution.models import ActionRow
from app.forecast_v6.repository import read_current
from app.missions.models import InboundRow
from app.operations.models import ForecastRow, OfferRow, SourceCursor, Store
from app.operations.repository import get_state
from app.operations.schemas import Offer
from app.planning.recovery.schemas import DailyDemand, RecoveryArrival, RecoveryInput
from app.planning.recovery.solver import allocate_daily
from app.planning.schemas import ForecastSnapshot, InboundSnapshot, Policy, RecoveryDecisionSnapshot
from app.planning.snapshot import source_fresh


async def capture_snapshot(session, case, revision, mission, settings):
    now = await session.scalar(select(func.clock_timestamp()))
    state = await get_state(session, case.store_id)
    cursor = await session.scalar(
        select(SourceCursor).where(SourceCursor.store_id == case.store_id)
    )
    if not source_fresh(cursor, now, settings.source_stale_seconds):
        raise AppError(409, "DATA_STALE", "Synchronize the business source before analysis")
    if state.simulation_time is None:
        raise AppError(422, "BUSINESS_TIME_REQUIRED", "Business clock is unavailable")
    stock = next(s for s in state.stocks if s.sku_id == case.sku_id)
    if stock.forecast_version is None:
        raise AppError(422, "FORECAST_UNAVAILABLE", "Current forecast projection is missing")
    forecast_row = await session.get(
        ForecastRow, (case.store_id, case.sku_id, stock.forecast_version)
    )
    if forecast_row is None:
        raise AppError(422, "FORECAST_UNAVAILABLE", "Current forecast source is missing")
    evidence = [
        {
            "id": case.store_id,
            "kind": "business_state",
            "version": str(state.state_version),
            "status": "verified_source",
            "summary": "当前库存、现金和已预留资金",
        }
    ]
    request = revision.inputs
    daily = request.get("daily_demand")
    source, source_id = "user_scenario", f"{case.id}:{revision.revision}"
    valid_until = now + timedelta(seconds=settings.plan_ttl_seconds)
    if daily is None:
        current = await read_current(session, case.store_id, case.sku_id, settings, now)
        if not current["usable_for_planning"]:
            raise AppError(
                422,
                "DAILY_DEMAND_REQUIRED",
                "Provide seven explicit daily demand buckets or an eligible v6 forecast",
            )
        document = current["forecast"]
        values = allocate_daily(
            [d["quantity"] for d in document["daily_predictions"]], document["predicted_quantity"]
        )
        daily = [
            {
                "settlement_at": state.simulation_time + timedelta(days=i + 1, seconds=-1),
                "demand_qty": amount,
            }
            for i, amount in enumerate(values)
        ]
        source, source_id = "forecast_v6", document["forecast_id"]
        valid_until = min(valid_until, datetime.fromisoformat(document["valid_until"]))
    daily = [DailyDemand.model_validate(d) for d in daily]
    evidence.append(
        {
            "id": source_id,
            "kind": "daily_demand",
            "version": str(revision.revision),
            "status": "user_assumption" if source == "user_scenario" else "verified_source",
            "summary": "显式七日日需求情景" if source == "user_scenario" else "已启用的 v6 日预测",
        }
    )
    rows = list(
        await session.scalars(
            select(OfferRow)
            .where(OfferRow.store_id == case.store_id, OfferRow.sku_id == case.sku_id)
            .order_by(OfferRow.supplier_id)
        )
    )
    selected_ids = request.get("supplier_ids")
    if selected_ids:
        rows = [r for r in rows if r.supplier_id in selected_ids]
        if len(rows) != len(set(selected_ids)):
            raise AppError(422, "OFFER_UNAVAILABLE", "A selected supplier has no structured offer")
    if len(rows) > 3:
        raise AppError(422, "OFFER_SELECTION_REQUIRED", "Select at most three supplier offers")
    offers = [Offer.model_validate(r.document) for r in rows]
    for offer in offers:
        evidence.append(
            {
                "id": offer.supplier_id,
                "kind": "supplier_offer",
                "version": offer.offer_version,
                "status": "verified_source",
                "summary": "业务源结构化报价，适用性在候选中逐项检查",
            }
        )
    inbound = list(
        await session.scalars(
            select(InboundRow)
            .where(
                InboundRow.store_id == case.store_id,
                InboundRow.sku_id == case.sku_id,
                InboundRow.ordered_qty > InboundRow.received_qty,
            )
            .order_by(InboundRow.action_id)
        )
    )
    if sum(a.ordered_qty - a.received_qty for a in inbound) != stock.in_transit:
        raise AppError(409, "INBOUND_STATE_MISMATCH", "Inbound orders do not reconcile to stock")
    arrivals = [RecoveryArrival.model_validate(a) for a in inbound]
    for arrival in arrivals:
        evidence.append(
            {
                "id": arrival.action_id,
                "kind": "inbound_order",
                "version": str(state.state_version),
                "status": "verified_source" if arrival.expected_arrival_at else "unresolved",
                "summary": f"未到货 {arrival.ordered_qty - arrival.received_qty} 件；原订单保留",
            }
        )
    # A prior elapsed ETA is overdue, not an arrival already included in today's inventory.
    limits = [
        v
        for v in (request.get("max_purchase_qty"), mission.task_constraints.get("max_purchase_qty"))
        if v is not None
    ]
    store = await session.get(Store, case.store_id)
    previous_action = (
        await session.scalar(select(ActionRow).where(ActionRow.plan_id == case.plan_id))
        if case.plan_id
        else None
    )
    recovery = RecoveryInput(
        store_id=case.store_id,
        sku_id=case.sku_id,
        on_hand=stock.on_hand,
        available_cash_minor=state.available_cash_minor,
        cash_floor_minor=mission.policy["cash_floor_minor"],
        budget_minor=request["budget_minor"],
        max_purchase_qty=min(limits) if limits else None,
        daily_demand=daily,
        demand_source=source,
        demand_source_id=source_id,
        arrivals=arrivals,
        offers=offers,
        business_time=state.simulation_time,
        evaluated_at=now,
        executable=True,
        unresolved_action_id=store.active_action_id or mission.current_action_id,
        completed_purchase_action_id=(
            previous_action.id
            if previous_action and previous_action.status == "SUCCEEDED"
            else None
        ),
    )
    # The inherited fields preserve existing read-only Plan consumers. Execution dispatches by kind.
    base_offer = next((o for o in offers if o.supplier_id == mission.policy["supplier_id"]), None)
    if base_offer is None:
        original = await session.get(
            OfferRow, (case.store_id, case.sku_id, mission.policy["supplier_id"])
        )
        if original is None:
            raise AppError(422, "OFFER_UNAVAILABLE", "Mission supplier source is missing")
        base_offer = Offer.model_validate(original.document)
    snapshot = RecoveryDecisionSnapshot(
        snapshot_version="decision-v1",
        state=state,
        mission_version=mission.mission_version,
        policy=Policy.model_validate(mission.policy),
        task_constraints=mission.task_constraints,
        policy_version=mission.policy_version,
        forecast=ForecastSnapshot(
            forecast_id=source_id,
            forecast_version=stock.forecast_version,
            store_id=case.store_id,
            sku_id=case.sku_id,
            remaining_demand=sum(d.demand_qty for d in daily),
            unit="piece",
            data_as_of=now,
            source_sequence=cursor.last_sequence,
            horizon_start=state.simulation_time,
            horizon_end=daily[-1].settlement_at + timedelta(seconds=1),
            valid_until=valid_until,
            source="manual" if source == "user_scenario" else "model",
            model_name=source,
            model_version=source_id,
            assumptions=[
                "Daily settlement model; sales cash receipts are not forecast.",
                "Existing accepted orders remain; only unreceived quantities are counted.",
            ],
        ),
        offer=base_offer,
        inbound_items=[
            InboundSnapshot(
                action_id=a.action_id,
                sku_id=a.sku_id,
                remaining_quantity=a.ordered_qty - a.received_qty,
                expected_arrival_at=a.expected_arrival_at,
                eligible=a.expected_arrival_at is not None
                and state.simulation_time <= a.expected_arrival_at <= daily[-1].settlement_at,
            )
            for a in arrivals
        ],
        eligible_inbound_qty=sum(
            a.ordered_qty - a.received_qty
            for a in arrivals
            if a.expected_arrival_at is not None
            and state.simulation_time <= a.expected_arrival_at <= daily[-1].settlement_at
        ),
        rule_version="recovery_solver_v1",
        evaluated_at=now,
        last_successful_sync_at=cursor.last_success_at,
        source_fresh_until=cursor.last_success_at
        + timedelta(seconds=settings.source_stale_seconds),
        recovery=recovery,
    )
    return snapshot, evidence
