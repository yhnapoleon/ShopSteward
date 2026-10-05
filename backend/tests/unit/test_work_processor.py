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
from app.work_items.processor_tools import ControlArgs, ForecastArgs, RevisionArgs, exact_period


def message(content, created_at=None):
    return SimpleNamespace(
        content=content, created_at=created_at or datetime(2026, 10, 5, tzinfo=UTC)
    )


@pytest.mark.parametrize(
    "content",
    ["只比较20和40件", "如果改成最多20件呢", "不要修改方案", "just compare; don't change it"],
)
def test_read_only_or_negative_request_cannot_mutate(content):
    with pytest.raises(AppError):
        require_explicit_revision(content)


def test_explicit_revision_and_ambiguous_stop():
    require_explicit_revision("把当前方案修改成最多20件")
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
    assert "不适用" in result["result"].content
    assert result["result"].references[0].id == "s"
    assert "mission_request" not in result


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
