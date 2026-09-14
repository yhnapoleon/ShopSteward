"""Pure quantity comparison shared by a real Plan and an independent simulation."""

from datetime import timedelta

from app.planning.schemas import Candidate


def evaluate_candidates(
    *,
    state,
    sku_id,
    remaining_demand,
    horizon_end,
    offer,
    policy,
    eligible_inbound_qty,
    task_constraints=None,
):
    stock = next(s for s in state.stocks if s.sku_id == sku_id)
    try:
        arrival = state.simulation_time + timedelta(seconds=offer.lead_time_seconds)
    except (OverflowError, TypeError):
        arrival = None
    constraints = task_constraints or {}
    candidates = []
    for quantity in sorted(policy.candidate_quantities):
        spend = quantity * offer.unit_price_minor
        cash_after = state.available_cash_minor - spend
        reasons = []
        if quantity > constraints.get("max_purchase_qty", quantity):
            reasons.append("TASK_QUANTITY_LIMIT")
        if cash_after < policy.cash_floor_minor:
            reasons.append("CASH_FLOOR_VIOLATION")
        if quantity:
            if quantity < offer.minimum_order_quantity:
                reasons.append("MINIMUM_ORDER_QUANTITY")
            if quantity % offer.pack_size:
                reasons.append("PACK_SIZE_MISMATCH")
            if arrival is None or arrival >= horizon_end:
                reasons.append("ARRIVAL_WINDOW_MISSED")
        candidates.append(
            Candidate(
                id=f"candidate_{quantity}",
                quantity=quantity,
                spend_minor=spend,
                cash_after_minor=cash_after,
                shortage_qty=max(
                    0, remaining_demand - stock.on_hand - eligible_inbound_qty - quantity
                ),
                feasible=not reasons,
                rejection_reasons=reasons,
            )
        )
    feasible = [c for c in candidates if c.feasible]
    recommended = min(feasible, key=lambda c: (c.shortage_qty, c.quantity)) if feasible else None
    return candidates, recommended, arrival
