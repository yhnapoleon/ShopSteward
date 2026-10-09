import pytest


def contracts():
    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    return AdmissionBoundary, ContextBuilder, MessageEnvelope, ModelProfile


def test_long_history_keeps_first_constraint_and_excludes_future_inputs():
    Admission, Builder, Message, Profile = contracts()
    messages = [
        Message(
            message_id=f"m{i}",
            run_id=f"r{i}",
            seq=i,
            role="user",
            content=("预算最多200元" if i == 1 else f"input {i}"),
        )
        for i in range(1, 102)
    ]
    view = Builder(Profile(model_id="test", max_input_tokens=24000)).build(
        admission=Admission(run_id="r100", conversation_id="c", input_through_seq=100),
        messages=messages,
        system="rules",
        tools=[],
        current_context="current",
    )
    rendered = str(view.messages)
    assert "预算最多200元" in rendered
    assert "input 101" not in rendered
    assert "m1" in view.manifest["selected_source_ids"]
    assert view.manifest["omitted"] == [{"source_id": "m101", "reason": "admission"}]


def test_required_content_overflow_is_not_silently_truncated():
    Admission, Builder, Message, Profile = contracts()
    from shopsteward_agent.context import ContextOverflow

    with pytest.raises(ContextOverflow, match="CONTEXT_REQUIRED_OVERFLOW"):
        Builder(Profile(model_id="test", max_input_tokens=100)).build(
            admission=Admission(run_id="r", conversation_id="c", input_through_seq=1),
            messages=[
                Message(message_id="m", run_id="r", seq=1, role="user", content="限制" * 500)
            ],
            system="rules",
            tools=[],
            current_context="current",
        )


def test_frame_patch_preserves_unmentioned_constraint_and_validates_exact_quote():
    from shopsteward_agent.context import TaskFrame, apply_patch

    frame = TaskFrame(run_id="r", constraints=[])
    frame = apply_patch(
        frame,
        [
            {
                "key": "quantity",
                "operator": "lte",
                "value": 20,
                "source_message_id": "a",
                "exact_quote": "最多20件",
                "source_span": [0, 5],
            }
        ],
        {"a": "最多20件"},
    )
    revised = apply_patch(
        frame,
        [
            {
                "key": "budget",
                "operator": "eq",
                "value": 0,
                "source_message_id": "b",
                "exact_quote": "预算为0",
                "source_span": [0, 4],
            }
        ],
        {"b": "预算为0"},
    )
    assert {c.key: c.value for c in revised.constraints} == {"quantity": 20, "budget": 0}
    assert revised.parent_frame_id == frame.frame_id
    with pytest.raises(ValueError, match="quote"):
        apply_patch(
            revised,
            [
                {
                    "key": "quantity",
                    "operator": "unset",
                    "source_message_id": "b",
                    "exact_quote": "取消上限",
                    "source_span": [0, 4],
                }
            ],
            {"b": "预算为0"},
        )


def test_source_dependency_change_invalidates_derived_blocks():
    from shopsteward_agent.context import valid_dependencies

    assert valid_dependencies({"knowledge:u": "2"}, {"knowledge:u": "2"})
    assert not valid_dependencies({"knowledge:u": "1"}, {"knowledge:u": "2"})
    assert not valid_dependencies({"document:d": "1"}, {})


def test_admission_allows_only_named_resume_and_earlier_run_answers():
    Admission, Builder, Message, Profile = contracts()
    boundary = Admission(
        run_id="r",
        conversation_id="c",
        input_through_seq=2,
        admitted_resume_message_ids=["resume"],
        prior_run_dependencies=["prior"],
    )
    inputs = [
        Message(
            message_id="late-answer",
            seq=6,
            run_id="prior",
            role="assistant",
            content="prior answer",
        ),
        Message(message_id="future", seq=3, run_id="future", role="user", content="future user"),
        Message(message_id="resume", seq=5, run_id="r", role="user", content="answer to clarify"),
    ]
    view = Builder(Profile(model_id="test")).build(
        admission=boundary, messages=inputs, system="rules", tools=[], current_context=""
    )
    assert "future user" not in str(view.messages)
    assert "answer to clarify" in str(view.messages)
    assert "prior answer" in str(view.messages)


def test_live_builder_extracts_budget_and_quantity_revisions_with_source_quotes():
    Admission, Builder, Message, Profile = contracts()
    inputs = [
        Message(message_id=f"m{i}", run_id="r", seq=i, role="user", content=text)
        for i, text in enumerate(
            ["预算300元，最多40件", "预算200元", "取消数量上限", "本次恰好20件"], start=1
        )
    ]
    view = Builder(Profile(model_id="test")).build(
        admission=Admission(run_id="r", conversation_id="c", input_through_seq=4),
        messages=inputs,
        system="rules",
        tools=[],
        current_context="",
    )
    constraints = {c.key: c for c in view.frame.constraints}
    assert constraints["budget"].value == 20000
    assert constraints["budget"].source_message_id == "m2"
    assert constraints["quantity"].operator == "eq"
    assert constraints["quantity"].value == 20
    assert constraints["quantity"].exact_quote == "恰好20件"
    assert view.frame.validation_status == "validated"
    assert "task_frame" in str(view.messages)


