import pytest

from app.agent_bridge.presentation import (
    explicit_memory_intent,
    memory_write_denied,
    money_facts,
    unsupported_amounts,
)


@pytest.mark.parametrize("content", [
    "请保存这个偏好，不要修改当前方案",
    "请保存这个偏好，不需要修改当前方案",
    "Please save this preference, do not update the plan",
])
def test_memory_save_authorization_is_independent_of_plan_change_prohibition(content):
    assert not memory_write_denied(content)
    assert explicit_memory_intent(content)


@pytest.mark.parametrize("content", [
    "请保存这个偏好，不需要保存这个偏好",
    "请保存这个偏好，不用记下",
    "请保存这个偏好，无需更新我的偏好",
    "请保存这个偏好，别再修改我的偏好",
    "Please save this preference, never update my preference",
    "只试算，不要保存",
])
def test_memory_save_still_honors_explicit_memory_prohibition(content):
    assert memory_write_denied(content)
    assert not explicit_memory_intent(content)


def test_money_conversion_uses_integer_minor_units_and_rejects_invented_yuan():
    facts = money_facts({"cash_minor": 100000, "purchase": {"total_minor": 40000}})
    assert facts == [
        {"field": "cash_minor", "minor": 100000, "yuan": "1000.00"},
        {"field": "purchase.total_minor", "minor": 40000, "yuan": "400.00"},
    ]
    assert unsupported_amounts("可用现金10,000元（100000分）", {100000, 40000}) == ["10,000元"]
    assert unsupported_amounts("可用现金1,000元，支出400.00元", {100000, 40000}) == []


def test_read_questions_and_one_off_constraints_do_not_authorize_memory_mutation():
    assert not explicit_memory_intent("本次采购改成最多20件")
    assert not explicit_memory_intent("What did you save?")
    assert not explicit_memory_intent("不要删除我的偏好")
    assert not explicit_memory_intent("请不要记住这个偏好")
    assert not explicit_memory_intent("请不要更新这个偏好")
    assert not explicit_memory_intent("Please do not update my preference")
    assert not explicit_memory_intent("我以前让你记住了什么？")
    assert not explicit_memory_intent("我有什么已保存的通用回答偏好？请按偏好解释当前方案。")
    assert not explicit_memory_intent("我的补货任务流程是什么？请按已保存的流程解释当前方案。")
    assert not explicit_memory_intent("请列出我保存的偏好")
    assert not explicit_memory_intent("Can you show what you remember?")
    assert explicit_memory_intent("请长期记住我的通用偏好：先结论")
    assert explicit_memory_intent("纠正刚才保存的偏好：改成先风险")
