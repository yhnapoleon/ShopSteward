"""Bounded enumeration with integer cash and explicit daily demand settlement."""

from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from app.planning.recovery.schemas import DailyBalance, RecoveryCandidate, SolverResult

MAX_BIGINT = 9223372036854775807


class SearchSpaceExceeded(ValueError):
    pass


def allocate_daily(values, total):
    values = [Decimal(str(v)) for v in values]
    if len(values) != 7 or any(not v.is_finite() or v < 0 for v in values):
        raise ValueError("Seven finite nonnegative daily predictions are required")
    if type(total) is not int or total < 0:
        raise ValueError("Total must be a nonnegative integer")
    # Existing v6 persists ceil(total_quantity_raw), not nearest-integer rounding.
    if int(sum(values).quantize(Decimal("1"), rounding=ROUND_CEILING)) != total:
        raise ValueError("Daily predictions do not match persisted total")
    floors = [int(v.to_integral_value(rounding=ROUND_FLOOR)) for v in values]
    remainder = total - sum(floors)
    if not 0 <= remainder <= 7:
        raise ValueError("Invalid allocation remainder")
    for index in sorted(range(7), key=lambda i: (-(values[i] - floors[i]), i))[:remainder]:
        floors[index] += 1
    return floors


def trajectory(snapshot, quantity, arrival):
    stock = snapshot.on_hand
    daily = []
    pending = list(snapshot.arrivals)
    proposed = quantity
    for demand in snapshot.daily_demand:
        due = [
            a
            for a in pending
            if a.expected_arrival_at is not None
            and snapshot.business_time <= a.expected_arrival_at <= demand.settlement_at
        ]
        existing = sum(a.ordered_qty - a.received_qty for a in due)
        pending = [a for a in pending if a not in due]
        received = proposed if arrival is not None and arrival <= demand.settlement_at else 0
        proposed -= received
        available = stock + existing + received
        served = min(available, demand.demand_qty)
        stock = available - served
        daily.append(
            DailyBalance(
                **demand.model_dump(),
                existing_arrivals=existing,
                proposed_arrivals=received,
                served_qty=served,
                lost_qty=demand.demand_qty - served,
                end_stock=stock,
            )
        )
    return daily


def solve(snapshot):
    candidates = []

    def add(offer, quantity):
        spend = quantity * offer.unit_price_minor if offer else 0
        reasons = []
        arrival = None
        if offer:
            try:
                arrival = snapshot.business_time + timedelta(seconds=offer.lead_time_seconds)
            except OverflowError:
                pass
            if offer.sku_id != snapshot.sku_id:
                reasons.append("OFFER_SCOPE_MISMATCH")
            if not offer.valid_from <= snapshot.evaluated_at < offer.valid_until:
                reasons.append("OFFER_EXPIRED")
            if quantity < offer.minimum_order_quantity:
                reasons.append("MINIMUM_ORDER_QUANTITY")
            if quantity % offer.pack_size:
                reasons.append("PACK_SIZE_MISMATCH")
            if arrival is None or arrival > snapshot.daily_demand[-1].settlement_at:
                reasons.append("ARRIVAL_WINDOW_MISSED")
            if not snapshot.executable:
                reasons.append("UNVERIFIED_EXECUTION_INPUT")
            if snapshot.unresolved_action_id:
                reasons.append("ACTION_IN_PROGRESS")
            if snapshot.completed_purchase_action_id:
                reasons.append("EMERGENCY_PURCHASE_ALREADY_ACCEPTED")
        if snapshot.max_purchase_qty is not None and quantity > snapshot.max_purchase_qty:
            reasons.append("TASK_QUANTITY_LIMIT")
        if spend > snapshot.budget_minor:
            reasons.append("BUDGET_EXCEEDED")
        if snapshot.available_cash_minor - spend < snapshot.cash_floor_minor:
            reasons.append("CASH_FLOOR_VIOLATION")
        if spend > MAX_BIGINT:
            reasons.append("MONEY_OVERFLOW")
        daily = trajectory(snapshot, quantity, arrival)
        lost = sum(d.lost_qty for d in daily)
        candidates.append(
            RecoveryCandidate(
                id=f"{offer.supplier_id}_{quantity}" if offer else "wait",
                supplier_id=offer.supplier_id if offer else None,
                quantity=quantity,
                spend_minor=spend,
                cash_after_minor=snapshot.available_cash_minor - spend,
                lost_qty=lost,
                shortage_qty=lost,
                end_stock=daily[-1].end_stock,
                feasible=not reasons,
                executable=bool(quantity) and not reasons,
                rejection_reasons=reasons,
                daily=daily,
            )
        )

    add(None, 0)
    for offer in sorted(snapshot.offers, key=lambda o: o.supplier_id):
        minimum = (
            (offer.minimum_order_quantity + offer.pack_size - 1)
            // offer.pack_size
            * offer.pack_size
        )
        available = max(
            0, min(snapshot.budget_minor, snapshot.available_cash_minor - snapshot.cash_floor_minor)
        )
        maximum = available // offer.unit_price_minor
        if snapshot.max_purchase_qty is not None:
            maximum = min(maximum, snapshot.max_purchase_qty)
        count = max(0, (maximum - minimum) // offer.pack_size + 1)
        if count > 100:
            raise SearchSpaceExceeded("At most 100 nonzero quantities per offer are supported")
        for quantity in range(minimum, maximum + 1, offer.pack_size) if count else [minimum]:
            add(offer, quantity)
    feasible = [c for c in candidates if c.feasible]
    recommended = min(
        feasible,
        key=lambda c: (c.lost_qty, c.spend_minor, c.end_stock, c.supplier_id or "", c.quantity),
        default=None,
    )
    return SolverResult(
        candidates=candidates,
        recommended_candidate_id=recommended.id if recommended else None,
        horizon_tail=[
            a
            for a in snapshot.arrivals
            if a.expected_arrival_at is None
            or a.expected_arrival_at > snapshot.daily_demand[-1].settlement_at
        ],
    )
