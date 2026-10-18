import json

import pytest
from pydantic import ValidationError


def decision(name="evaluate_plan", **overrides):
    from shopsteward_agent.task_policy.contracts import Decision

    arguments = {"plan_id": "plan-current", "max_purchase_qty": 20, **overrides}
    return Decision.model_validate({"name": name, "arguments": arguments})


@pytest.mark.parametrize("quantity", [True, False, -1, 20.5, 20.0, "20", 1000001])
def test_quantity_is_not_coerced_or_clamped(quantity):
    with pytest.raises(ValidationError):
        decision(max_purchase_qty=quantity)


@pytest.mark.parametrize("quantity", [0, 20, None, 1000000])
def test_zero_null_and_integer_limits_are_preserved(quantity):
    result = decision(max_purchase_qty=quantity)
    assert result.arguments["max_purchase_qty"] == quantity
    assert type(result.arguments["max_purchase_qty"]) is type(quantity)


def test_omitted_cap_is_not_an_explicit_null():
    from shopsteward_agent.task_policy.contracts import Decision

    with pytest.raises(ValidationError):
        Decision.model_validate({"name": "evaluate_plan", "arguments": {"plan_id": "p"}})


@pytest.mark.parametrize("version", [True, 0, -1, 1.5, "2"])
def test_revision_version_must_be_a_positive_strict_integer(version):
    with pytest.raises(ValidationError):
        decision("revise_plan", expected_mission_version=version)


def test_revision_cannot_omit_version_or_accept_a_model_supplied_source():
    with pytest.raises(ValidationError):
        decision("revise_plan")
    with pytest.raises(ValidationError):
        decision("revise_plan", expected_mission_version=2, source_message_id="invented")
    assert decision("revise_plan", expected_mission_version=2).arguments == {
        "plan_id": "plan-current",
        "max_purchase_qty": 20,
        "expected_mission_version": 2,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "purchase", "arguments": {}},
        {"name": "clarify", "arguments": {"question": " "}},
        {"name": "handoff", "arguments": {"reason": "too_hard"}},
        {"name": "no_action", "arguments": {"reason": "cancel_mission"}},
        {"name": "evaluate_plan", "arguments": {"plan_id": " ", "max_purchase_qty": 20}},
    ],
)
def test_unknown_actions_and_invalid_control_arguments_are_rejected(payload):
    from shopsteward_agent.task_policy.contracts import Decision

    with pytest.raises(ValidationError):
        Decision.model_validate(payload)


def test_single_call_parser_accepts_json_key_order_but_rejects_multiple_calls():
    from shopsteward_agent.task_policy.contracts import parse_decision

    call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "evaluate_plan", "arguments": '{"max_purchase_qty":20,"plan_id":"p"}'},
    }
    result = parse_decision({"content": "", "tool_calls": [call]})
    assert result.arguments == {"plan_id": "p", "max_purchase_qty": 20}
    call["function"]["arguments"] = {"plan_id": "p", "max_purchase_qty": 20}
    assert parse_decision({"tool_calls": [call]}) == result
    for calls in ([], [call, call]):
        with pytest.raises(ValueError, match="exactly one"):
            parse_decision({"tool_calls": calls})
    call["function"]["arguments"] = "{invalid"
    with pytest.raises(ValueError):
        parse_decision({"tool_calls": [call]})


def test_exported_tools_require_cap_and_exclude_source_message_id():
    from shopsteward_agent.task_policy.contracts import decision_tool_schemas

    tools = {
        item["function"]["name"]: item["function"]["parameters"] for item in decision_tool_schemas()
    }
    assert set(tools) == {"evaluate_plan", "revise_plan", "clarify", "handoff", "no_action"}
    assert "max_purchase_qty" in tools["evaluate_plan"]["required"]
    assert "expected_mission_version" in tools["revise_plan"]["required"]
    assert "source_message_id" not in json.dumps(tools)


def test_policy_context_rejects_oracle_fields():
    from shopsteward_agent.task_policy.contracts import PolicyContext, decision_tool_schemas

    values = {
        "messages": [{"role": "user", "content": "如果上限20件呢？"}],
        "mission_id": "m",
        "plan_id": "p",
        "mission_version": 1,
        "quantity_unit": "件",
        "quantity_cap": None,
        "tool_schemas": decision_tool_schemas(),
        "context_version": "v0",
    }
    assert PolicyContext.model_validate(values).mission_version == 1
    with pytest.raises(ValidationError):
        PolicyContext.model_validate({**values, "expected_action": "evaluate_plan"})


@pytest.mark.asyncio
async def test_selected_prompt_and_completed_reply_reach_model_unchanged():
    from shopsteward_agent.task_policy.contracts import PolicyContext, decision_tool_schemas
    from shopsteward_agent.task_policy.policy import RestrictedPolicy, prompt_for_version

    class Model:
        async def complete(self, messages, tools, tool_choice):
            self.received = (messages, tools, tool_choice)
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "revise_plan",
                            "arguments": {
                                "plan_id": "p",
                                "max_purchase_qty": 23,
                                "expected_mission_version": 2,
                            },
                        },
                    }
                ]
            }

    context = PolicyContext(
        messages=[
            {"role": "user", "content": "Please change the purchase cap."},
            {"role": "assistant", "content": "What quantity cap would you like?"},
            {"role": "user", "content": "Change the current cap to 23 units."},
        ],
        mission_id="m",
        plan_id="p",
        mission_version=2,
        quantity_unit="件",
        quantity_cap=20,
        tool_schemas=decision_tool_schemas(),
        context_version="test",
    )
    model = Model()
    result = await RestrictedPolicy(model, prompt_version="v2").decide(context)
    messages, tools, choice = model.received
    assert messages[0]["content"].startswith(prompt_for_version("v2"))
    assert messages[1:] == context.messages
    assert tools == context.tool_schemas and choice == "required"
    assert result.decision.arguments["max_purchase_qty"] == 23
    assert result.raw_response["tool_calls"][0]["function"]["arguments"]["max_purchase_qty"] == 23


def test_prompt_versions_reject_unknown_and_keep_default():
    from shopsteward_agent.task_policy.policy import SYSTEM_PROMPT, prompt_for_version

    assert prompt_for_version("v1") == SYSTEM_PROMPT
    assert prompt_for_version("v2") != SYSTEM_PROMPT
    with pytest.raises(ValueError, match="unknown prompt version"):
        prompt_for_version("unknown")
