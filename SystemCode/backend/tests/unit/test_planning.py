import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


def example():
    doc = json.loads(
        (Path(__file__).parents[3] / "docs/api/backend.openapi.json").read_text(encoding="utf-8")
    )
    return doc["paths"]["/api/v1/plans/{plan_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]


def snapshot():
    from app.planning.schemas import DecisionSnapshot

    return DecisionSnapshot.model_validate(example()["input_snapshot"])


def plan(value):
    from app.planning.engine import build_plan

    return build_plan("mission_001", 1, value, ttl_seconds=900)


def test_sc01_recommends_40_and_rejects_80_without_spending():
    value = snapshot()
    result = plan(value)
    assert result.recommended_candidate_id == "candidate_40"
    assert result.proposed_purchase.total_minor == 40000
    assert value.state.cash_minor == 100000
    assert result.candidates[-1].rejection_reasons == ["CASH_FLOOR_VIOLATION"]
    assert result.candidates[-1].cash_after_minor == 20000
    doc = json.loads(
        (Path(__file__).parents[3] / "docs/api/backend.openapi.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        {"$ref": "#/components/schemas/Plan", "components": doc["components"]},
        format_checker=FormatChecker(),
    ).validate(result.model_dump(mode="json"))


def test_canonical_hash_matches_published_contract_and_excludes_status_explanation():
    from app.planning.engine import proposal_hash

    value = example()
    assert proposal_hash(value) == value["proposal_hash"]
    value["status"] = "REJECTED"
    value["explanation"] = "different display text"
    assert proposal_hash(value) == value["proposal_hash"]
    value["proposed_purchase"]["quantity"] = 20
    assert proposal_hash(value) != value["proposal_hash"]


def test_zero_and_no_feasible_candidate_never_propose_purchase():
    value = snapshot()
    value.state.stocks[0].on_hand = 60
    result = plan(value)
    assert result.recommended_candidate_id == "candidate_0"
    assert result.proposed_purchase is None
    value.state.cash_minor = value.state.available_cash_minor = 10000
    result = plan(value)
    assert result.recommended_candidate_id is None
    assert result.proposed_purchase is None


def test_hash_canonicalizes_offsets_precision_and_candidate_order():
    from app.planning.engine import proposal_hash

    value = example()
    value["input_snapshot"]["evaluated_at"] = "2026-06-30T08:00:00.999999+08:00"
    # Equivalent second, independently of the example's evaluation date.
    expected = proposal_hash(value)
    value["input_snapshot"]["evaluated_at"] = "2026-06-30T00:00:00Z"
    value["candidates"].reverse()
    assert proposal_hash(value) == expected
    value["candidates"][0]["spend_minor"] = 1.0
    with pytest.raises(ValueError):
        proposal_hash(value)


def test_persistable_decision_uses_utc_seconds():
    from datetime import datetime

    value = snapshot()
    value.evaluated_at = datetime.fromisoformat("2026-06-30T08:00:00.999999+08:00")
    result = plan(value).model_dump(mode="json")
    assert result["created_at"] == "2026-06-30T00:00:00Z"
    assert result["input_snapshot"]["evaluated_at"] == result["created_at"]


def test_moq_pack_and_late_arrival_reject_positive_candidates():
    value = snapshot()
    value.policy.candidate_quantities = [0, 10, 25]
    result = plan(value)
    assert "MINIMUM_ORDER_QUANTITY" in result.candidates[1].rejection_reasons
    assert "PACK_SIZE_MISMATCH" in result.candidates[2].rejection_reasons
    value.offer.lead_time_seconds = 8 * 86400
    assert "ARRIVAL_WINDOW_MISSED" in plan(value).candidates[1].rejection_reasons


def test_available_cash_and_eligible_inbound_are_used():
    value = snapshot()
    value.state.reserved_cash_minor = 50000
    value.state.available_cash_minor = 50000
    value.eligible_inbound_qty = 20
    result = plan(value)
    assert result.recommended_candidate_id == "candidate_20"
    assert result.proposed_purchase.total_minor == 20000
    assert result.candidates[2].feasible is False


def test_policy_disallows_duplicate_and_coerced_quantities():
    from pydantic import ValidationError

    from app.planning.schemas import Policy

    for quantities in [[0, 0], [True], [1.1], ["20"], [], list(range(21))]:
        with pytest.raises(ValidationError):
            Policy(cash_floor_minor=30000, candidate_quantities=quantities, supplier_id="s")
