"""Typed claims are checked against the solver; prose is neither credited nor penalized."""


def days(*lost):
    return [{"lost_qty": quantity} for quantity in lost]


PROPOSAL = {
    "recommended_candidate_id": "B_20",
    "candidates": [
        {"id": "wait", "feasible": True, "daily": days(0, 0, 10, 10, 0, 0, 0)},
        {"id": "B_20", "feasible": True, "daily": days(0, 0, 0, 0, 0, 0, 0)},
        {"id": "A_40", "feasible": False, "daily": days(0, 0, 0, 0, 0, 0, 0)},
    ],
}


def typed(kind, target, result, **extra):
    return {
        "statement": f"{kind} {target} {result}",
        "support": ["proposal"],
        "subject": {"type": kind, "id": target},
        "applicability": {"result": result},
        **extra,
    }


def test_required_conditions_are_the_decision_its_effect_and_the_cost_of_waiting():
    from shopsteward_pt.strategy_eval.claims import required_conditions

    assert required_conditions(PROPOSAL) == [
        "candidate:B_20=recommended",
        "gap:B_20=none",
        "gap:wait=day-3",
    ]
    waiting = {**PROPOSAL, "recommended_candidate_id": "wait"}
    assert required_conditions(waiting) == ["candidate:wait=recommended", "gap:wait=day-3"]


def test_only_correct_typed_claims_count_and_prose_is_ignored():
    from shopsteward_pt.strategy_eval.claims import check_claims

    checked = check_claims(
        [
            typed("candidate", "B_20", "recommended"),
            typed("candidate", "A_40", "rejected"),
            typed("gap", "wait", "day-3"),
            {"statement": "B20 obviously closes the gap", "support": ["proposal"]},
        ],
        PROPOSAL,
    )
    assert checked["covered"] == ["candidate:B_20=recommended", "gap:wait=day-3"]
    assert round(checked["coverage"], 3) == 0.667
    assert checked["contradictions"] == [] and checked["unverifiable"] == 0


def test_wrong_status_wrong_day_and_invented_candidates_are_contradictions():
    from shopsteward_pt.strategy_eval.claims import check_claims

    checked = check_claims(
        [
            typed("candidate", "wait", "recommended"),
            typed("candidate", "A_40", "feasible"),
            typed("gap", "wait", "day-4", asserted_by=["impact:followup"]),
            typed("gap", "B_20", "day-1"),
            typed("candidate", "Z_99", "feasible"),
        ],
        PROPOSAL,
    )
    assert [item["claim"] for item in checked["contradictions"]] == [
        "candidate:wait=recommended",
        "candidate:A_40=feasible",
        "gap:wait=day-4",
        "gap:B_20=day-1",
        "candidate:Z_99=feasible",
    ]
    assert checked["coverage"] == 0


def test_out_of_vocabulary_results_are_unverifiable_not_wrong():
    from shopsteward_pt.strategy_eval.claims import check_claims

    checked = check_claims(
        [typed("gap", "wait", "shortage"), typed("candidate", "B_20", "best")], PROPOSAL
    )
    assert (checked["unverifiable"], checked["contradictions"], checked["covered"]) == (2, [], [])


def test_mast_tags_come_only_from_what_the_ledger_proves():
    from shopsteward_pt.strategy_eval.mast import mast_tags

    read = {"subtask_id": "impact", "name": "read_case_snapshot", "args_hash": "h"}
    analysis = {
        "subtasks": [
            {"subtask_id": "evidence", "status": "failed", "missing": ["AGENT_MODEL_BUDGET"]},
            {"subtask_id": "impact", "status": "failed", "missing": ["AGENT_TOOL_NOT_OFFERED"]},
        ],
        "tool_log": [read, read],
        "merged": {"conflicts": [{"type": "uncited_calculation"}]},
    }
    wrong = {"coverage": 0, "contradictions": [{"asserted_by": ["evidence:followup"]}]}
    assert mast_tags(analysis, wrong) == ["FM-1.2", "FM-1.3", "FM-1.5", "FM-3.2", "FM-3.3"]

    done = {"subtasks": [{"subtask_id": "single", "status": "complete", "missing": []}]}
    assert mast_tags(done, {"coverage": 0.5, "contradictions": []}) == ["FM-3.1"]
    assert mast_tags(done, {"coverage": 1.0, "contradictions": []}) == []


def run_record(case, bundle, *, ok, score, calls, **extra):
    return {
        "case_id": case,
        "replicate": 1,
        "strategy": "single",
        "bundle": bundle,
        "partition": "gate",
        "task_success": ok,
        "score": score,
        "model_calls": calls,
        "critical_failures": [],
        "contradictions": [],
        **extra,
    }


def test_gate_pairs_runs_by_case_and_names_every_loss():
    import pytest

    from shopsteward_pt.strategy_eval.runner import gate_report

    records = [
        run_record("a", "seed", ok=False, score=0.0, calls=2),
        run_record("b", "seed", ok=True, score=1.0, calls=2),
        run_record("a", "r1", ok=True, score=1.0, calls=2),
        run_record("b", "r1", ok=True, score=1.0, calls=2),
        run_record("c", "r1", ok=True, score=1.0, calls=2),  # unpaired: not counted
    ]
    report = gate_report(records, strategy="single", baseline="seed", candidate="r1")
    assert (report["paired_runs"], report["gains"], report["losses"]) == (2, ["a"], [])
    assert report["task_success"] == {"baseline": 1, "candidate": 2}
    assert report["verdict"] == "pass"

    worse = [*records[:2], run_record("a", "r2", ok=True, score=1.0, calls=2)]
    worse.append(
        run_record("b", "r2", ok=False, score=0.0, calls=2, contradictions=["gap:wait=none"])
    )
    failed = gate_report(worse, strategy="single", baseline="seed", candidate="r2")
    assert failed["losses"] == ["b"] and failed["verdict"] == "fail"
    assert failed["checks"] == {
        "no_critical_failure_or_contradiction": False,
        "no_observed_loss": False,
        "improved": False,
    }
    with pytest.raises(ValueError, match="no paired gate runs"):
        gate_report(records, strategy="fixed", baseline="seed", candidate="r1")
