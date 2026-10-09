"""One decision per response; business execution remains in the backend."""

import json
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ActionName = Literal["evaluate_plan", "revise_plan", "clarify", "handoff", "no_action"]
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
Quantity = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
Version = Annotated[int, Field(strict=True, ge=1)]
ShortText = Annotated[str, Field(min_length=1, max_length=300, pattern=r"\S")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvaluationArguments(Contract):
    plan_id: Identifier
    # Required even when null: missing information is not an instruction to remove a cap.
    max_purchase_qty: Quantity | None


class RevisionArguments(EvaluationArguments):
    expected_mission_version: Version


class ClarificationArguments(Contract):
    question: ShortText


class HandoffArguments(Contract):
    reason: Literal["unsupported_request", "insufficient_context", "permission_scope"]


class NoActionArguments(Contract):
    reason: Literal["withdraw_current_request"]


ARGUMENT_MODELS = {
    "evaluate_plan": EvaluationArguments,
    "revise_plan": RevisionArguments,
    "clarify": ClarificationArguments,
    "handoff": HandoffArguments,
    "no_action": NoActionArguments,
}

DESCRIPTIONS = {
    "evaluate_plan": "只读试算本次采购数量上限；不修改正式方案。null表示无额外数量上限。",
    "revise_plan": "按用户明确要求修订本次上限，生成待确认方案；不执行采购。null表示取消额外上限。",
    "clarify": "只询问影响当前动作的必要缺项，不猜数量、单位或指代。",
    "handoff": "请求超出支持范围、上下文不足或权限不足时转交通用路径。",
    "no_action": "用户撤回当前请求时结束本请求；不取消整个任务或回滚既有修改。",
}


class Decision(Contract):
    name: ActionName
    arguments: dict[str, Any]

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        self.arguments = ARGUMENT_MODELS[self.name].model_validate(self.arguments).model_dump()
        return self


class PolicyContext(Contract):
    messages: Annotated[list[dict[str, Any]], Field(min_length=1)]
    mission_id: Identifier
    plan_id: Identifier | None
    mission_version: Version
    quantity_unit: Literal["件"]
    quantity_cap: Quantity | None
    tool_schemas: Annotated[list[dict[str, Any]], Field(min_length=1)]
    context_version: Identifier


class DecisionRecord(Contract):
    decision: Decision | None
    raw_response: dict[str, Any]
    parse_error: str | None
    usage: dict[str, Any] | None
    latency_ms: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def check_parse_result(self) -> Self:
        if (self.decision is None) != bool(self.parse_error):
            raise ValueError("a missing decision requires a parse_error; valid decisions have none")
        return self


def decision_tool_schemas() -> list[dict]:
    """Export model-visible arguments without backend provenance fields."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in ARGUMENT_MODELS.items()
    ]


def parse_decision(response: dict) -> Decision:
    """Parse the normalized OpenAIModel envelope, without repair or inference."""
    calls = response.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1:
        raise ValueError("response must contain exactly one tool call")
    call = calls[0]
    if not isinstance(call, dict) or call.get("type") != "function":
        raise ValueError("tool call must be a function")
    function = call.get("function")
    if not isinstance(function, dict):
        raise ValueError("tool call requires a function object")
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    return Decision.model_validate({"name": function.get("name"), "arguments": arguments})
