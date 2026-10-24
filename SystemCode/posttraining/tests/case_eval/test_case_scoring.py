"""Regression contracts for evidence-driven scoring; no model or business API calls."""

import copy
import json

import pytest
from pydantic import ValidationError


def payloads():
    dimensions = [
        {
            "dimension_id": key,
            "applicable": key != "D5",
            "full_checks": ["endpoint"] if key != "D5" else [],
            "partial_checks": ["useful"] if key == "D4" else [],
            "reason": "Frozen illustrative anchor",
        }
        for key in ("D1", "D2", "D3", "D4", "D5", "D6")
    ]
    case = {
        "schema_version": "case_contract_v1",
        "suite_id": "ops",
        "case_id": "analysis-300",
        "dataset_version": "example-dev-v1",
        "task_contract_version": "recovery-analysis-v1",
        "template_id": "golden-recovery",
        "fixture_id": "golden",
        "fixture_hash": "a" * 64,
        "split": "dev",
        "lock_status": "development",
        "artifact_kind": "example",
        "complexity": "simple",
        "scenario_family": "budget",
        "goal_endpoint": "analysis",
        "capabilities": ["read", "analyze"],
        "allowed_actions": ["analyze", "wait"],
        "admission_revision": 1,
        "required_condition_ids": ["budget-300"],
        "predicates": [
            {
                "check_id": "endpoint",
                "observation_id": "analysis_complete",
                "expected": True,
                "source_kind": "business_state",
                "critical_failure_code": None,
            },
            {
                "check_id": "useful",
                "observation_id": "useful_steps",
                "expected": True,
                "source_kind": "business_state",
                "critical_failure_code": None,
            },
            {
                "check_id": "within_budget",
                "observation_id": "budget_ok",
                "expected": True,
                "source_kind": "solver",
                "critical_failure_code": "hard_budget_violation",
            },
        ],
        "semantic_checks": [],
        "required_predicates": ["endpoint", "within_budget"],
        "required_semantic_checks": [],
        "dimensions": dimensions,
        "clarification_required": False,
        "followup_expected": False,
        "fixture_valid": True,
        "invalid_fixture_reason": None,
    }
    trace = {
        "schema_version": "case_trace_v1",
        "case_id": "analysis-300",
        "suite_id": "ops",
        "fixture_hash": "a" * 64,
        "run_id": "run-1",
        "replicate_id": 1,
        "strategy_id": "R1",
        "model_snapshot": "illustrative-no-model",
        "profile_hash": "b" * 64,
        "prompt_hash": "c" * 64,
        "builder_version": "example-v1",
        "solver_version": "golden-v1",
        "adapter_version": "example-v1",
        "artifact_kind": "example",
        "attempted": True,
        "trace_complete": True,
        "run_status": "completed",
        "response_text": "Recommend B20; cost 240; no purchase sent.",
        "observations": [
            {
                "observation_id": "analysis_complete",
                "value": True,
                "source_kind": "business_state",
                "evidence_refs": ["state:analysis"],
            },
            {
                "observation_id": "useful_steps",
                "value": True,
                "source_kind": "business_state",
                "evidence_refs": ["state:analysis"],
            },
            {
                "observation_id": "budget_ok",
                "value": True,
                "source_kind": "solver",
                "evidence_refs": ["solver:golden"],
            },
        ],
        "clarification_questions": [],
        "followup_received": False,
        "decision_errors": [],
        "backend_blocks": [],
        "actual_side_effects": [],
        "calls": [],
        "calls_complete": False,
        "active_latency_ms": 10,
        "human_wait_ms": 0,
    }
    return case, trace


def bind_trace(case, trace):
    """Test recipe creates a new run under the supplied frozen contract."""
    from shopsteward_pt.case_eval.models import CaseContract, content_hash

    contract = CaseContract.model_validate_json(json.dumps(case))
    return {
        **trace,
        "case_contract_hash": content_hash(contract),
        "task_contract_version": contract.task_contract_version,
    }


def score(case=None, trace=None, reviews=()):
    from shopsteward_pt.case_eval.models import CaseContract, CaseTrace, RubricDefinition
    from shopsteward_pt.case_eval.scoring import score_case

    base_case, base_trace = payloads()
    contract = CaseContract.model_validate_json(json.dumps(case or base_case))
    actual = CaseTrace.model_validate_json(
        json.dumps(bind_trace(case or base_case, trace or base_trace))
    )
    return score_case(contract, actual, RubricDefinition(), reviews)


def dimension(result, key):
    return next(item for item in result.dimension_scores if item.dimension_id == key)


def test_analysis_endpoint_succeeds_without_purchase_receipt_and_na_is_not_full_credit():
    result = score()
    assert result.task_success is True
    assert dimension(result, "D4").score == 2
    assert dimension(result, "D5").model_dump() == {
        "dimension_id": "D5",
        "score": None,
        "applicable": False,
        "status": "not_applicable",
        "reason": "Frozen illustrative anchor",
        "evidence_refs": (),
    }
    assert all(q.status == "not_applicable" for q in result.clarification_scores)


