import asyncio

import pytest


@pytest.mark.asyncio
async def test_shared_budget_bounds_parallel_experts_and_marks_partial():
    from shopsteward_agent.cases import BoundedCaseRunner, CallBudget, SubtaskSpec
    from shopsteward_agent.context import ModelProfile

    class Model:
        active = 0
        maximum = 0
        calls = 0

        async def complete(self, messages, tools, **kwargs):
            self.active += 1
            self.calls += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return {
                "content": '{"claims": [], "missing": [], "followup_requests": []}',
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }

    model = Model()
    budget = CallBudget(max_model_calls=2, max_tool_calls=3)
    specs = [
        SubtaskSpec(
            case_id="c",
            revision_id="1",
            run_id="root",
            subtask_id=role,
            role=role,
            question="check",
            allowed_scope={"store_id": "store", "sku_id": "sku"},
        )
        for role in ("evidence", "impact", "options")
    ]
    runner = BoundedCaseRunner(
        model=model, profile=ModelProfile(model_id="test"), tools=[], call_tool=None, budget=budget
    )
    result = await runner.run(specs)
    assert model.calls == 2 and model.maximum <= 2
    assert sum(item["status"] == "complete" for item in result["subtasks"]) == 2
    assert result["status"] == "partial"
    assert result["budget"]["model_calls"] == 2
    assert result["usage"]["total_tokens"] == 30


@pytest.mark.asyncio
async def test_experts_cannot_access_write_tools_or_invent_support():
    from shopsteward_agent.cases import BoundedCaseRunner, CallBudget, SubtaskSpec
    from shopsteward_agent.context import ModelProfile

    class Model:
        async def complete(self, messages, tools, **kwargs):
            assert "memory_edit" not in str(tools)
            return {
                "content": '{"claims": [{"statement":"claim", "support":["invented"]}], "missing": []}'
            }

    specs = [
        SubtaskSpec(
            case_id="c",
            revision_id="1",
            run_id="root",
            subtask_id="e",
            role="evidence",
            question="check",
            allowed_scope={"store_id": "s"},
        )
    ]
    result = await BoundedCaseRunner(
        model=Model(),
        profile=ModelProfile(model_id="test"),
        tools=[
            {
                "type": "function",
                "function": {"name": "memory_edit", "parameters": {"type": "object"}},
            }
        ],
        call_tool=None,
        budget=CallBudget(),
    ).run(specs)
    assert result["subtasks"][0]["status"] == "failed"
    assert "unsupported_claim" in result["subtasks"][0]["missing"]
    # The rejected answer and the reference nobody supplied are kept for diagnosis.
    rejected = result["subtasks"][0]["rejected"]
    assert rejected["unsupplied"] == ["invented"] and '"statement":"claim"' in rejected["answer"]


@pytest.mark.asyncio
async def test_budget_failed_unknown_attempt_stays_reserved_on_restore():
    from shopsteward_agent import RuntimeFailure
    from shopsteward_agent.cases import CallBudget

    budget = CallBudget(max_model_calls=1)
    await budget.reserve("lost-request", "model")
    await budget.settle("lost-request", None, "failed")
    restored = CallBudget.from_snapshot(budget.snapshot())
    with pytest.raises(RuntimeFailure, match="model_budget"):
        await restored.reserve("retry", "model")
    assert restored.snapshot()["usage"] is None
