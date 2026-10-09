import pytest
from test_scorers import example


@pytest.mark.asyncio
async def test_policy_excludes_oracle_and_preserves_invalid_response():
    from shopsteward_agent.task_policy.contracts import PolicyContext
    from shopsteward_agent.task_policy.policy import RestrictedPolicy

    calls = []

    class Model:
        async def complete(self, messages, tools, **kwargs):
            calls.append(messages)
            return {
                "content": "I cannot choose",
                "tool_calls": [],
                "usage": {"input_tokens": 5, "output_tokens": 3},
            }

    context = PolicyContext.model_validate(example()[1]["context"])
    record = await RestrictedPolicy(Model()).decide(context)
    assert len(calls) == 1
    assert "expected_steps" not in str(calls[0])
    assert record.decision is None
    assert record.raw_response["content"] == "I cannot choose"
    assert record.usage["output_tokens"] == 3


@pytest.mark.asyncio
async def test_wrong_clarification_is_not_given_the_scripted_answer():
    from shopsteward_agent.task_policy.contracts import PolicyContext

    from shopsteward_pt.eval.policies import RulePolicy
    from shopsteward_pt.eval.records import EpisodeSpec
    from shopsteward_pt.eval.runner import run_episode

    spec, trace = example()
    spec.update(
        task_type="PT-04",
        user_message="把本次采购上限调低一些。",
        followup_user_message="把上限改成20件。",
    )
    spec["expected_steps"].insert(
        0,
        {"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"},
    )
    context = PolicyContext.model_validate(trace["context"])
    context.messages = [{"role": "user", "content": spec["user_message"]}]
    result = await run_episode(
        EpisodeSpec.model_validate(spec),
        "B0",
        mode="decision",
        config={},
        frozen_context=context.model_dump(),
        policy=RulePolicy(),
        reviews={},
    )
    assert len(result.steps) == 1
    assert result.steps[0].decision.name == "clarify"
    assert len(result.context.messages) == 1


@pytest.mark.asyncio
async def test_rule_baseline_selects_readonly_for_negated_revision():
    from shopsteward_agent.task_policy.contracts import PolicyContext

    from shopsteward_pt.eval.policies import RulePolicy

    context = PolicyContext.model_validate(example()[1]["context"])
    context.messages = [{"role": "user", "content": "先别改，只试算本次上限20件。"}]
    result = await RulePolicy().decide(context)
    assert result.decision.name == "evaluate_plan"
    assert result.decision.arguments == {"plan_id": "plan-1", "max_purchase_qty": 20}
