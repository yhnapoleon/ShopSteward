from dataclasses import dataclass

from app.alerts.schemas import AlertType, Severity
from app.planning.engine import arrival_at


@dataclass(frozen=True)
class Finding:
    type: AlertType
    severity: Severity
    summary: str
    facts: dict


def evaluate(snapshot, candidates):
    stock = next(s for s in snapshot.state.stocks if s.sku_id == snapshot.forecast.sku_id)
    shortage = max(
        0, snapshot.forecast.remaining_demand - stock.on_hand - snapshot.eligible_inbound_qty
    )
    cash = snapshot.state.available_cash_minor
    floor = snapshot.policy.cash_floor_minor
    facts = {"shortage_qty": shortage, "cash_floor_minor": floor, "available_cash_minor": cash}
    if snapshot.state.data_as_of:
        facts["data_as_of"] = snapshot.state.data_as_of.isoformat()
    findings = []
    if shortage:
        findings.append(
            Finding(
                "STOCKOUT_RISK",
                "CRITICAL" if stock.on_hand == 0 else "WARNING",
                f"预计缺货{shortage}件；尚未执行的采购建议未计入库存。",
                facts,
            )
        )
    offer = snapshot.offer
    needed = max(shortage, offer.minimum_order_quantity)
    needed = ((needed + offer.pack_size - 1) // offer.pack_size) * offer.pack_size
    arrival = arrival_at(snapshot)
    funding_gap = (
        shortage > 0
        and arrival is not None
        and arrival < snapshot.forecast.horizon_end
        and not any(c.feasible and c.shortage_qty == 0 for c in candidates)
        and cash - needed * offer.unit_price_minor < floor
    )
    if cash < floor or funding_gap:
        findings.append(
            Finding(
                "CASH_CONSTRAINT",
                "CRITICAL" if cash < floor else "WARNING",
                "可用现金低于底线。" if cash < floor else "保持现金底线时，资金不足以补齐缺口。",
                facts,
            )
        )
    return findings


def inconclusive(reason):
    return Finding("DATA_STALE", "WARNING", "当前数据不足以完成可靠检查。", {"reason": reason})
