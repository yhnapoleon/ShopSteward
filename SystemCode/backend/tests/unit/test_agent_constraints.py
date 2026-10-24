from test_planning import snapshot

from app.planning.engine import build_plan


def test_task_quantity_limit_rejects_larger_candidates_without_lowering_cash_floor():
    original = snapshot()
    modified = original.model_copy(update={"task_constraints": {"max_purchase_qty": 20}})
    plan = build_plan("mission", 2, modified, ttl_seconds=900)
    assert plan.proposed_purchase.quantity <= 20
    assert modified.policy.cash_floor_minor == original.policy.cash_floor_minor
    assert all(not c.feasible for c in plan.candidates if c.quantity > 20)