def test_scenario_quantity_does_not_replace_real_constraint_and_zero_is_preserved():
    from shopsteward_agent.context.frame import extract_frame

    frame = extract_frame(
        "r",
        [
            {"message_id": "one", "content": "本次最多40件，预算0元"},
            {"message_id": "two", "content": "假如买20件会怎样"},
        ],
    )
    assert {(c.key, c.scope): c.value for c in frame.constraints} == {
        ("quantity", "one_run"): 40,
        ("budget", "one_run"): 0,
        ("quantity", "scenario"): 20,
    }


def test_ambiguous_quantity_is_exposed_instead_of_silently_overwriting():
    from shopsteward_agent.context.frame import extract_frame

    frame = extract_frame(
        "r",
        [
            {"message_id": "one", "content": "最多40件"},
            {"message_id": "two", "content": "最多20或者30件"},
        ],
    )
    assert frame.constraints[0].value == 40
    assert "quantity_unparsed:two" in frame.unresolved


def test_long_term_memory_commands_do_not_become_per_run_constraints():
    from shopsteward_agent.context.frame import extract_frame

    frame = extract_frame(
        "r",
        [
            {"message_id": "one", "content": "请记住我默认预算300元"},
            {"message_id": "two", "content": "删除这个预算偏好"},
        ],
    )
    assert frame.constraints == []


def test_read_only_trial_quantity_does_not_overwrite_actual_constraint():
    from shopsteward_agent.context.frame import extract_frame

    frame = extract_frame(
        "r",
        [
            {"message_id": "one", "content": "本次最多40件"},
            {"message_id": "two", "content": "只试算最多20件，不要保存"},
        ],
    )
    assert {(c.key, c.scope): c.value for c in frame.constraints} == {
        ("quantity", "one_run"): 40,
        ("quantity", "scenario"): 20,
    }
    assert frame.requested_effect == "read_only"
    assert frame.effect_source_message_id == "two"


@pytest.mark.parametrize(
    "messages, allowed, denied",
    [
        (["请把方案修改为最多20件，不要下单"], {"revise_plan"}, set()),
        (["请保存这个偏好，不要修改当前方案"], {"memory_edit"}, {"revise_plan"}),
        (["只试算，不要保存", "请把数量上限改成20件"], {"revise_plan"}, set()),
        (["只试算，不要保存", "Change the maximum to 20 items"], {"revise_plan"}, set()),
        (["只试算，不要保存", "20件"], set(), {"revise_plan", "memory_edit", "request_check"}),
    ],
)
def test_intent_denials_are_targeted_and_explicit_revisions_replace_readonly(
    messages, allowed, denied
):
    from shopsteward_agent.context.intent import classify_intent

    result = classify_intent(
        [{"message_id": str(i), "content": text} for i, text in enumerate(messages)]
    )
    assert not allowed & set(result["denied_tools"])
    assert denied <= set(result["denied_tools"])


@pytest.mark.parametrize(
    "question",
    [
        "只试算，不要保存，数量上限改成20件",
        "不要保存，先把数量上限改成20件试算一下",
        "数量上限改成20件，只试算，不要保存",
        "不要保存，数量上限改成20件，只试算",
        "只试算，数量上限改成20件，不要保存",
        "Only simulate, do not save, change the maximum to 20 items",
    ],
)
def test_same_message_prohibition_dominates_scenario_change_regardless_of_clause_order(question):
    from shopsteward_agent.context.intent import classify_intent

    result = classify_intent([{"message_id": "m", "content": question}])
    assert set(result["denied_tools"]) == {
        "revise_plan",
        "memory_edit",
        "request_check",
        "analyze_recovery_case",
    }
    assert result["requested_effect"] == "read_only"
    assert result["effect_exact_quote"] in {"只试算", "不要保存", "Only simulate", "do not save"}
    for source in result["denied_tool_sources"].values():
        start, end = source["effect_source_span"]
        assert question[start:end] == source["effect_exact_quote"]


@pytest.mark.parametrize(
    "command",
    [
        "删除这个偏好",
        "忘记这个偏好",
        "纠正这个偏好",
        "更正这个偏好",
        "清除这个偏好",
        "更新这个偏好",
        "Forget this preference",
        "Delete this preference",
        "Update this preference",
        "Correct this preference",
    ],
)
def test_later_explicit_memory_command_replaces_only_memory_prohibition(command):
    from shopsteward_agent.context.intent import classify_intent

    result = classify_intent(
        [
            {"message_id": "old", "content": "只试算，不要保存"},
            {"message_id": "new", "content": command},
        ]
    )
    assert set(result["denied_tools"]) == {"revise_plan", "request_check", "analyze_recovery_case"}
    assert result["requested_effect"] == "write"
    assert result["effect_source_message_id"] == "new"


def test_same_message_targeted_denial_does_not_block_different_target():
    from shopsteward_agent.context.intent import classify_intent

    result = classify_intent(
        [
            {"message_id": "old", "content": "只试算，不要保存"},
            {"message_id": "new", "content": "不要修改当前方案，请保存这个偏好"},
        ]
    )
    assert set(result["denied_tools"]) == {"revise_plan", "request_check", "analyze_recovery_case"}
