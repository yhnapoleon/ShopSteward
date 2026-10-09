"""A strategy run becomes a scoreable trace; business truth still comes from the oracle."""

import json

import pytest
from test_case_scoring import payloads

ORACLE = [
    {
        "observation_id": key,
        "value": True,
        "source_kind": kind,
        "evidence_refs": [f"oracle:{key}"],
    }
    for key, kind in (
        ("analysis_complete", "business_state"),
        ("useful_steps", "business_state"),
        ("budget_ok", "solver"),
    )
]


def contract():
    from shopsteward_pt.case_eval.models import CaseContract

    case, _ = payloads()
    return CaseContract.model_validate_json(json.dumps({**case, "artifact_kind": "recorded"}))


def call(role, index=1, *, run="root", status="completed", model="main"):
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    done = status == "completed"
    return {
        "schema_version": "context-v1",
        "run_id": f"{run}:{role}",
        "call_index": index,
        "segment_id": 0,
        "role": role,
        "purpose": "task",
        "attempt": 1,
        "status": status,
        "profile": {"model_id": model},
        "manifest": {"builder_version": "context-builder-v1"},
        "request_hash": "a" * 64,
        "returned_model": None,
        "response_id": None,
        "usage": usage if done else None,
        "usage_status": "exact" if done else "unknown",
        "cost_status": "unknown",
        "error_code": None,
        "duration_ms": 3,
    }


def analysis(strategy="adaptive_multi", roles=("evidence", "impact"), **updates):
    ids = {"fixed": "R0", "single": "R1", "static_multi": "R2", "adaptive_multi": "R3"}
    subtasks = [
        {"subtask_id": role, "role": role, "status": "complete", "claims": [], "missing": []}
        for role in roles
    ]
    return {
        "status": "complete",
        "strategy": strategy,
        "strategy_id": ids[strategy],
        "routing": {
            "forced": True,
            "roles": dict.fromkeys(roles, "first_round"),
            "signals": {"offer_count": 1, "feasible_purchases": 1},
            "prompt_hash": "c" * 64,
        },
        "profiles": {role: {"model_id": "main"} for role in roles},
        "subtasks": subtasks,
        "merged": {
            "claims": [
                {
                    "statement": "B20 covers day 3",
                    "support": ["proposal"],
                    "asserted_by": ["impact"],
                }
            ],
            "missing": [],
            "conflicts": [],
            "clarification": None,
        },
        "followup": {"status": "none", "unserved": []},
        "budget": {"model_calls": len(roles), "tool_calls": 0},
        "call_records": [call(role) for role in roles],
        **updates,
    }


def export(result, *, observations=ORACLE):
    from shopsteward_pt.case_eval.strategy_trace import strategy_trace

    return strategy_trace(
        contract(),
        result,
        run_id="run-1",
        replicate_id=1,
        observations=observations,
        solver_version="recovery_solver_v1",
        adapter_version="daily-allocation-v1",
    )


def score(trace):
    from shopsteward_pt.case_eval.models import RubricDefinition
    from shopsteward_pt.case_eval.scoring import score_case

    return score_case(contract(), trace, RubricDefinition())


def observed(trace):
    return {item.observation_id: item.value for item in trace.observations}


def test_single_and_multi_agent_runs_are_scored_by_the_same_contract():
    multi = export(analysis())
    single = export(analysis("single", ("single",)))
    assert (multi.strategy_id, single.strategy_id) == ("R3", "R1")
    assert score(multi).task_success is True and score(single).task_success is True
    assert {item.role for item in multi.calls} == {"expert"}
    assert {item.role for item in single.calls} == {"root"}
    assert multi.calls_complete and multi.trace_complete
    assert multi.builder_version == "context-builder-v1"
    assert multi.model_snapshot == "main"
    assert json.loads(multi.response_text)["claims"][0]["statement"] == "B20 covers day 3"


