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
    # The interface's own forms are checked the same way.
    assert unsupported_amounts("Cash CNY 1,000, spend CNY 400.00.", {100000, 40000}) == []
    assert unsupported_amounts("现金¥1,000，合计 ¥450.00", {100000, 40000}) == ["¥450.00"]


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


def test_unsupported_amount_removes_its_sentence_and_keeps_the_rest():
    from app.agent_bridge.presentation import without_unsupported_amounts

    allowed = {100000, 40000}
    content = "| 数量 | 支出 |\n| 40件 | 400.00元 |\n| 80件 | 900元 |\n建议买40件；现金余600元。"
    kept = without_unsupported_amounts(content, allowed)
    assert "| 40件 | 400.00元 |" in kept and "900元" not in kept
    assert "建议买40件；" in kept and "600元" not in kept
    assert kept.endswith("金额以业务记录为准。）")
    english = "Buy 40 units. That costs 450元. Cash stays safe."
    english = without_unsupported_amounts(english, allowed)
    assert english.startswith("Buy 40 units. Cash stays safe.")
    assert "not found in the business records" in english
    assert without_unsupported_amounts("可用现金1,000元。", allowed) == "可用现金1,000元。"
    assert without_unsupported_amounts("现金余600元。", allowed) == ""


def test_each_timestamp_gets_its_business_time_neighbour():
    from app.agent_bridge.presentation import local_times

    value = local_times(
        {
            "expected_arrival_at": "2026-10-22T16:30:00Z",
            "delivery_date": "2026-10-23",
            "items": [
                {"created_at": "2026-10-21T02:59:20.123456+00:00", "note": "2026-10-21 noon"}
            ],
            "quantity": 20,
        }
    )
    # 16:30 UTC on Thursday is 00:30 on Friday in Shanghai.
    assert value["expected_arrival_at_local"] == "Fri 23/10 00:30"
    assert value["delivery_date_local"] == "Fri 23/10"
    assert value["items"][0]["created_at_local"] == "Wed 21/10 10:59"
    # Counterexamples: text that only contains a date, numbers and invalid dates stay as they are.
    assert "note_local" not in value["items"][0] and "quantity_local" not in value
    assert "x_local" not in local_times({"x": "2026-13-40"})


def test_remember_with_a_negated_preference_is_an_explicit_memory_command():
    assert explicit_memory_intent("Remember: I don’t take deliveries on weekends.")
    assert not explicit_memory_intent("Just place the order")
