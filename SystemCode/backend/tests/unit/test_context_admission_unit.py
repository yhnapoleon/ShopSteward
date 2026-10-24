from types import SimpleNamespace


def test_mission_sources_preserve_old_constraints_without_admitting_future_turns():
    from app.agent_bridge.context_sources import ASSISTANT_HISTORY, admitted_history

    rows = [
        SimpleNamespace(
            id=f"m{i}",
            seq=i,
            run_id=f"r{i}",
            role="user",
            content=("保留预算限制" if i == 1 else str(i)),
        )
        for i in range(1, 102)
    ]
    rows += [
        SimpleNamespace(
            id="old-answer", seq=103, run_id="r1", role="assistant", content="earlier answer"
        ),
        SimpleNamespace(
            id="future-answer", seq=104, run_id="r101", role="assistant", content="future answer"
        ),
        SimpleNamespace(id="resume", seq=105, run_id="r100", role="user", content="clarified"),
    ]
    history, admission = admitted_history(
        rows, run_id="r100", conversation_id="c", input_through_seq=100, prior_run_ids=["r1"]
    )
    assert history[0]["content"] == "保留预算限制"
    assert len([m for m in history if m["role"] == "user"]) == 101
    assert not any(m["message_id"] in {"m101", "future-answer"} for m in history)
    assert admission["admitted_resume_message_ids"] == ["resume"]
    assert history[1]["message_id"] == "old-answer"
    # Later proactive answers push out the oldest answer, never a user message.
    rows += [
        SimpleNamespace(id=f"f{i}", seq=105 + i, run_id=f"f{i}", role="assistant", content="")
        for i in range(1, ASSISTANT_HISTORY + 1)
    ]
    prior = ["r1", *(f"f{i}" for i in range(1, ASSISTANT_HISTORY + 1))]
    history, _ = admitted_history(
        rows, run_id="r100", conversation_id="c", input_through_seq=100, prior_run_ids=prior
    )
    assert [m["role"] for m in history].count("user") == 101
    assert "old-answer" not in [m["message_id"] for m in history]
    assert history[-1]["message_id"] == f"f{ASSISTANT_HISTORY}"


def test_explicit_no_save_survives_clarification_and_can_be_replaced_by_explicit_save():
    from app.agent_bridge.context_sources import requested_effect

    assert requested_effect(["只试算最多20件，不要保存", "20件"]) == "read_only"
    assert requested_effect(["只试算最多20件，不要保存", "现在保存这个修改"]) == "write"
