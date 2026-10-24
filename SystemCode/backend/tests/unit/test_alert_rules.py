from test_planning import plan, snapshot


def risks(value):
    from app.alerts.rules import evaluate

    return {r.type: r for r in evaluate(value, plan(value).candidates)}


def test_sc01_has_stock_risk_but_oversized_rejected_candidate_is_not_cash_risk():
    result = risks(snapshot())
    assert set(result) == {"STOCKOUT_RISK"}
    assert result["STOCKOUT_RISK"].facts["shortage_qty"] == 40
    assert result["STOCKOUT_RISK"].severity == "WARNING"


def test_cash_risk_uses_available_cash_and_rounds_moq_pack():
    value = snapshot()
    value.state.cash_minor = value.state.available_cash_minor = 65000
    assert risks(value)["CASH_CONSTRAINT"].severity == "WARNING"
    value.state.cash_minor = value.state.available_cash_minor = 29000
    assert risks(value)["CASH_CONSTRAINT"].severity == "CRITICAL"
    value.state.cash_minor = value.state.available_cash_minor = 75000
    value.offer.minimum_order_quantity = 50
    assert "CASH_CONSTRAINT" in risks(value)


def test_short_candidate_menu_or_late_arrival_does_not_invent_cash_problem():
    value = snapshot()
    value.policy.candidate_quantities = [0, 20]
    assert "CASH_CONSTRAINT" not in risks(value)
    value.offer.lead_time_seconds = 8 * 86400
    assert "CASH_CONSTRAINT" not in risks(value)


def test_zero_stock_escalates_and_eligible_inbound_resolves_shortage():
    value = snapshot()
    value.state.stocks[0].on_hand = 0
    assert risks(value)["STOCKOUT_RISK"].severity == "CRITICAL"
    value.eligible_inbound_qty = 60
    assert risks(value) == {}
