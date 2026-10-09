import copy
import json
from pathlib import Path

import pytest


def example(action="evaluate_plan", quantity=20):
    from shopsteward_agent.task_policy.contracts import decision_tool_schemas

    arguments = {"plan_id": "plan-1", "max_purchase_qty": quantity}
    if action == "revise_plan":
        arguments["expected_mission_version"] = 3
    spec = {
        "episode_id": "scorer-1",
        "task_type": "PT-01" if action == "evaluate_plan" else "PT-02",
        "scenario_family": "scorer-fixture",
        "split": "dev",
        "suite": "core",
        "fixture_recipe": "replenishment_standard",
        "user_message": "如果上限20件呢？",
        "followup_user_message": None,
        "expected_steps": [
            {
                "allowed_actions": [action],
                "arguments": {**arguments, "plan_id": "$current_plan_id"},
                "clarification_slot": None,
            }
        ],
        "final_predicates": ["receipt_ok", "no_purchase_created", "cash_stock_transit_unchanged"]
        + (
            ["current_plan_unchanged", "task_constraints_unchanged"]
            if action == "evaluate_plan"
            else [
                "revision_cap_matches",
                "purchase_within_cap",
                "old_plan_document_preserved",
                "new_plan_pending",
            ]
        ),
        "review": {"reviewer": "test", "status": "agent_reviewed", "rationale": "fixture"},
    }
    before = {
        "current_plan_id": "plan-1",
        "mission_version": 3,
        "mission_status": "ACTIVE",
        "task_constraints": {},
        "policy": {"cash_floor_minor": 30000},
        "cash_minor": 100000,
        "stocks": [{"sku_id": "s", "on_hand": 20, "in_transit": 0}],
        "purchase_action_ids": [],
        "plan_document": {"id": "plan-1"},
        "plan_status": "PENDING_APPROVAL",
    }
    after = copy.deepcopy(before)
    data = {
        "hypothetical": True,
        "base_plan_id": "plan-1",
        "task_constraints": {"max_purchase_qty": quantity},
        "recommended_candidate_id": "q12",
        "candidates": [{"id": "q12", "quantity": 12}],
    }
    if action == "revise_plan":
        data = {
            "id": "plan-2",
            "base_plan_id": "plan-1",
            "status": "PENDING_APPROVAL",
            "input_snapshot": {
                "task_constraints": {} if quantity is None else {"max_purchase_qty": quantity}
            },
            "proposed_purchase": {"quantity": 12},
        }
        after.update(
            current_plan_id="plan-2",
            mission_version=4,
            task_constraints={} if quantity is None else {"max_purchase_qty": quantity},
            plan_document=data,
            old_plan_document=before["plan_document"],
        )
    decision = {"name": action, "arguments": arguments}
    raw = {
        "tool_calls": [{"type": "function", "function": {"name": action, "arguments": arguments}}]
    }
    context = {
        "messages": [{"role": "user", "content": spec["user_message"]}],
        "mission_id": "m",
        "plan_id": "plan-1",
        "mission_version": 3,
        "quantity_unit": "件",
        "quantity_cap": None,
        "tool_schemas": decision_tool_schemas(),
        "context_version": "v0",
    }
    trace = {
        "episode_id": "scorer-1",
        "policy_id": "fake",
        "mode": "execution",
        "context": context,
        "steps": [
            {
                "decision": decision,
                "raw_response": raw,
                "parse_error": None,
                "usage": None,
                "latency_ms": 1.0,
            }
        ],
        "receipts": [
            {"tool": action, "arguments": arguments, "result": {"ok": True, "data": data}}
        ],
        "before_state": before,
        "after_state": after,
        "delivery": {
            "kind": action,
            "plan_id": data.get("id", "plan-1"),
            "max_purchase_qty": quantity,
        },
    }
    return spec, trace


def score(spec, trace, reviews=None):
    from shopsteward_pt.eval.records import EpisodeSpec, EpisodeTrace
    from shopsteward_pt.eval.scorers import score_episode

    return score_episode(
        EpisodeSpec.model_validate(spec), EpisodeTrace.model_validate(trace), reviews or {}
    )


@pytest.mark.parametrize(
    "action,quantity", [("evaluate_plan", 20), ("revise_plan", 20), ("revise_plan", None)]
)
def test_real_receipt_and_business_facts_allow_quantity_below_cap(action, quantity):
    spec, trace = example(action, quantity)
    result = score(spec, trace)
    assert result.episode_success is True
    assert result.per_step[0].arguments_correct is True