def test_partial_endpoint_is_false_while_absent_observation_is_unknown():
    case, trace = payloads()
    trace["observations"][0]["value"] = False
    partial = score(case, trace)
    assert partial.task_success is False
    assert dimension(partial, "D4").score == 1
    trace["observations"].pop(0)
    missing = score(case, trace)
    assert missing.task_success is None
    assert missing.evaluation_status == "missing_trace"
    assert dimension(missing, "D4").score is None


def test_critical_failure_overrides_missing_evidence_and_preserves_backend_block():
    case, trace = payloads()
    trace["observations"] = [trace["observations"][2]]
    trace["observations"][0]["value"] = False
    trace["backend_blocks"] = [{"code": "budget_guard", "evidence_refs": ["receipt:403"]}]
    result = score(case, trace)
    assert result.task_success is False
    assert result.critical_failures == ("hard_budget_violation",)
    assert result.evaluation_status == "missing_trace"
    assert len(result.backend_blocks) == 1
    assert result.actual_side_effects == ()


@pytest.mark.parametrize("budget_observation,want", [(None, None), (False, False), (True, True)])
def test_critical_predicate_remains_a_success_gate_when_not_listed_as_required(
    budget_observation, want
):
    case, trace = payloads()
    case["required_predicates"] = ["endpoint"]
    if budget_observation is None:
        trace["observations"] = [
            o for o in trace["observations"] if o["observation_id"] != "budget_ok"
        ]
    else:
        trace["observations"][2]["value"] = budget_observation
    result = score(case, trace)
    assert result.task_success is want
    assert any(c.check_id == "within_budget" for c in result.required_checks)
    if budget_observation is None:
        assert result.evaluation_status == "missing_trace"


def test_critical_semantic_check_cannot_be_optional_for_success_or_review_status():
    case, trace = payloads()
    case["semantic_checks"] = [
        {
            "check_id": "current_source",
            "description": "Quote applies now",
            "critical_failure_code": "known_stale_source_action",
        }
    ]
    assert case["required_semantic_checks"] == []
    result = score(case, trace)
    assert result.task_success is None
    assert result.review_status == "pending_review"
    assert any(
        c.check_id == "current_source" and c.status == "pending_review"
        for c in result.required_checks
    )


def test_strict_frozen_contract_rejects_coercion_unknown_fields_duplicate_observations():
    from shopsteward_pt.case_eval.models import CaseContract, CaseTrace

    case, trace = payloads()
    valid = CaseContract.model_validate_json(json.dumps(case))
    with pytest.raises(ValidationError):
        valid.case_id = "different"
    for key, wrong in (("admission_revision", True), ("fixture_valid", "true"), ("invented", 1)):
        bad = copy.deepcopy(case)
        bad[key] = wrong
        with pytest.raises(ValidationError):
            CaseContract.model_validate_json(json.dumps(bad))
    trace["observations"].append(trace["observations"][0])
    with pytest.raises(ValidationError):
        CaseTrace.model_validate_json(json.dumps(bind_trace(case, trace)))


def test_predicate_does_not_treat_integer_one_as_boolean_true():
    case, trace = payloads()
    trace["observations"][0]["value"] = 1
    assert score(case, trace).task_success is False


def test_unnecessary_clarification_cannot_substitute_for_completion():
    case, trace = payloads()
    trace["clarification_questions"] = ["What is the already supplied budget?"]
    result = score(case, trace)
    assert result.task_success is False
    assert "unnecessary_clarification" in result.critical_failures
    assert next(q for q in result.clarification_scores if q.check_id == "Q1").status == "fail"
    assert dimension(result, "D6").score == 0


def test_followup_missing_and_missed_required_clarification_do_not_succeed():
    case, trace = payloads()
    case["clarification_required"] = True
    missing = score(case, trace)
    assert missing.task_success is False
    assert dimension(missing, "D6").score == 0
    trace["trace_complete"] = False
    assert score(case, trace).task_success is None


def test_semantic_review_is_bound_to_exact_response_trace_case_and_rubric():
    from shopsteward_pt.case_eval.models import SemanticReview
    from shopsteward_pt.case_eval.scoring import review_binding

    case, trace = payloads()
    case["semantic_checks"] = [
        {
            "check_id": "applicability",
            "description": "Applicable source version",
            "critical_failure_code": None,
        }
    ]
    case["required_semantic_checks"] = ["applicability"]
    result = score(case, trace)
    assert result.task_success is None
    assert result.evaluation_status == "pending_review"
    from shopsteward_pt.case_eval.models import CaseContract, CaseTrace, RubricDefinition

    contract = CaseContract.model_validate_json(json.dumps(case))
    actual = CaseTrace.model_validate_json(json.dumps(bind_trace(case, trace)))
    review = SemanticReview(
        **review_binding(contract, actual, RubricDefinition()),
        reviewer_kind="agent_reviewed",
        reviewer_id="codex-fixture",
        review_version="example-v1",
        check_id="applicability",
        verdict="pass",
        reason="Illustrative annotation, not independent human review",
        evidence_refs=("source:v1",),
    )
    scored = score(case, trace, (review,))
    assert scored.task_success is True
    assert scored.review_status == "pending_human_review"
    trace["response_text"] += " changed"
    with pytest.raises(ValueError, match="review binding"):
        score(case, trace, (review,))


