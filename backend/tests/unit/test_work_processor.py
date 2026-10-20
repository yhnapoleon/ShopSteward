from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.work_items.authorization import (
    authorize_action,
    grounded_period,
    require_explicit_revision,
)
from app.work_items.processor import (
    Lease,
    delivery,
    internal_service,
    stable_command,
    validate_lease,
)
from app.work_items.processor_tools import (
    ComparisonArgs,
    ControlArgs,
    ForecastArgs,
    RevisionArgs,
    exact_period,
)


def message(content, created_at=None):
    return SimpleNamespace(
        content=content, created_at=created_at or datetime(2026, 10, 5, tzinfo=UTC)
    )


@pytest.mark.parametrize(
    "content",
    [
        "只比较20和40件",
        "如果改成最多20件呢",
        "不要修改方案",
        "just compare; don't change it",
        "先不采购，方案也不要调整",
    ],
)
def test_read_only_or_negative_request_cannot_mutate(content):
    with pytest.raises(AppError):
        require_explicit_revision(content)


def test_explicit_revision_and_ambiguous_stop():
    require_explicit_revision("把当前方案修改成最多20件")
    # Declining to order is not declining the revision that was asked for.
    require_explicit_revision("请把方案修改为最多20件，不要下单")
    require_explicit_revision("Change the plan to at most 20 units, but don't order yet")
    args = ControlArgs(
        mission_id="m", operation="pause", expected_mission_version=1, source_quote="停一下"
    )
    with pytest.raises(AppError, match="澄清"):
        authorize_action("control_mission", args, [message("停一下")])
    authorize_action("control_mission", args, [message("暂停备货跟进")])


def test_next_week_cannot_be_replaced_with_forecast_fixture_dates():
    args = ForecastArgs(
        sku_id="sku", requested_start="2016-03-01T00:00:00Z", requested_end="2016-03-08T00:00:00Z"
    )
    with pytest.raises(AppError) as error:
        grounded_period(args, [message("下周够卖吗？")])
    assert error.value.code == "USER_PERIOD_MISMATCH"
    args.requested_start = datetime(2026, 10, 12, tzinfo=UTC)
    args.requested_end = datetime(2026, 10, 19, tzinfo=UTC)
    grounded_period(args, [message("下周够卖吗？")])
    assert not exact_period(
        "2026-10-05T00:00:00Z", "2026-10-12T00:00:00Z", args.requested_start, args.requested_end
    )


def test_stable_receipt_uses_same_input_and_semantic_change_across_reclaims():
    lease = Lease("w", 2, "token", internal_service("s"), "user-message")
    args = RevisionArgs(
        mission_id="m",
        plan_id="old",
        max_purchase_qty=20,
        expected_mission_version=1,
        source_quote="最多20件",
    )
    first = stable_command(lease, "revise_plan", args)
    lease.version = 7
    args.plan_id = "new"
    args.expected_mission_version = 2
    assert stable_command(lease, "revise_plan", args) == first
    lease.input_id = "another-user-message"
    assert stable_command(lease, "revise_plan", args) != first


def test_version_cancel_and_expiry_fence():
    import hashlib

    now = datetime.now(UTC)
    lease = Lease("w", 2, "token", internal_service("s"), "msg")
    row = SimpleNamespace(
        version=2,
        canonical_id=None,
        status="PROCESSING",
        processing_owner="work-processor",
        processing_hash=hashlib.sha256(b"token").hexdigest(),
        processing_expires_at=now + timedelta(seconds=30),
    )
    validate_lease(row, lease, now)
    for field, value in [("version", 3), ("status", "CANCELLED"), ("processing_expires_at", now)]:
        original = getattr(row, field)
        setattr(row, field, value)
        with pytest.raises(AppError):
            validate_lease(row, lease, now)
        setattr(row, field, original)


def test_unusable_forecast_overrides_model_claim_and_preserves_real_reference():
    result = delivery(
        {"content": "下周肯定够卖。"},
        [
            {
                "ok": True,
                "data": {"usable_for_requested_period": False},
                "references": [{"type": "store", "id": "s", "label": "真实来源"}],
            }
        ],
    )
    content = result["result"].content
    assert content.startswith("注意：现有预测不覆盖") and content.endswith("下周肯定够卖。")
    assert result["result"].references[0].id == "s"
    assert "mission_request" not in result


def test_a_later_forecast_read_for_the_right_dates_replaces_the_wrong_one():
    def read(usable):
        return {
            "ok": True,
            "data": {"forecast": {"sku_id": "sku_001"}, "usable_for_requested_period": usable},
        }

    result = delivery({"content": "Stock covers next week."}, [read(False), read(True)])
    assert result["result"].content == "Stock covers next week."
    wrong = delivery({"content": "Stock covers next week."}, [read(True), read(False)])
    assert wrong["result"].content.startswith("Note: the current forecast does not cover")


def test_user_cash_floor_cannot_be_silently_rescaled():
    from app.work_items.authorization import grounded_cash_floor

    grounded_cash_floor(50000, [message("现金至少留500元")])
    with pytest.raises(AppError) as error:
        grounded_cash_floor(500, [message("至少留500元")])
    assert error.value.code == "CASH_FLOOR_SOURCE_MISMATCH"


@pytest.mark.parametrize(
    "content", ["至少留500块钱", "keep at least 500 yuan", "cash floor 500 CNY"]
)
def test_floor_colloquial_and_currency_units(content):
    from app.work_items.authorization import grounded_cash_floor

    grounded_cash_floor(50000, [message(content)], required=True)
    with pytest.raises(AppError):
        grounded_cash_floor(500, [message(content)], required=True)


