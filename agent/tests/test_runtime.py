import asyncio

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import shopsteward_agent as package


def test_public_runtime_exists():
    assert hasattr(package, "Runtime")


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.seen = []

    async def complete(self, messages, tools, **kwargs):
        self.seen.append(messages)
        return next(self.replies)


def call(name="read", args=None, id="vendor"):
    return {
        "id": id,
        "type": "function",
        "function": {"name": name, "arguments": args or "{}"},
    }


async def context():
    return "fresh context"


async def tool(name, args, invocation_id):
    return {"ok": True, "references": [{"id": "fact-1"}], "receipt": invocation_id}


def runtime(model, saver=None, **kwargs):
    return package.Runtime(
        model,
        saver or InMemorySaver(),
        [
            {
                "type": "function",
                "function": {"name": "read", "parameters": {"type": "object"}},
            }
        ],
        tool,
        context,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_loop_references_and_completed_recovery():
    model = Model([{"content": "", "tool_calls": [call()]}, {"content": "Answer"}])
    run = runtime(model)
    result = await run.execute("r1", [{"role": "user", "content": "question"}])
    assert result["content"] == "Answer"
    assert result["references"] == [{"id": "fact-1"}]
    assert result["model_calls"] == 2 and result["tool_calls"] == 1
    assert model.seen[1][-1]["role"] == "tool"
    assert await run.execute("r1", []) == result


@pytest.mark.asyncio
async def test_interrupt_resume_and_new_run_isolation():
    model = Model(
        [
            {"tool_calls": [call("clarify", '{"question":"Which store?"}')]},
            {"content": "Resumed"},
            {"content": "New"},
        ]
    )
    run = runtime(model)
    waiting = await run.execute("old", [{"role": "user", "content": "old input"}])
    assert waiting["status"] == "WAITING_INPUT" and waiting["interrupt_id"]
    result = await run.execute("old", [], resume="A")
    assert result["content"] == "Resumed"
    await run.execute("new", [{"role": "user", "content": "new input"}])
    assert not any(m.get("content") == "old input" for m in model.seen[-1])


@pytest.mark.asyncio
async def test_resume_receipt_survives_terminal_checkpoint_and_next_interrupt():
    model = Model(
        [
            {"tool_calls": [call("clarify", '{"question":"First?"}')]},
            {"tool_calls": [call("clarify", '{"question":"Second?"}', id="second")]},
            {"content": "Completed"},
        ]
    )
    run = runtime(model)
    first = await run.execute("resume-fence", [])
    second = await run.execute(
        "resume-fence", [], resume="first answer", resume_interrupt_id=first["interrupt_id"]
    )
    assert second["status"] == "WAITING_INPUT"
    replay = await run.execute(
        "resume-fence", [], resume="first answer", resume_interrupt_id=first["interrupt_id"]
    )
    assert replay["interrupt_id"] == second["interrupt_id"]
    final = await run.execute(
        "resume-fence", [], resume="second answer", resume_interrupt_id=second["interrupt_id"]
    )
    assert (
        await run.execute(
            "resume-fence", [], resume="second answer", resume_interrupt_id=second["interrupt_id"]
        )
        == final
    )


@pytest.mark.asyncio
async def test_required_business_effect_cannot_be_replaced_by_a_success_claim():
    class Required(Model):
        async def complete(self, messages, tools, **kwargs):
            assert kwargs.get("tool_choice") == "required"
            assert {t["function"]["name"] for t in tools} == {"read", "clarify"}
            return {"content": "Already saved"}

    with pytest.raises(package.RuntimeFailure, match="required_tool"):
        await runtime(Required([]), required_tools=["read"]).execute("required", [])


@pytest.mark.asyncio
async def test_bounded_loop_and_bad_protocol():
    run = runtime(Model([{"tool_calls": [call()]}] * 10), max_model_calls=2)
    with pytest.raises(package.RuntimeFailure, match="model_budget"):
        await run.execute("loop", [])
    with pytest.raises(package.RuntimeFailure, match="protocol"):
        await runtime(Model([{"tool_calls": [call(args="not json")]}] * 2)).execute("bad", [])


@pytest.mark.asyncio
async def test_deadline():
    class Slow:
        async def complete(self, messages, tools):
            await asyncio.sleep(0.05)

    with pytest.raises(package.RuntimeFailure, match="deadline"):
        await runtime(Slow(), model_timeout=0.001).execute("slow", [])


@pytest.mark.asyncio
async def test_counter_survives_interrupted_model_and_tool_replay_identity():
    saver = InMemorySaver()

    class Crashed:
        async def complete(self, messages, tools):
            raise asyncio.CancelledError()

    run = runtime(Crashed(), saver, max_model_calls=1)
    from langgraph.errors import NodeCancelledError

    with pytest.raises(NodeCancelledError):
        await run.execute("crashed", [])
    # A replay of the reserved model node is bounded by the persisted run deadline.
    second = runtime(Model([{"tool_calls": [call()]}]), saver, max_model_calls=1)
    with pytest.raises(package.RuntimeFailure, match="model_budget"):
        await second.execute("crashed", [])
    state = await second.graph.aget_state({"configurable": {"thread_id": "crashed"}})
    assert state.values["model_calls"] == 1


@pytest.mark.asyncio
async def test_failed_tool_references_excluded_and_context_reloaded():
    contexts = iter(["old memory", "new memory"])

    async def load():
        return next(contexts)

    async def failing(name, args, invocation):
        return {"ok": False, "error": "denied", "references": ["forged"]}

    model = Model([{"tool_calls": [call()]}, {"content": "denied"}])
    run = runtime(model)
    run.load_context, run.call_tool = load, failing
    result = await run.execute("failedtool", [])
    assert result["references"] == []
    assert "old memory" not in str(model.seen[1])
    assert "new memory" in str(model.seen[1])


@pytest.mark.asyncio
async def test_unknown_tool_and_tool_budget():
    with pytest.raises(package.RuntimeFailure, match="unknown_tool"):
        await runtime(Model([{"tool_calls": [call("approve")]}])).execute("unknown", [])
    with pytest.raises(package.RuntimeFailure, match="tool_budget"):
        await runtime(
            Model([{"tool_calls": [call()]}, {"tool_calls": [call()]}]), max_tool_calls=1
        ).execute("tools", [])


def test_memory_module_does_not_import_model_stack():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from shopsteward_agent.memory.hermes_policy import apply_memory_changes; assert 'langgraph' not in sys.modules",
        ],
        capture_output=True,
    )
    assert result.returncode == 0


