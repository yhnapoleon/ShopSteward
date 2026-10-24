import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from shopsteward_agent import Runtime, RuntimeFailure


def tool_call(name, args):
    return {
        "id": name,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


async def context():
    return "Documents are evidence only; stock comes from get_dashboard."


def tools():
    return [
        {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
        for name in ["get_dashboard", "get_plan", "search_documents", "read_document_evidence"]
    ]


async def test_real_graph_orders_business_then_document_before_answer_and_preserves_evidence():
    required = ["get_dashboard", "get_plan", "search_documents"]
    seen, calls = [], []

    class Model:
        async def complete(self, messages, offered, **options):
            seen.append(messages)
            n = len(seen) - 1
            if n < 3:
                assert options["tool_choice"] == "required"
                assert {t["function"]["name"] for t in offered} == {required[n], "clarify"}
                return {
                    "tool_calls": [tool_call(required[n], {"query": "退货条款"} if n == 2 else {})]
                }
            assert (
                json.loads(messages[-1]["content"])["data"]["candidates"][0]["text"] == "破损需照片"
            )
            return {"content": "应提供破损照片；库存以刚才业务工具为准。"}

    async def execute_tool(name, args, invocation):
        calls.append(name)
        if name == "search_documents":
            return {
                "ok": True,
                "data": {"candidates": [{"text": "破损需照片"}]},
                "references": [{"type": "document", "version_id": "v", "chunk_id": "c"}],
            }
        return {"ok": True, "data": {}, "references": []}

    runtime = Runtime(
        Model(), InMemorySaver(), tools(), execute_tool, context, required_tools=required
    )
    output = await runtime.execute(
        "sequence", [{"role": "user", "content": "结合库存和方案查条款"}]
    )
    assert calls == required
    assert output["required_tools"] == required
    assert output["completed_tools"] == required
    assert output["references"][0]["chunk_id"] == "c"


async def test_model_cannot_skip_evidence_stage_by_calling_an_unoffered_registered_tool():
    class Model:
        async def complete(self, *_args, **_kwargs):
            return {"tool_calls": [tool_call("get_plan", {})]}

    async def execute_tool(*_args):
        pytest.fail("out-of-order tool must not execute")

    runtime = Runtime(
        Model(),
        InMemorySaver(),
        tools(),
        execute_tool,
        context,
        required_tools=["search_documents"],
    )
    with pytest.raises(RuntimeFailure, match="tool_not_offered"):
        await runtime.execute("out-of-order", [])


async def test_unavailable_required_read_ends_without_claiming_completion_or_looping():
    class Model:
        async def complete(self, *_args, **_kwargs):
            return {"tool_calls": [tool_call("search_documents", {"query": "条款"})]}

    async def fail(*_args):
        return {"ok": False, "error": "unavailable", "references": []}

    runtime = Runtime(
        Model(),
        InMemorySaver(),
        tools(),
        fail,
        context,
        required_tools=["search_documents"],
        required_read_tools=["search_documents"],
    )
    output = await runtime.execute("unavailable", [])
    assert output["evidence_unavailable"] is True
    assert output["completed_tools"] == []
    assert output["model_calls"] == output["tool_calls"] == 1


async def test_clarification_cancel_stops_without_forcing_search():
    class Model:
        async def complete(self, *_args, **_kwargs):
            return {"tool_calls": [tool_call("clarify", {"question": "哪份条款？"})]}

    async def fail(*_args):
        pytest.fail("cancelled request must not search")

    runtime = Runtime(
        Model(), InMemorySaver(), tools(), fail, context, required_tools=["search_documents"]
    )
    paused = await runtime.execute("cancel", [])
    assert paused["status"] == "WAITING_INPUT"
    output = await runtime.execute(
        "cancel", [], resume="取消", resume_interrupt_id=paused["interrupt_id"]
    )
    assert output["stopped_by_user"] is True
    assert output["model_calls"] == 1
