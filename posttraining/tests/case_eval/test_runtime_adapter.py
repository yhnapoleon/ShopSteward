import pytest


def record(**updates):
    from shopsteward_agent.context.contracts import CallRecord

    return CallRecord(
        run_id="run",
        call_index=1,
        status="completed",
        profile={"model_id": "fake"},
        manifest={},
        request_hash="a" * 64,
        **updates,
    )


def test_reserved_updates_are_not_double_counted_and_absent_usage_remains_unknown():
    from shopsteward_pt.case_eval.runtime_adapter import adapt_runtime_calls

    completed = record(
        usage={
            "input_tokens": 10,
            "output_tokens": 3,
            "total_tokens": 13,
            "input_token_details": {"cache_read": 4},
            "output_token_details": {"reasoning": 1},
        },
        usage_status="exact",
    )
    reserved = completed.model_copy(
        update={"status": "reserved", "usage": None, "usage_status": "unknown"}
    )
    adapted = adapt_runtime_calls((reserved, completed))
    assert len(adapted.calls) == 1
    assert adapted.calls[0].input_tokens == 10
    assert adapted.calls[0].cached_input_tokens == 4
    assert adapted.calls[0].reasoning_tokens == 1
    assert adapted.calls[0].cost is None
    assert adapted.calls_complete is True
    unknown = adapt_runtime_calls((record(),))
    assert unknown.calls[0].input_tokens is None
    assert unknown.calls[0].cost is None


def test_inflight_call_and_arbitrary_dict_cannot_claim_complete_runtime_ledger():
    from shopsteward_pt.case_eval.runtime_adapter import adapt_runtime_calls

    reserved = record().model_copy(update={"status": "reserved"})
    assert adapt_runtime_calls((reserved,)).calls_complete is False
    with pytest.raises(TypeError, match="CallRecord"):
        adapt_runtime_calls(({"usage": {"input_tokens": 1}},))


def test_conflicting_terminal_usage_and_unknown_roles_are_rejected():
    from shopsteward_pt.case_eval.runtime_adapter import adapt_runtime_calls

    completed = record()
    changed = completed.model_copy(update={"usage": {"input_tokens": 10}, "usage_status": "exact"})
    with pytest.raises(ValueError, match="conflicting terminal"):
        adapt_runtime_calls((completed, changed))
    with pytest.raises(ValueError, match="explicit role mapping"):
        adapt_runtime_calls((record(role="applicability"),))
    mapped = adapt_runtime_calls(
        (record(role="applicability"),), role_map={"applicability": "expert"}
    )
    assert mapped.calls[0].role == "expert"