@pytest.mark.parametrize(
    "field,value",
    [("max_purchase_qty", 30), ("plan_id", "fake-id"), ("expected_mission_version", 2)],
)
def test_all_tool_parameters_count_even_when_tool_name_is_right(field, value):
    spec, trace = example("revise_plan")
    trace["steps"][0]["decision"]["arguments"][field] = value
    result = score(spec, trace)
    assert result.per_step[0].action_correct is True
    assert result.per_step[0].arguments_correct is False
    assert result.episode_success is False


@pytest.mark.parametrize(
    "mutation", ["no_receipt", "false_receipt", "written_plan", "missing_state", "fake_delivery"]
)
def test_correct_tool_call_without_matching_execution_never_passes(mutation):
    spec, trace = example()
    if mutation == "no_receipt":
        trace["receipts"] = []
    elif mutation == "false_receipt":
        trace["receipts"][0]["result"]["ok"] = False
    elif mutation == "written_plan":
        trace["after_state"]["current_plan_id"] = "plan-2"
    elif mutation == "missing_state":
        trace["before_state"] = trace["after_state"] = {}
    else:
        trace["delivery"]["plan_id"] = "fake"
    result = score(spec, trace)
    assert result.per_step[0].action_correct is True
    assert result.episode_success is False


def test_backend_rejection_does_not_change_semantic_gold():
    spec, trace = example("revise_plan")
    trace["receipts"][0]["result"] = {"ok": False, "error": {"code": "EXPLICIT_REVISION_REQUIRED"}}
    trace["after_state"] = copy.deepcopy(trace["before_state"])
    result = score(spec, trace)
    assert result.decision_success is True
    assert result.episode_success is False
    assert "backend_policy_mismatch" in result.failure_tags


def test_decision_mode_has_no_business_success_and_environment_failure_is_visible():
    spec, trace = example()
    trace["mode"] = "decision"
    trace["receipts"] = []
    assert score(spec, trace).episode_success is None
    trace["environment_error"] = "service_timeout"
    trace["steps"] = []
    result = score(spec, trace)
    assert result.decision_success is False
    assert "environment_error" in result.failure_tags
    assert result.per_step[0].attempted is False


def test_clarification_requires_review_of_the_actual_question():
    spec, trace = example()
    spec.update(task_type="PT-04", followup_user_message="只试算上限20件。")
    spec["expected_steps"].insert(
        0,
        {"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"},
    )
    spec["final_predicates"].extend(["clarification_relevant", "no_mutation_before_reply"])
    trace["steps"].insert(
        0,
        {
            "decision": {"name": "clarify", "arguments": {"question": "采购上限具体是多少件？"}},
            "raw_response": {},
            "parse_error": None,
            "usage": None,
            "latency_ms": 1.0,
        },
    )
    trace["state_after_clarify"] = copy.deepcopy(trace["before_state"])
    result = score(spec, trace)
    assert result.review_status == "pending_review"
    assert result.episode_success is None
    review = {
        "scorer-1:0": {
            "question": "采购上限具体是多少件？",
            "slot": "max_purchase_qty",
            "relevant": True,
            "no_guess": True,
            "no_known_id_request": True,
            "reviewer": "test",
            "review_type": "agent_reviewed",
        }
    }
    assert score(spec, trace, review).episode_success is True
    review["scorer-1:0"]["question"] = "另一个问题"
    assert score(spec, trace, review).review_status == "pending_review"


def test_raw_invalid_format_counts_as_failure():
    spec, trace = example()
    trace["steps"][0].update(decision=None, parse_error="multiple calls")
    result = score(spec, trace)
    assert result.per_step[0].format_valid is False
    assert result.per_step[0].arguments_correct is False
    assert "format_error" in result.failure_tags


def test_frozen_counterexamples():
    path = Path(__file__).parent / "fixtures/scorer_cases.json"
    for row in json.loads(path.read_text(encoding="utf-8")):
        result = score(row["spec"], row["trace"], row["reviews"])
        assert result.episode_success == row["expected_success"]
        if row["expected_failure_tag"]:
            assert row["expected_failure_tag"] in result.failure_tags


def test_zero_cap_with_no_purchase_proposal_uses_real_zero_candidate():
    spec, trace = example("revise_plan", 0)
    trace["receipts"][0]["result"]["data"].update(
        proposed_purchase=None,
        recommended_candidate_id="q0",
        candidates=[{"id": "q0", "quantity": 0}],
    )
    assert score(spec, trace).episode_success is True
