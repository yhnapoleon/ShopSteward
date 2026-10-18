from test_scorers import example, score


def test_full_parameter_denominator_includes_wrong_tool_and_cost_includes_failure():
    from shopsteward_pt.eval.records import EpisodeTrace
    from shopsteward_pt.reporting import summarize

    spec, good = example()
    good["cost"] = {"amount": 1.0, "currency": "USD"}
    _, bad = example()
    bad["steps"][0]["decision"] = {
        "name": "handoff",
        "arguments": {"reason": "unsupported_request"},
    }
    bad["cost"] = {"amount": 2.0, "currency": "USD"}
    summary = summarize(
        [score(spec, good), score(spec, bad)], [EpisodeTrace.model_validate(t) for t in [good, bad]]
    )
    assert summary["arguments_accuracy"] == {"correct": 1, "total": 2, "rate": 0.5}
    assert summary["cost"]["per_success"] == 3.0
    assert summary["core_success"]["total"] == 2


def test_missing_price_is_not_zero_and_decision_has_no_execution_success():
    from shopsteward_pt.eval.records import EpisodeTrace
    from shopsteward_pt.reporting import summarize

    spec, trace = example()
    trace["mode"] = "decision"
    summary = summarize([score(spec, trace)], [EpisodeTrace.model_validate(trace)])
    assert summary["cost"]["amount"] is None
    assert summary["core_success"] is None
