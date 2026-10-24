from datetime import UTC, datetime, timedelta

import pytest


def golden(budget=30000):
    from app.planning.recovery.schemas import RecoveryInput

    start = datetime(2026, 10, 1, tzinfo=UTC)
    return RecoveryInput(
        store_id="store",
        sku_id="sku",
        on_hand=20,
        available_cash_minor=80000,
        cash_floor_minor=50000,
        budget_minor=budget,
        business_time=start,
        evaluated_at=start,
        demand_source="user_scenario",
        executable=True,
        daily_demand=[
            {"settlement_at": start + timedelta(days=i, hours=23), "demand_qty": 10}
            for i in range(7)
        ],
        arrivals=[
            {
                "action_id": "old",
                "sku_id": "sku",
                "ordered_qty": 50,
                "received_qty": 0,
                "expected_arrival_at": start + timedelta(days=4),
            }
        ],
        offers=[
            {
                "supplier_id": supplier,
                "sku_id": "sku",
                "unit_price_minor": price,
                "minimum_order_quantity": moq,
                "pack_size": 10,
                "offer_version": "v1",
                "currency": "CNY",
                "lead_time_seconds": days * 86400,
                "valid_from": start - timedelta(days=1),
                "valid_until": start + timedelta(days=1),
            }
            for supplier, price, moq, days in [
                ("A", 900, 40, 2),
                ("B", 1200, 20, 2),
                ("C", 800, 20, 4),
            ]
        ],
    )


def test_golden_daily_recovery_preserves_paid_order_and_selects_b20():
    from app.planning.recovery.solver import solve

    result = solve(golden())
    selected = next(c for c in result.candidates if c.id == result.recommended_candidate_id)
    assert (selected.supplier_id, selected.quantity, selected.spend_minor) == ("B", 20, 24000)
    assert (selected.lost_qty, selected.end_stock) == (0, 20)
    assert [d.end_stock for d in selected.daily] == [10, 0, 10, 0, 40, 30, 20]
    waiting = next(c for c in result.candidates if c.quantity == 0)
    assert [d.lost_qty for d in waiting.daily] == [0, 0, 10, 10, 0, 0, 0]
    a = next(c for c in result.candidates if c.supplier_id == "A")
    assert a.quantity == 40 and not a.feasible
    assert "CASH_FLOOR_VIOLATION" in a.rejection_reasons


def test_budget_200_selects_waiting_instead_of_useless_late_purchase():
    from app.planning.recovery.solver import solve

    result = solve(golden(20000))
    selected = next(c for c in result.candidates if c.id == result.recommended_candidate_id)
    assert (selected.quantity, selected.spend_minor, selected.lost_qty) == (0, 0, 20)


def test_partial_receipts_and_unknown_eta_do_not_double_count_stock():
    from app.planning.recovery.solver import solve

    value = golden(0)
    value.arrivals[0].received_qty = 20
    waiting = solve(value).candidates[0]
    assert sum(d.existing_arrivals for d in waiting.daily) == 30
    assert waiting.end_stock == 0
    value.arrivals[0].expected_arrival_at = None
    waiting = solve(value).candidates[0]
    assert waiting.lost_qty == 50


def test_expired_offers_and_zero_quantity_limit_never_executable():
    from app.planning.recovery.solver import solve

    value = golden()
    value.max_purchase_qty = 0
    assert all(not c.feasible for c in solve(value).candidates if c.quantity)
    value.max_purchase_qty = None
    value.evaluated_at += timedelta(days=2)
    assert all(
        "OFFER_EXPIRED" in c.rejection_reasons for c in solve(value).candidates if c.quantity
    )


def test_bounded_search_refuses_to_claim_optimality_after_truncation():
    from app.planning.recovery.solver import SearchSpaceExceeded, solve

    value = golden(100000000)
    value.available_cash_minor = 100000000
    with pytest.raises(SearchSpaceExceeded):
        solve(value)


def test_daily_allocator_uses_largest_remainder_and_rejects_inconsistent_total():
    from app.planning.recovery.solver import allocate_daily

    assert allocate_daily([1.8, 1.8, 1.4, 1.0, 1.0, 1.0, 1.0], 9) == [2, 2, 1, 1, 1, 1, 1]
    with pytest.raises(ValueError):
        allocate_daily([1.0] * 7, 10)


def test_daily_allocator_accepts_the_persisted_v6_ceiling_total():
    from app.planning.recovery.solver import allocate_daily

    assert allocate_daily([1.01] * 7, 8) == [2, 1, 1, 1, 1, 1, 1]


def test_unknown_submission_is_visible_in_analysis_but_never_executable():
    from app.planning.recovery.solver import solve

    value = golden()
    value.unresolved_action_id = "unknown-original"
    result = solve(value)
    assert all(
        not c.executable and "ACTION_IN_PROGRESS" in c.rejection_reasons
        for c in result.candidates
        if c.quantity
    )
    assert result.recommended_candidate_id == "wait"
