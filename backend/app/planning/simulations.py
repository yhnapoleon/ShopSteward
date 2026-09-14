"""Persist a quantity comparison in the existing owner-scoped result history.

Only WorkItem/WorkMessage/Command are written; a trial never creates a Mission,
Plan, Action, reservation, forecast renewal or ledger effect.
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.core.hashing import digest
from app.missions import repository as missions
from app.missions.models import InboundRow
from app.missions.schemas import MissionCreate
from app.operations.models import ForecastRow, OfferRow, ProductRow, SourceCursor, StockRow, Store
from app.operations.repository import get_state
from app.operations.schemas import Offer
from app.planning.engine import RULE_VERSION
from app.planning.evaluation import evaluate_candidates
from app.planning.schemas import InboundSnapshot, Policy
from app.planning.simulation_schemas import QuantitySimulation, QuantitySimulationInput
from app.planning.snapshot import FixedForecastProvider, source_fresh

REASONS = {
    "CASH_FLOOR_VIOLATION": "采购后可用现金低于底线",
    "MINIMUM_ORDER_QUANTITY": "不足供应商起订量",
    "PACK_SIZE_MISMATCH": "不满足整包装数量",
    "ARRIVAL_WINDOW_MISSED": "预计到货无法赶上本期需求",
    "TASK_QUANTITY_LIMIT": "超过本轮数量上限",
}


def yuan(value):
    return ("-" if value < 0 else "") + f"{abs(value) // 100}.{abs(value) % 100:02d}"


async def capture(session, store_id, body, settings):
    state = await get_state(session, store_id)
    if state.state_version != body.expected_state_version:
        raise AppError(409, "SIMULATION_STATE_CHANGED", "经营数据已变化，请刷新后重新试算。")
    cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == store_id))
    now = await session.scalar(select(func.clock_timestamp()))
    if not source_fresh(cursor, now, settings.source_stale_seconds):
        raise AppError(409, "DATA_STALE", "经营数据尚未同步，先刷新数据再试算。")
    stock = next((s for s in state.stocks if s.sku_id == body.sku_id), None)
    product = await session.get(ProductRow, (store_id, body.sku_id))
    offer_row = await session.get(OfferRow, (store_id, body.sku_id, body.supplier_id))
    if stock is None or product is None or offer_row is None:
        raise AppError(422, "SIMULATION_INPUT_MISSING", "当前门店缺少这个商品的库存或供应商报价。")
    offer = Offer.model_validate(offer_row.document)
    if offer.currency != state.currency or not offer.valid_from <= now < offer.valid_until:
        raise AppError(409, "OFFER_EXPIRED", "报价尚未生效或已过期，更新报价后再试算。")
    if state.simulation_time is None:
        raise AppError(422, "SIMULATION_TIME_MISSING", "缺少经营时点，无法判断到货窗口。")
    forecast = None
    if body.remaining_demand is None:
        row = (
            await session.get(ForecastRow, (store_id, stock.sku_id, stock.forecast_version))
            if stock.forecast_version
            else None
        )
        if row is None or stock.remaining_demand is None:
            raise AppError(
                422, "FORECAST_UNAVAILABLE", "缺少当前需求依据，请填写明确的需求假设及期间。"
            )
        try:
            forecast, renewal = FixedForecastProvider().read(
                row, stock, state, cursor, now, settings.fixed_forecast_ttl_seconds
            )
            if renewal:
                raise ValueError("expired forecast")
        except (ValueError, TypeError, KeyError):
            raise AppError(
                409,
                "FORECAST_UNAVAILABLE",
                "当前需求依据已过期或不覆盖本期；请更新需求，或填写独立的需求假设。",
            ) from None
        demand, start, end, source = (
            forecast.remaining_demand,
            forecast.horizon_start,
            forecast.horizon_end,
            forecast.source,
        )
    else:
        demand, start, source = body.remaining_demand, state.simulation_time, "assumption"
        try:
            end = start + timedelta(days=body.horizon_days)
        except OverflowError:
            raise AppError(422, "SIMULATION_TIME_INVALID", "假设期间超出可计算范围。") from None
    rows = list(
        await session.scalars(
            select(InboundRow)
            .where(
                InboundRow.store_id == store_id,
                InboundRow.sku_id == stock.sku_id,
                InboundRow.ordered_qty > InboundRow.received_qty,
            )
            .order_by(InboundRow.action_id)
        )
    )
    if sum(r.ordered_qty - r.received_qty for r in rows) != stock.in_transit:
        raise AppError(409, "INBOUND_STATE_MISMATCH", "在途明细与库存尚未一致，请先完成回执核实。")
    inbound = [
        InboundSnapshot(
            action_id=r.action_id,
            sku_id=r.sku_id,
            remaining_quantity=r.ordered_qty - r.received_qty,
            expected_arrival_at=r.expected_arrival_at,
            eligible=r.expected_arrival_at is not None
            and state.simulation_time <= r.expected_arrival_at < end,
        )
        for r in rows
    ]
    # Browser numbers must remain exact. Never round money to fit a JSON/JS number.
    values = [
        state.cash_minor,
        state.reserved_cash_minor,
        state.available_cash_minor,
        state.receivables_minor,
        offer.unit_price_minor,
        *(q * offer.unit_price_minor for q in body.candidate_quantities),
        demand,
        state.state_version,
        cursor.last_sequence,
        offer.minimum_order_quantity,
        offer.pack_size,
        offer.lead_time_seconds,
        *(q for s in state.stocks for q in (s.on_hand, s.in_transit, s.remaining_demand or 0)),
    ]
    if max(values) > 2**53 - 1:
        raise AppError(422, "SIMULATION_RANGE_EXCEEDED", "金额或数量超出当前试算的精确显示范围。")
    return QuantitySimulationInput(
        state=state,
        sku_id=stock.sku_id,
        product_name=product.document["name"],
        policy=Policy(
            cash_floor_minor=body.cash_floor_minor,
            candidate_quantities=body.candidate_quantities,
            supplier_id=body.supplier_id,
        ),
        remaining_demand=demand,
        horizon_start=start,
        horizon_end=end,
        demand_source=source,
        forecast_id=forecast.forecast_id if forecast else None,
        forecast_version=forecast.forecast_version if forecast else None,
        forecast_valid_until=forecast.valid_until if forecast else None,
        offer=offer,
        inbound_items=inbound,
        eligible_inbound_qty=sum(r.remaining_quantity for r in inbound if r.eligible),
        source_sequence=cursor.last_sequence,
        source_type=cursor.source,
        evaluated_at=now,
        source_fresh_until=cursor.last_success_at
        + timedelta(seconds=settings.source_stale_seconds),
    )


async def stale_reasons(session, calculation, settings):
    value = calculation.input
    store = await session.get(Store, value.state.store_id)
    cursor = await session.scalar(
        select(SourceCursor).where(SourceCursor.store_id == value.state.store_id)
    )
    now = await session.scalar(select(func.clock_timestamp()))
    reasons = []
    if store is None or store.state_version != value.state.state_version:
        reasons.append("经营状态已变化")
    if not source_fresh(cursor, now, settings.source_stale_seconds):
        reasons.append("经营来源待同步")
    if calculation.valid_until <= now:
        reasons.append("试算所用依据已过期")
    offer = await session.get(
        OfferRow, (value.state.store_id, value.sku_id, value.offer.supplier_id)
    )
    if offer is None or Offer.model_validate(offer.document) != value.offer:
        reasons.append("供应商报价已变化")
    if value.forecast_version:
        stock = await session.get(StockRow, (value.state.store_id, value.sku_id))
        if stock is None or stock.forecast_version != value.forecast_version:
            reasons.append("需求依据已变化")
    return reasons


async def create(session, principal, store_id, body, key, settings):
    from app.work_items import repository as work
    from app.work_items.models import WorkItem

    authorize_store(principal, store_id)
    if body.work_item_id:
        origin = await work.visible(session, principal, body.work_item_id)
        if origin.store_id != store_id:
            raise AppError(409, "SIMULATION_SCOPE_CONFLICT", "不能把试算转到另一门店。")
    await missions.lock_store(session, store_id)
    receipt, replay = await missions.command(
        session,
        principal.principal_id,
        "quantity_simulation",
        key,
        {"store_id": store_id, **body.model_dump()},
    )
    if replay:
        return await work.detail(
            session, await work.visible(session, principal, receipt.response["id"]), settings
        )
    existing = None
    if body.work_item_id:
        existing = await work.visible(session, principal, body.work_item_id, lock=True)
        if existing.store_id != store_id or not (
            existing.result and existing.result.get("calculation")
        ):
            raise AppError(
                409, "SIMULATION_SCOPE_CONFLICT", "只能在同一门店的原试算事项中继续比较。"
            )
        work.check_version(existing, body.expected_work_version)
    value = await capture(session, store_id, body, settings)
    candidates, recommended, arrival = evaluate_candidates(
        state=value.state,
        sku_id=value.sku_id,
        remaining_demand=value.remaining_demand,
        horizon_end=value.horizon_end,
        offer=value.offer,
        policy=value.policy,
        eligible_inbound_qty=value.eligible_inbound_qty,
    )
    calculation = QuantitySimulation(
        rule_version=RULE_VERSION,
        input_hash="sha256:" + digest(value.model_dump(mode="json")),
        input=value,
        candidates=candidates,
        recommended_candidate_id=recommended.id if recommended else None,
        expected_arrival_at=arrival,
        valid_until=min(
            value.evaluated_at + timedelta(seconds=settings.plan_ttl_seconds),
            value.offer.valid_until,
            value.forecast_valid_until or value.offer.valid_until,
        ),
        request=body,
    )
    summary = (
        f"在这些候选中，采购{recommended.quantity}件最合适："
        f"支出{yuan(recommended.spend_minor)}元，可用现金余{yuan(recommended.cash_after_minor)}元，"
        f"剩余缺口{recommended.shortage_qty}件。"
        if recommended
        else "当前所有候选均不满足约束，请调整现金底线、数量或补充有效报价后重算。"
    )
    explanation = (
        summary + "\n\n先排除不满足现金底线、起订量、包装及到货窗口的候选，"
        "再选择缺口最小、采购数量最少的可行项。"
    )
    assumptions = [
        f"现金底线：{yuan(body.cash_floor_minor)}元；本期需求：{value.remaining_demand}件。",
        f"期间：{value.horizon_start.isoformat()} 至 {value.horizon_end.isoformat()}。",
        "需求来自用户明确假设，未写入正式需求或预测。"
        if value.demand_source == "assumption"
        else f"需求来源：{value.demand_source}；版本：{value.forecast_version}。",
        "按期内可到货数量比较，假设可用在途和本次采购先于剩余销售；不模拟逐日销售、延迟回款或晚两天采购。",
        "不可行候选的缺口仅表示足量按时到货时的算术值，不能作为可执行的缺货承诺。",
        "支出只从当前可用现金扣算；待结算收入不计入可用现金。",
        "这是单商品数量试算；比较和保存不会预留资金、创建备货委托或发出采购。",
    ]
    if value.source_type == "simulation":
        assumptions.insert(0, "经营事实来自合成模拟环境，不是真实商店经营记录。")
    row = existing or WorkItem(
        id=str(uuid4()),
        store_id=store_id,
        principal_id=principal.principal_id,
        title=f"{value.product_name} · 补货数量试算"[:200],
        status="RESULT_READY",
        summary=summary,
        next_step="可调整条件重新试算。正式备货需要有效需求依据。"
        if value.demand_source == "assumption"
        else "可调整条件重新试算，或核对条件后建立备货委托。",
    )
    if existing:
        row.status, row.summary = "RESULT_READY", summary
        row.demonstration = False
        row.question = row.mission_request = None
        row.next_step = "本次比较已更新，之前结果保留在事项对话中；已有备货条件未改变。"
        work.release(row)
        await work.changed(session, row)
    else:
        session.add(row)
    await session.flush()
    # A hypothetical demand must never silently become a real forecast or policy.
    if value.demand_source != "assumption" and not row.mission_id:
        row.mission_request = MissionCreate(
            store_id=store_id,
            sku_id=value.sku_id,
            objective=f"{value.product_name}备货：现金至少保留{yuan(body.cash_floor_minor)}元，采购逐笔确认。",
            policy=value.policy,
            check_interval_seconds=30,
        ).model_dump(mode="json")
    await work.append(
        session,
        row,
        "user",
        "比较补货数量：" + "、".join(str(q) for q in body.candidate_quantities) + "件。",
    )
    result = {
        "kind": "analysis",
        "title": row.title,
        "content": explanation,
        "assumptions": assumptions,
        "references": [{"type": "store", "id": store_id, "label": "本次试算的经营快照"}],
        "columns": [
            "采购数量（件）",
            "支出（元）",
            "剩余可用现金（元）",
            "按时到货后缺口（件）",
            "判断",
        ],
        "rows": [
            [
                str(c.quantity),
                yuan(c.spend_minor),
                yuan(c.cash_after_minor),
                str(c.shortage_qty),
                "；".join(REASONS[r] for r in c.rejection_reasons)
                if not c.feasible
                else "本次推荐"
                if recommended and c.id == recommended.id
                else "可行",
            ]
            for c in candidates
        ],
        "calculation": calculation.model_dump(mode="json"),
    }
    message = await work.append(session, row, "assistant", explanation, result=result)
    row.result = message.result
    receipt.response = {"id": row.id}
    return await work.detail(session, row, settings)
