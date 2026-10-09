import pytest


def test_paired_replays_are_independent_and_use_frozen_target():
    from app.learning.evaluation import paired_metrics

    rows = [
        dict(
            id=str(i),
            suite="normal",
            baseline={"success": True, "tool_calls": 10, "corrections": 2},
            candidate={"success": True, "tool_calls": 8, "corrections": 1},
        )
        for i in range(20)
    ]
    result = paired_metrics(rows, target="tool_calls_reduction", source_ids=set())
    assert result["independent_cases"] == 20
    assert result["improvement"] == pytest.approx(0.2)
    assert (
        result["quality_delta_lower"] < -0.02
    )  # 20 zero-loss cases do not prove 2% noninferiority.
    with pytest.raises(ValueError, match="independent"):
        paired_metrics(rows, target="tool_calls_reduction", source_ids={"0"})
    with pytest.raises(ValueError, match="unique"):
        paired_metrics(rows + [rows[0]], target="tool_calls_reduction", source_ids=set())


def test_unknown_result_never_becomes_success():
    from app.learning.evaluation import paired_metrics

    rows = [
        dict(
            id="a",
            suite="normal",
            baseline={"success": True, "tool_calls": 10, "corrections": 2},
            candidate={"success": None, "tool_calls": 8, "corrections": 1},
        )
    ]
    with pytest.raises(ValueError):
        paired_metrics(rows, target="tool_calls_reduction", source_ids=set())


def test_conditions_require_server_facts_and_unknown_means_no_match():
    from app.learning.retrieval import applicable

    spec = {
        "preconditions": ["current_case"],
        "exclusions": ["unknown_execution"],
        "required_tools": ["read"],
    }
    assert not applicable(spec, {"current_case": True}, {"read"})
    assert applicable(spec, {"current_case": True, "unknown_execution": False}, {"read"})
    assert not applicable(spec, {"current_case": True, "unknown_execution": True}, {"read"})
    assert not applicable(spec, {"current_case": True, "unknown_execution": False}, set())
