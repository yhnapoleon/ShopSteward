from datetime import timedelta
from uuid import uuid4

from app.core.hashing import digest
from app.planning.recovery.schemas import RecoveryIntent
from app.planning.recovery.solver import solve
from app.planning.schemas import ProposedPurchase, RecoveryPlan


def recovery_hash(document):
    fields = (
        "plan_kind",
        "mission_id",
        "plan_version",
        "state_version",
        "forecast_version",
        "policy_version",
        "rule_version",
        "input_snapshot",
        "candidates",
        "recommended_candidate_id",
        "selected_candidate_id",
        "recovery_intent",
        "proposed_purchase",
        "expires_at",
    )
    return "sha256:" + digest(
        {"hash_version": "recovery_hash_v1", **{key: document[key] for key in fields}}
    )


def build_recovery_plan(mission, snapshot, proposal, selected_id, actor, expires_at):
    result = solve(snapshot.recovery)
    chosen = next(c for c in result.candidates if c.id == selected_id)
    offer = next(o for o in snapshot.recovery.offers if o.supplier_id == chosen.supplier_id)
    snapshot = snapshot.model_copy(
        update={"mission_version": mission.mission_version, "offer": offer}
    )
    plan = RecoveryPlan(
        id=str(uuid4()),
        plan_kind="recovery_v1",
        mission_id=mission.id,
        plan_version=mission.plan_counter + 1,
        state_version=snapshot.state.state_version,
        forecast_version=snapshot.forecast.forecast_version,
        policy_version=snapshot.policy_version,
        rule_version="recovery_solver_v1",
        status="PENDING_APPROVAL",
        input_snapshot=snapshot,
        candidates=result.candidates,
        recommended_candidate_id=result.recommended_candidate_id,
        selected_candidate_id=selected_id,
        recovery_intent=RecoveryIntent(
            case_id=proposal.case_id,
            revision=proposal.revision,
            proposal_id=proposal.id,
            selected_candidate_id=selected_id,
            adopted_by=actor,
            supplier_override=chosen.supplier_id,
        ),
        proposal_hash="sha256:" + "0" * 64,
        explanation=(
            f"应急补购 {chosen.quantity} 件，支出 {chosen.spend_minor} 分；"
            f"七日预测缺货 {chosen.lost_qty} 件。原订单保留。"
        ),
        created_at=snapshot.evaluated_at,
        expires_at=min(expires_at, offer.valid_until),
        proposed_purchase=ProposedPurchase(
            store_id=mission.store_id,
            sku_id=mission.sku_id,
            supplier_id=offer.supplier_id,
            quantity=chosen.quantity,
            unit_price_minor=offer.unit_price_minor,
            total_minor=chosen.spend_minor,
            currency=offer.currency,
            expected_arrival_at=snapshot.recovery.business_time
            + timedelta(seconds=offer.lead_time_seconds),
        ),
    )
    plan.proposal_hash = recovery_hash(plan.model_dump(mode="json"))
    return plan
