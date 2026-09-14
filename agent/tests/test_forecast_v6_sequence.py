import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from shopsteward_agent import Runtime


@pytest.mark.parametrize("available", [True, False])
async def test_v6_evidence_reaches_real_graph_before_plan_and_stops_if_unavailable(available):
    required = ["get_dashboard", "get_forecast", "get_plan"]
    calls = []
    reference = dict(type="forecast", id="forecast-v6", version="v6", store_id="s", sku_id="k")

    class Model:
        async def complete(self, messages, offered, **options):
            if len(calls) < 3:
                name = required[len(calls)]
                assert options["tool_choice"] == "required"
                assert {t["function"]["name"] for t in offered} == {name, "clarify"}
                if name == "get_plan":
                    value = json.loads(messages[-1]["content"])
                    assert value["data"]["forecast"]["predicted_quantity"] == 27
                    assert value["data"]["mode"] == "historical_demo"
                return dict(
                    tool_calls=[
                        dict(id=name, type="function", function=dict(name=name, arguments="{}"))
                    ]
                )
            return dict(content="历史演示预计七日27件；不能直接用于当前采购。")

    async def call(name, args, invocation):
        calls.append(name)
        assert args == {}
        if name == "get_forecast":
            return dict(
                ok=available,
                data=dict(
                    status="READY" if available else "UNAVAILABLE",
                    mode="historical_demo",
                    forecast=dict(predicted_quantity=27),
                ),
                references=[reference] if available else [],
                error=None if available else "history_required",
            )
        return dict(ok=True, data={}, references=[])

    async def context():
        return "预测须由get_forecast取证，历史演示不能直接用于当前采购。"

    runtime = Runtime(
        Model(),
        InMemorySaver(),
        [
            dict(
                type="function",
                function=dict(
                    name=n,
                    parameters=dict(type="object", properties={}, additionalProperties=False),
                ),
            )
            for n in required
        ],
        call,
        context,
        required_tools=required,
        required_read_tools=required,
    )
    result = await runtime.execute(
        "v6-" + str(available), [dict(role="user", content="预测并检查补货计划")]
    )
    assert calls == (required if available else required[:2])
    if available:
        assert reference in result["references"]
        assert result["completed_tools"] == required
    else:
        assert result["evidence_unavailable"] is True
        assert result["references"] == []