def test_collaboration_diagnostics_are_observations_not_success_evidence():
    result = analysis(
        roles=("evidence", "impact"),
        followup={"status": "dispatched", "role": "options", "unserved": [{"question": "x"}]},
    )
    result["subtasks"].append(
        {"subtask_id": "options:followup", "role": "options", "status": "partial", "claims": []}
    )
    result["merged"]["conflicts"] = [{"type": "applicability", "positions": []}]
    result["merged"]["claims"][0]["asserted_by"] = ["evidence", "impact"]
    trace = export(result)
    assert {key: value for key, value in observed(trace).items() if key.startswith("collab.")} == {
        "collab.instances": 3,
        "collab.followup_dispatched": True,
        "collab.unserved_followups": 1,
        "collab.unsettled_conflicts": 1,
        "collab.repeated_assertions": 1,
        "collab.model_calls": 2,
        "collab.tool_calls": 0,
    }
    # The run's own bookkeeping never substitutes for the oracle's business facts.
    without_oracle = export(result, observations=[])
    assert score(without_oracle).task_success is None


def test_inflight_or_unstarted_runs_are_not_reported_as_complete_traces():
    reserved = analysis()
    reserved["call_records"][1] = call("impact", status="reserved")
    trace = export(reserved)
    assert (trace.calls_complete, trace.trace_complete) == (False, False)

    for status in ("disabled", "unavailable"):
        idle = export({"status": status, "subtasks": [], "call_records": []})
        assert (idle.attempted, idle.run_status, idle.response_text) == (False, "not_started", None)
        assert idle.strategy_id == "unassigned"
        assert score(idle).task_success is not True


def test_all_failed_run_keeps_its_cost_and_provider_failure_status():
    failed = analysis()
    for subtask in failed["subtasks"]:
        subtask.update(status="failed", missing=["AGENT_MODEL_DEADLINE"])
    failed["status"] = "partial"
    trace = export(failed)
    assert (trace.run_status, trace.response_text) == ("timeout", None)
    assert len(trace.calls) == 2
    assert score(trace).task_success is not True


def test_role_models_and_one_clarification_are_carried_into_the_trace():
    result = analysis()
    result["profiles"]["evidence"] = {"model_id": "light"}
    result["merged"]["clarification"] = {"requested_by": "evidence", "question": "Which order?"}
    trace = export(result)
    assert trace.model_snapshot == "evidence=light;impact=main"
    assert trace.clarification_questions == ("Which order?",)
    same = export(analysis())
    assert trace.profile_hash != same.profile_hash and trace.prompt_hash == "c" * 64


def test_caller_cannot_shadow_runtime_diagnostics():
    from pydantic import ValidationError

    forged = [*ORACLE, {**ORACLE[0], "observation_id": "collab.model_calls", "value": 0}]
    with pytest.raises(ValidationError, match="duplicate observation"):
        export(analysis(), observations=forged)


@pytest.mark.asyncio
async def test_a_real_runner_result_exports_and_scores():
    pytest.importorskip("langgraph")
    from shopsteward_agent.cases import BoundedCaseRunner, CallBudget, run_strategy
    from shopsteward_agent.context import ModelProfile

    class Model:
        async def complete(self, messages, tools, **kwargs):
            return {
                "content": json.dumps(
                    {
                        "claims": [{"statement": "B20 covers day 3", "support": ["proposal"]}],
                        "missing": [],
                        "followup_requests": [],
                    }
                ),
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }

    records = {}

    async def record(item):
        records[(item["run_id"], item["role"], item["call_index"])] = item

    runner = BoundedCaseRunner(
        model=Model(),
        profile=ModelProfile(model_id="main"),
        tools=[],
        call_tool=None,
        budget=CallBudget(),
        record_call=record,
    )
    roles = ("fixed", "single", "evidence", "impact", "options")
    result = await run_strategy(
        runner,
        "static_multi",
        base={
            "case_id": "c",
            "revision_id": "1",
            "run_id": "root",
            "allowed_scope": {"store_id": "s"},
            "supplied_evidence_ids": ["proposal"],
        },
        questions={role: f"Q:{role}" for role in roles},
        forced=True,
    )
    trace = export({**result, "call_records": list(records.values())})
    assert (trace.strategy_id, len(trace.calls), trace.calls_complete) == ("R2", 3, True)
    assert observed(trace)["collab.repeated_assertions"] == 1
    assert score(trace).task_success is True