def test_unspecified_floor_requires_clarification():
    from app.work_items.authorization import grounded_cash_floor

    with pytest.raises(AppError):
        grounded_cash_floor(0, [message("帮我跟进备货")], required=True)


def test_deterministic_quotation_does_not_validate_unused_model_money():
    result = delivery(
        {"content": "饮料12元/件。"},
        [
            {"_tool": "get_work_context", "data": {"cash_minor": 100000}},
            {
                "_tool": "process_quotation",
                "work_result": {
                    "kind": "quotation",
                    "title": "报价结果",
                    "content": "已按原件计算。",
                    "columns": ["单价"],
                    "rows": [["12"]],
                },
            },
        ],
    )
    assert result["status"] == "RESULT_READY"
    assert result["result"].rows == [["12"]]


def comparison(**changes):
    return ComparisonArgs.model_validate(
        {
            "sku_id": "sku",
            "supplier_id": "supplier",
            "expected_state_version": 1,
            "cash_floor_minor": 30000,
            "candidate_quantities": [40, 20, 40],
            "requested_start": "2026-10-05T00:00:00Z",
            "requested_end": "2026-10-12T00:00:00Z",
            **changes,
        }
    )


def test_comparison_always_keeps_the_no_purchase_baseline():
    args = comparison()
    assert args.candidate_quantities == [0, 20, 40]
    assert args.request().candidate_quantities == [0, 20, 40]
    assert comparison(candidate_quantities=[0, 20]).candidate_quantities == [0, 20]
    schema = ComparisonArgs.model_json_schema()["properties"]["candidate_quantities"]
    assert "0件" in schema["description"]


def test_invalid_tool_arguments_name_the_failing_field():
    from pydantic import ValidationError

    from app.work_items.processor import invalid_arguments

    with pytest.raises(ValidationError) as error:
        comparison(cash_floor_minor="300", candidate_quantities=[])
    message = invalid_arguments(error.value)
    assert "cash_floor_minor" in message and "candidate_quantities" in message
    with pytest.raises(ValidationError) as error:
        comparison(remaining_demand=60).request()
    assert "自定义需求必须同时给出需求件数和假设期间" in invalid_arguments(error.value)
    assert "Value error" not in invalid_arguments(error.value)


def proposal(quote):
    from app.work_items.processor_tools import ProposalArgs

    return ProposalArgs.model_validate(
        {**comparison().model_dump(mode="json"), "source_quote": quote, "objective": "跟进"}
    )


@pytest.mark.parametrize(
    "content",
    [
        "帮我盯着可乐，现金至少留300元",
        "以后可乐都帮我看着点",
        "可乐的补货交给你了，长期关注一下",
        "Keep an eye on cola for me and keep at least 300 yuan",
        "Please look after cola restocking from now on",
        "请持续跟进可乐备货",
    ],
)
def test_natural_follow_up_requests_can_be_proposed(content):
    authorize_action("propose_mission", proposal(content), [message(content)])


@pytest.mark.parametrize(
    "content", ["可乐40件够卖吗？", "看着办吧", "What is the cash balance?", "不要盯着可乐了"]
)
def test_one_off_or_declined_requests_cannot_propose_a_mission(content):
    with pytest.raises(AppError):
        authorize_action("propose_mission", proposal(content), [message(content)])


def test_pause_accepts_natural_follow_up_wording():
    args = ControlArgs(
        mission_id="m", operation="pause", expected_mission_version=1, source_quote="暂停盯可乐"
    )
    authorize_action("control_mission", args, [message("暂停盯可乐")])
    authorize_action("control_mission", args, [message("Pause watching cola for now")])


def compared(content):
    return delivery(
        {"content": content},
        [
            {
                "_tool": "compare_quantities",
                "data": {"cash_minor": 100000, "candidates": [{"spend_minor": 40000}]},
                "references": [{"type": "store", "id": "s", "label": "真实来源"}],
            }
        ],
    )


def test_unsupported_amount_drops_only_its_sentence():
    result = compared("买40件花费400元。买40件后现金剩余650元。建议先买40件。")
    assert result["status"] == "RESULT_READY"
    content = result["result"].content
    assert "400元" in content and "建议先买40件" in content
    assert "650元" not in content and "已删去" in content


def test_answer_with_only_unsupported_amounts_is_still_blocked():
    result = compared("现金剩余650元。")
    assert result["status"] == "BLOCKED"


class RewriteModel:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete(self, messages, tools, **kwargs):
        self.calls.append((messages, tools, kwargs))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


async def test_rewrite_names_unsupported_amounts_and_returns_the_rewrite():
    from app.agent_bridge.presentation import rewrite_amounts

    records = [{"tool": "compare_quantities", "data": {"candidates": [{"spend_minor": 40000}]}}]
    model = RewriteModel({"content": "买40件花费400.00元。", "tool_calls": []})
    text = await rewrite_amounts(model, ["tool"], "买40件花费450元。", records, model_timeout=5)
    assert text == "买40件花费400.00元。"
    messages, tools, options = model.calls[0]
    assert "450元" in messages[0]["content"] and "40000" in messages[0]["content"]
    assert messages[1]["content"] == "买40件花费450元。"
    assert tools == ["tool"] and options == {"tool_choice": "none"}
    # Supported text costs no model call; a failed rewrite keeps the original for the check.
    supported = await rewrite_amounts(model, [], "花费400元。", records, model_timeout=5)
    assert supported == "花费400元。"
    assert len(model.calls) == 1
    failing = RewriteModel(RuntimeError("provider down"))
    assert (
        await rewrite_amounts(failing, [], "花费450元。", records, model_timeout=5) == "花费450元。"
    )
