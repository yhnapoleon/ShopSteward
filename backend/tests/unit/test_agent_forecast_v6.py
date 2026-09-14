from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent_bridge.evidence_policy import evidence_policy
from app.agent_bridge.forecast_evidence import forecast_answer_guard
from app.agent_bridge.tools import Empty, execute_tool, tool_schemas


def test_forecast_evidence_can_be_saved_as_scheduler_result():
    from app.agent_bridge.jobs import scheduler_references
    from app.api.schemas import JobResult

    references = answer()["references"]
    result = JobResult.model_validate(
        dict(summary="Forecast explained", references=scheduler_references(references))
    )
    assert result.references[0].type == "artifact"
    assert references[0]["type"] == "forecast"


def current(mode="observed"):
    return dict(
        status="READY",
        store_id="s",
        sku_id="k",
        mode=mode,
        forecast=dict(forecast_id="f", model_version="v6"),
    )


def answer(mode="observed"):
    return dict(
        content="预计七天销售 12 件。",
        references=[
            dict(type="forecast", id="f", version="v6", store_id="s", sku_id="k", mode=mode)
        ],
    )


def test_forecast_and_replenishment_require_ordered_evidence():
    for content in ["请预测下周销量", "根据预测制定补货计划", "现在应该补货吗", "看一下模型推演"]:
        policy = evidence_policy(content, documents_enabled=False, forecasts_enabled=True)
        assert policy["required_tools"][:2] == ["get_dashboard", "get_forecast"]
    assert evidence_policy("根据预测制定补货计划", documents_enabled=False, forecasts_enabled=True)[
        "required_tools"
    ] == ["get_dashboard", "get_forecast", "get_plan"]


@pytest.mark.parametrize(
    "content", ["什么是销量预测", "解释预测模型的原理", "不用预测，只查当前库存"]
)
def test_general_or_negated_forecast_does_not_force_model_read(content):
    assert (
        "get_forecast"
        not in evidence_policy(content, documents_enabled=False, forecasts_enabled=True)[
            "required_tools"
        ]
    )


def test_explicit_prediction_when_disabled_returns_unavailability_via_tool():
    assert (
        "get_forecast"
        in evidence_policy("下周预计卖多少", documents_enabled=False)["required_tools"]
    )


def test_forecast_guard_requires_same_current_scope_and_version():
    assert forecast_answer_guard(answer(), required=True, current=current()) == answer()
    for modified in [
        dict(status="STALE"),
        dict(sku_id="other"),
        dict(forecast=dict(forecast_id="new", model_version="v6")),
    ]:
        guarded = forecast_answer_guard(answer(), required=True, current=current() | modified)
        assert not guarded["references"]
        assert "12" not in guarded["content"]
        assert "FORECAST_EVIDENCE_CHANGED" in guarded["validation_warnings"]
    guarded = forecast_answer_guard(
        dict(content="预计12件", references=[]), required=True, current=current()
    )
    assert "FORECAST_EVIDENCE_MISSING" in guarded["validation_warnings"]


def test_demo_guard_labels_historical_evidence_and_preserves_clarification():
    guarded = forecast_answer_guard(
        answer("historical_demo"), required=True, current=current("historical_demo")
    )
    assert "模型推演，仅供参考" in guarded["content"]
    assert "历史演示" not in guarded["content"]
    paused = dict(status="WAITING_INPUT", content="需要哪些数据？")
    assert forecast_answer_guard(paused, required=True, current=None) == paused


async def test_forecast_tool_is_read_only_mission_scoped_and_no_reference_on_failure(monkeypatch):
    read = AsyncMock(
        return_value=current("historical_demo")
        | {
            "history": [{"date": "2016-03-27", "sold_quantity": 2, "complete": True}],
            "model": {"supported_series": [{"series_id": "x"}] * 300, "model_version": "v6"},
        }
    )
    monkeypatch.setattr("app.forecast_v6.repository.read_current", read)
    session, settings = object(), object()
    mission, store = SimpleNamespace(sku_id="k"), SimpleNamespace(id="s")
    result = await execute_tool(
        session, settings, None, None, None, mission, store, "get_forecast", Empty(), "call"
    )
    read.assert_awaited_once_with(session, "s", "k", settings)
    assert result["ok"] and result["references"] == answer("historical_demo")["references"]
    assert "history" not in result["data"]
    assert "supported_series" not in result["data"]["model"]
    assert result["data"]["input_coverage"]["days"] == 1
    read.return_value = dict(status="UNAVAILABLE", reason="HISTORY_REQUIRED", forecast=None)
    result = await execute_tool(
        session, settings, None, None, None, mission, store, "get_forecast", Empty(), "call2"
    )
    assert result["ok"] is False and result["references"] == []
    assert result["data"]["reason"] == "HISTORY_REQUIRED"


def test_forecast_tool_cannot_accept_llm_scope_or_series():
    schema = next(
        t["function"]["parameters"]
        for t in tool_schemas(SimpleNamespace(roles=["viewer"]))
        if t["function"]["name"] == "get_forecast"
    )
    assert schema["properties"] == {} and schema["additionalProperties"] is False
