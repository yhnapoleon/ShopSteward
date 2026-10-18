import runpy
from pathlib import Path


def report_functions():
    return runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/report_repair_eval.py")
    )


def test_followup_denominator_includes_missing_steps_and_all_calls():
    summarize = report_functions()["summarize_followups"]
    specs = [{"episode_id": key, "followup_user_message": "change to 23"} for key in ("a", "b")]
    good = {"decision": {"name": "revise_plan"}}
    clarify = {"decision": {"name": "clarify"}}
    traces = [
        {"episode_id": "a", "steps": [clarify, good]},
        {"episode_id": "b", "steps": [clarify, clarify]},
    ]
    scores = [
        {
            "episode_id": "a",
            "decision_success": True,
            "per_step": [{}, {"action_correct": True, "arguments_correct": True}],
        },
        {
            "episode_id": "b",
            "decision_success": False,
            "per_step": [{}, {"action_correct": False, "arguments_correct": False}],
        },
    ]
    result = summarize(specs, traces, scores)
    assert result["completion"] == {"correct": 1, "total": 2, "rate": 0.5}
    assert result["repeated_clarification"] == {"correct": 1, "total": 2, "rate": 0.5}
    assert result["model_calls_per_success"] == 4
    traces[1]["steps"] = [clarify]
    scores[1]["per_step"] = [{}]
    result = summarize(specs, traces, scores)
    assert result["completion"]["total"] == 2
    assert result["completion"]["correct"] == 1
    assert result["model_calls_per_success"] == 3
    assert result["missing_followup"] == 1


def test_pairing_keeps_regressions_even_when_net_change_is_zero():
    compare = report_functions()["compare_scores"]
    before = [
        {"episode_id": "a", "decision_success": True},
        {"episode_id": "b", "decision_success": False},
    ]
    after = [
        {"episode_id": "a", "decision_success": False},
        {"episode_id": "b", "decision_success": True},
    ]
    result = compare(before, after, "decision")
    assert result["fixed"] == ["b"]
    assert result["regressed"] == ["a"]
    assert result["persistent_failures"] == []
