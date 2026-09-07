from datetime import timedelta
from uuid import uuid4

from app.core.hashing import digest
from app.planning.canonical import canonical
from app.planning.schemas import Candidate, DecisionSnapshot, Plan, ProposedPurchase

RULE_VERSION = "finite-candidates-v1"


def proposal_hash(plan):
    fields = (
        "mission_id",
        "plan_version",
        "input_snapshot",
        "candidates",
        "recommended_candidate_id",
        "proposed_purchase",
        "expires_at",
    )
    return "sha256:" + digest(
        canonical({"hash_version": "decision-v1", **{key: plan[key] for key in fields}})
    )


def input_hash(snapshot):
    value = canonical(snapshot.model_dump(mode="json"))
    # A fresh sync/evaluation alone does not change purchase intent.
    for field in ("evaluated_at", "last_successful_sync_at", "source_fresh_until"):
        value.pop(field)
    return digest(value)


def arrival_at(snapshot):
    try:
        return snapshot.state.simulation_time + timedelta(seconds=snapshot.offer.lead_time_seconds)
    except (OverflowError, TypeError):
        return None


def build_plan(mission_id, plan_version, snapshot, *, ttl_seconds):
    snapshot = DecisionSnapshot.model_validate(canonical(snapshot.model_dump(mode="json")))
    stock = next(s for s in snapshot.state.stocks if s.sku_id == snapshot.forecast.sku_id)
    offer = snapshot.offer
    arrival = arrival_at(snapshot)
    candidates = []
    for quantity in sorted(snapshot.policy.candidate_quantities):
        spend = quantity * offer.unit_price_minor
        cash_after = snapshot.state.available_cash_minor - spend
        reasons = []
        if quantity > snapshot.task_constraints.get("max_purchase_qty", quantity):
            reasons.append("TASK_QUANTITY_LIMIT")
        if cash_after < snapshot.policy.cash_floor_minor:
            reasons.append("CASH_FLOOR_VIOLATION")
        if quantity:
            if quantity < offer.minimum_order_quantity:
                reasons.append("MINIMUM_ORDER_QUANTITY")
            if quantity % offer.pack_size:
                reasons.append("PACK_SIZE_MISMATCH")
            if arrival is None or arrival >= snapshot.forecast.horizon_end:
                reasons.append("ARRIVAL_WINDOW_MISSED")
        candidates.append(
            Candidate(
                id=f"candidate_{quantity}",
                quantity=quantity,
                spend_minor=spend,
                cash_after_minor=cash_after,
                shortage_qty=max(
                    0,
                    snapshot.forecast.remaining_demand
                    - stock.on_hand
                    - snapshot.eligible_inbound_qty
                    - quantity,
                ),
                feasible=not reasons,
                rejection_reasons=reasons,
            )
        )
    feasible = [c for c in candidates if c.feasible]
    recommended = min(feasible, key=lambda c: (c.shortage_qty, c.quantity)) if feasible else None
    purchase = None
    if recommended is not None and recommended.quantity:
        purchase = ProposedPurchase(
            store_id=snapshot.state.store_id,
            sku_id=offer.sku_id,
            supplier_id=offer.supplier_id,
            quantity=recommended.quantity,
            unit_price_minor=offer.unit_price_minor,
            total_minor=recommended.spend_minor,
            currency=offer.currency,
            expected_arrival_at=arrival,
        )
    explanation = (
        f"推荐采购{recommended.quantity}件；预计支出{recommended.spend_minor}分，"
        f"采购后可用现金{recommended.cash_after_minor}分，剩余缺口{recommended.shortage_qty}件。"
        if recommended
        else "当前候选均不满足采购约束，未提出采购。"
    )
    plan = Plan(
        id=str(uuid4()),
        mission_id=mission_id,
        plan_version=plan_version,
        state_version=snapshot.state.state_version,
        forecast_version=snapshot.forecast.forecast_version,
        policy_version=snapshot.policy_version,
        rule_version=snapshot.rule_version,
        status="PENDING_APPROVAL",
        input_snapshot=snapshot,
        candidates=candidates,
        recommended_candidate_id=recommended.id if recommended else None,
        proposal_hash="sha256:" + "0" * 64,
        explanation=explanation,
        created_at=snapshot.evaluated_at,
        expires_at=min(
            snapshot.evaluated_at + timedelta(seconds=ttl_seconds),
            snapshot.forecast.valid_until,
            offer.valid_until,
        ),
        proposed_purchase=purchase,
    )
    plan.proposal_hash = proposal_hash(plan.model_dump(mode="json"))
    return plan


def check_status(snapshot):
    stock = next(s for s in snapshot.state.stocks if s.sku_id == snapshot.forecast.sku_id)
    shortage = snapshot.forecast.remaining_demand - stock.on_hand - snapshot.eligible_inbound_qty
    return (
        "ANOMALY"
        if shortage > 0 or snapshot.state.available_cash_minor < snapshot.policy.cash_floor_minor
        else "HEALTHY"
    )
