import json

import pytest
from test_case_scoring import payloads, score


def with_cost(trace, cost, role="root", call_id="root"):
    trace["calls_complete"] = True
    trace["calls"].append(
        {
            "call_id": call_id,
            "role": role,
            "status": "completed",
            "input_tokens": 10,
            "output_tokens": 4,
            "reasoning_tokens": None,
            "cached_input_tokens": None,
            "cost": cost,
        }
    )
    return trace


def test_all_valid_attempts_in_denominator_and_failures_in_cost_numerator():
    from shopsteward_pt.case_eval.reporting import summarize

    case, good = payloads()
    with_cost(good, 1.0)
    _, failed = payloads()
    failed["run_id"] = "run-2"
    failed["observations"][0]["value"] = False
    with_cost(failed, 2.0, "expert")
    _, missing = payloads()
    missing["run_id"] = "run-3"
    missing["observations"] = []
    with_cost(missing, 3.0, "helper")
    group = summarize([score(case, t) for t in (good, failed, missing)])["groups"][0]
    assert group["outcomes"] == {
        "attempted": 3,
        "success": 1,
        "failure": 1,
        "undetermined": 1,
        "pending_review": 0,
        "missing_trace": 1,
        "success_rate_lower": 1 / 3,
        "success_rate_upper": 2 / 3,
    }
    assert group["cost"]["total"] == 6.0
    assert group["cost"]["per_success"] == 6.0
    assert group["usage"]["observed_calls"] == 3
    assert group["usage"]["input_tokens"]["known_subtotal"] == 30
    assert group["usage"]["reasoning_tokens"]["total"] is None


def test_unknown_cost_never_becomes_zero_and_no_success_cost_is_undefined():
    from shopsteward_pt.case_eval.reporting import summarize

    case, trace = payloads()
    with_cost(trace, 2.0)
    with_cost(trace, None, "expert", "expert")
    trace["observations"][0]["value"] = False
    group = summarize([score(case, trace)])["groups"][0]
    assert group["cost"] == {
        "status": "partial",
        "total": None,
        "known_subtotal": 2.0,
        "unknown_runs": 1,
        "per_success": None,
        "per_success_status": "undefined_no_success",
    }


def test_invalid_fixture_exclusion_requires_consistency_across_strategies():
    from shopsteward_pt.case_eval.reporting import summarize

    case, trace = payloads()
    valid = score(case, trace)
    case["fixture_valid"] = False
    case["invalid_fixture_reason"] = "Broken fixture reference"
    trace["run_id"] = "other"
    trace["strategy_id"] = "R3"
    invalid = score(case, trace)
    with pytest.raises(ValueError, match="fixture validity"):
        summarize([valid, invalid])
    report = summarize([invalid])
    assert report["groups"][0]["outcomes"]["attempted"] == 0
    assert report["excluded"][0]["reason"] == "Broken fixture reference"


def test_different_endpoints_and_configurations_are_not_merged():
    from shopsteward_pt.case_eval.reporting import summarize

    case, trace = payloads()
    first = score(case, trace)
    case["goal_endpoint"] = "pending_plan"
    trace["run_id"] = "other"
    second = score(case, trace)
    assert len(summarize([first, second])["groups"]) == 2


def test_result_contract_rejects_success_with_critical_failure():
    from pydantic import ValidationError

    from shopsteward_pt.case_eval.models import CaseResult

    data = score().model_dump(mode="json")
    data["critical_failures"] = ["hard_budget_violation"]
    with pytest.raises(ValidationError):
        CaseResult.model_validate_json(json.dumps(data))


def test_report_rejects_different_gold_for_same_case_and_contract_across_strategies():
    from shopsteward_pt.case_eval.reporting import summarize

    case, trace = payloads()
    original = score(case, trace)
    case["predicates"][0]["acceptable_values"] = ["different gold"]
    trace["strategy_id"] = "R3"
    trace["run_id"] = "other"
    changed = score(case, trace)
    with pytest.raises(ValueError, match="frozen case"):
        summarize([original, changed])