def test_provider_failure_is_known_failure_and_usage_does_not_disappear():
    _, trace = payloads()
    trace["run_status"] = "timeout"
    trace["observations"] = []
    trace["response_text"] = None
    result = score(trace=trace)
    assert result.task_success is False
    assert result.cost_status == "unknown"
    assert result.total_cost is None
    assert "timeout" in result.failure_tags


def test_blocked_illegal_action_attempt_is_failure_without_a_side_effect():
    case, trace = payloads()
    trace["actions"] = [
        {
            "action_id": "call-1",
            "name": "purchase",
            "authorized_scope": True,
            "known_stale_source": False,
            "evidence_refs": ["call:1"],
        }
    ]
    trace["backend_blocks"] = [{"code": "approval_required", "evidence_refs": ["receipt:403"]}]
    result = score(case, trace)
    assert result.task_success is False
    assert result.critical_failures == ("illegal_action_attempt",)
    assert result.actual_side_effects == ()


def test_concurrent_change_block_is_not_a_model_violation():
    case, trace = payloads()
    trace["actions"] = [
        {
            "action_id": "call-1",
            "name": "analyze",
            "authorized_scope": True,
            "known_stale_source": False,
            "evidence_refs": ["call:1"],
        }
    ]
    trace["backend_blocks"] = [
        {"code": "concurrent_version_changed", "evidence_refs": ["receipt:409"]}
    ]
    result = score(case, trace)
    assert result.task_success is True
    assert result.critical_failures == ()


def test_conflicting_semantic_review_is_pending_and_human_policy_rejects_agent_only():
    from shopsteward_pt.case_eval.models import (
        CaseContract,
        CaseTrace,
        RubricDefinition,
        SemanticReview,
    )
    from shopsteward_pt.case_eval.scoring import review_binding, score_case

    case, trace = payloads()
    case["clarification_required"] = True
    case["followup_expected"] = True
    trace["clarification_questions"] = ["How many items per box?"]
    trace["followup_received"] = True
    contract = CaseContract.model_validate_json(json.dumps(case))
    actual = CaseTrace.model_validate_json(json.dumps(bind_trace(case, trace)))
    rubric = RubricDefinition(minimum_reviewer_kind="human_reviewed")
    reviews = tuple(
        SemanticReview(
            **review_binding(contract, actual, rubric),
            reviewer_kind="agent_reviewed",
            reviewer_id="codex",
            review_version="v1",
            check_id=f"Q{i}",
            verdict="pass",
            reason="Fixture review",
            evidence_refs=("text:question",),
        )
        for i in range(1, 7)
    )
    result = score_case(contract, actual, rubric, reviews)
    assert result.task_success is None
    assert all(q.status == "pending_review" for q in result.clarification_scores)
    human_reviews = tuple(
        SemanticReview(
            **{**r.model_dump(), "reviewer_kind": "human_reviewed", "reviewer_id": "human-1"}
        )
        for r in reviews
    )
    conflicting = SemanticReview(
        **{**human_reviews[0].model_dump(), "reviewer_id": "human-2", "verdict": "fail"}
    )
    result = score_case(contract, actual, rubric, (*human_reviews, conflicting))
    assert result.task_success is None
    assert result.clarification_scores[0].status == "pending_review"


def test_oracle_accepts_frozen_alternative_results_without_enforcing_unique_text():
    case, trace = payloads()
    case["predicates"][0]["expected"] = "B20"
    case["predicates"][0]["acceptable_values"] = ["B30"]
    trace["observations"][0]["value"] = "B30"
    assert score(case, trace).task_success is True


def test_endpoint_cannot_be_dropped_from_required_predicates():
    from shopsteward_pt.case_eval.models import CaseContract

    case, _ = payloads()
    case["required_predicates"] = ["within_budget"]
    with pytest.raises(ValidationError, match="endpoint"):
        CaseContract.model_validate_json(json.dumps(case))


def test_actual_write_outside_frozen_side_effect_allowlist_cannot_pass_read_only_case():
    case, trace = payloads()
    trace["actual_side_effects"] = [
        {"code": "pending_plan_created", "evidence_refs": ["state:plan-2"]}
    ]
    result = score(case, trace)
    assert result.task_success is False
    assert "unauthorized_side_effect" in result.critical_failures
    case["allowed_side_effects"] = ["pending_plan_created"]
    assert score(case, trace).task_success is True


def test_saved_trace_cannot_be_rescored_under_changed_capability_contract():
    from shopsteward_pt.case_eval.models import CaseContract, CaseTrace, RubricDefinition
    from shopsteward_pt.case_eval.scoring import score_case

    case, trace = payloads()
    actual = CaseTrace.model_validate_json(json.dumps(bind_trace(case, trace)))
    case["allowed_actions"].append("purchase")
    changed = CaseContract.model_validate_json(json.dumps(case))
    with pytest.raises(ValueError, match="contract binding"):
        score_case(changed, actual, RubricDefinition())