def test_safe_failure_code():
    assert package.RuntimeFailure("model_protocol").code == "AGENT_MODEL_PROTOCOL"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"ok": True, "references": None},
        {"ok": True, "references": "bad"},
        {"ok": True, "value": object()},
        {"ok": True, "value": float("nan")},
    ],
)
async def test_malformed_tool_result_is_structured(bad):
    import json

    model = Model([{"tool_calls": [call()]}, {"content": "Handled"}])
    run = runtime(model)

    async def callback(*args):
        return bad

    run.call_tool = callback
    result = await run.execute("malformed-result", [])
    assert result["references"] == []
    assert json.loads(model.seen[-1][-1]["content"]) == {"ok": False, "error": "tool_protocol"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second, expected",
    [
        (
            {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            {"input_tokens": 15, "output_tokens": 5, "total_tokens": 20},
        ),
        (None, None),
    ],
)
async def test_usage_aggregates_or_becomes_unknown(second, expected):
    model = Model(
        [
            {
                "tool_calls": [call()],
                "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            },
            {"content": "Done", "usage": second},
        ]
    )
    assert (await runtime(model).execute("usage", []))["usage"] == expected


@pytest.mark.asyncio
async def test_protocol_repairs_once_and_counts_usage():
    model = Model(
        [
            {
                "tool_calls": [call(args="bad")],
                "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            },
            {
                "content": "Repaired",
                "usage": {"input_tokens": 4, "output_tokens": 1, "total_tokens": 5},
            },
        ]
    )
    result = await runtime(model).execute("repair", [])
    assert result["content"] == "Repaired" and result["model_calls"] == 2
    assert result["usage"]["total_tokens"] == 8
    assert "protocol" in str(model.seen[-1]).lower()
    repeating = Model([{"tool_calls": [call(args="bad")]}, {"tool_calls": [call(args="bad")]}])
    with pytest.raises(package.RuntimeFailure, match="model_protocol"):
        await runtime(repeating).execute("repair-fail", [])
    assert len(repeating.seen) == 2


@pytest.mark.asyncio
async def test_repair_malformed_name_but_never_unauthorized_name():
    malformed = Model([{"tool_calls": [call(name=None)]}, {"content": "Repaired"}])
    assert (await runtime(malformed).execute("malformed-name", []))["content"] == "Repaired"
    unauthorized = Model(
        [
            {"tool_calls": [call(args="bad"), call("approve", id="other")]},
            {"content": "Must not execute"},
        ]
    )
    with pytest.raises(package.RuntimeFailure, match="unknown_tool"):
        await runtime(unauthorized).execute("unauthorized", [])
    assert len(unauthorized.seen) == 1


@pytest.mark.asyncio
async def test_context_path_records_calls_and_keeps_active_protocol_intact():
    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    opaque = [{"type": "reasoning", "encrypted_content": "opaque", "id": "r"}]
    model = Model([{"tool_calls": [call()], "provider_items": opaque}, {"content": "Done"}])
    records = []

    async def record(value):
        records.append(value)

    run = runtime(
        model,
        context_builder=ContextBuilder(ModelProfile(model_id="test")),
        admission=AdmissionBoundary(run_id="context", conversation_id="c", input_through_seq=1),
        message_envelopes=[MessageEnvelope(message_id="m", seq=1, role="user", content="question")],
        record_call=record,
    )
    result = await run.execute("context", [{"role": "user", "content": "question"}])
    assert model.seen[1][:-2] == model.seen[0]
    assert model.seen[1][-2]["provider_items"] == opaque
    assert [r["status"] for r in records] == ["reserved", "completed", "reserved", "completed"]
    assert result["context_manifest"]["selected_source_ids"] == ["m"]
    assert result["cost_status"] == "unknown"


@pytest.mark.asyncio
async def test_context_source_change_rebuilds_without_old_tool_evidence():
    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    model = Model([{"tool_calls": [call()]}, {"content": "Done"}])
    run = runtime(
        model,
        context_builder=ContextBuilder(ModelProfile(model_id="test")),
        admission=AdmissionBoundary(run_id="change", conversation_id="c", input_through_seq=1),
        message_envelopes=[MessageEnvelope(message_id="m", seq=1, role="user", content="question")],
    )
    contexts = iter(["saved preference A", "no saved preferences"])

    async def load():
        return next(contexts)

    run.load_context = load
    result = await run.execute("change", [{"role": "user", "content": "question"}])
    assert "saved preference A" not in str(model.seen[1])
    assert not any(message.get("role") == "tool" for message in model.seen[1])
    assert result["context_manifest"]["segment_id"] == 1


@pytest.mark.asyncio
async def test_frame_blocks_revision_that_drops_unresolved_or_exact_quantity():
    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    model = Model([{"tool_calls": [call("revise_plan", '{"max_purchase_qty":20}')]}])
    executed = []

    async def write(*args):
        executed.append(args)
        return {"ok": True}

    run = package.Runtime(
        model,
        InMemorySaver(),
        [
            {
                "type": "function",
                "function": {"name": "revise_plan", "parameters": {"type": "object"}},
            }
        ],
        write,
        context,
        context_builder=ContextBuilder(ModelProfile(model_id="test")),
        admission=AdmissionBoundary(run_id="exact", conversation_id="c", input_through_seq=1),
        message_envelopes=[
            MessageEnvelope(message_id="m", seq=1, role="user", content="本次恰好20件")
        ],
    )
    with pytest.raises(package.RuntimeFailure, match="context_constraint_not_supported"):
        await run.execute("exact", [{"role": "user", "content": "本次恰好20件"}])
    assert executed == []


@pytest.mark.asyncio
async def test_newly_read_valid_document_keeps_tool_receipt_but_revocation_rebuilds():
    import json

    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    model = Model(
        [{"tool_calls": [call()]}, {"tool_calls": [call(id="second")]}, {"content": "Done"}]
    )
    run = runtime(
        model,
        context_builder=ContextBuilder(ModelProfile(model_id="test")),
        admission=AdmissionBoundary(run_id="docs", conversation_id="c", input_through_seq=1),
        message_envelopes=[MessageEnvelope(message_id="m", seq=1, role="user", content="question")],
    )
    contexts = iter([{}, {"doc": "v1"}, {}])

    async def load():
        return {
            "instructions": "rules",
            "data": json.dumps({"document_source_versions": next(contexts)}),
        }

    run.load_context = load
    result = await run.execute("docs", [{"role": "user", "content": "question"}])
    assert any(message.get("role") == "tool" for message in model.seen[1])
    assert not any(message.get("role") == "tool" for message in model.seen[2])
    assert result["context_manifest"]["segment_id"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name", ["revise_plan", "memory_edit", "request_check", "analyze_recovery_case"]
)
@pytest.mark.parametrize(
    "question",
    [
        "只试算最多20件，不要保存",
        "只试算，不要保存，数量上限改成20件",
        "不要保存，先把数量上限改成20件试算一下",
    ],
)
async def test_no_save_intent_blocks_adversarial_mutation_calls(tool_name, question):
    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    executed = []

    async def write(*args):
        executed.append(args)
        return {"ok": True}

    run = package.Runtime(
        Model([{"tool_calls": [call(tool_name, '{"max_purchase_qty":20}')]}, {"content": "done"}]),
        InMemorySaver(),
        [{"type": "function", "function": {"name": tool_name, "parameters": {"type": "object"}}}],
        write,
        context,
        context_builder=ContextBuilder(ModelProfile(model_id="test")),
        admission=AdmissionBoundary(run_id="readonly", conversation_id="c", input_through_seq=1),
        message_envelopes=[MessageEnvelope(message_id="m", seq=1, role="user", content=question)],
    )
    with pytest.raises(package.RuntimeFailure, match="read_only_intent"):
        await run.execute("readonly", [{"role": "user", "content": question}])
    assert executed == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "history, tool_name",
    [
        (["请把方案修改为最多20件，不要下单"], "revise_plan"),
        (["只试算，不要保存", "请把数量上限改成20件"], "revise_plan"),
        (["只试算，不要保存", "Change the maximum to 20 items"], "revise_plan"),
        (["请保存这个偏好，不要修改当前方案"], "memory_edit"),
        (["只试算，不要保存", "删除这个偏好"], "memory_edit"),
        (["只试算，不要保存", "Forget this preference"], "memory_edit"),
        (["只试算，不要保存", "Update this preference"], "memory_edit"),
    ],
)
async def test_targeted_denial_does_not_block_authorized_other_effect(history, tool_name):
    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    executed = []

    async def write(*args):
        executed.append(args)
        return {"ok": True}

    messages = [{"role": "user", "content": content} for content in history]
    run = package.Runtime(
        Model([{"tool_calls": [call(tool_name, '{"max_purchase_qty":20}')]}, {"content": "done"}]),
        InMemorySaver(),
        [{"type": "function", "function": {"name": tool_name, "parameters": {"type": "object"}}}],
        write,
        context,
        context_builder=ContextBuilder(ModelProfile(model_id="test")),
        admission=AdmissionBoundary(
            run_id="allowed", conversation_id="c", input_through_seq=len(history)
        ),
        message_envelopes=[
            MessageEnvelope(message_id=str(i), seq=i, role="user", content=content)
            for i, content in enumerate(history, start=1)
        ],
    )
    await run.execute("allowed", messages)
    assert len(executed) == 1
