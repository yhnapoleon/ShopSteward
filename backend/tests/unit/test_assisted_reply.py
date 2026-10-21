"""Reading a pasted supplier reply: what the rules find, and what a model may claim."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

TODAY = date(2026, 10, 12)
ORDER = {"quantity": 40, "unit_price_minor": 1000, "total_minor": 40000, "currency": "CNY"}


def test_the_order_message_states_what_was_approved_in_both_languages():
    from datetime import UTC, datetime

    from app.execution.assisted import order_message

    action = SimpleNamespace(
        id="1a2b3c4d-0000-4000-8000-000000000000",
        purchase_snapshot={
            "sku_id": "sku_001",
            "supplier_id": "supplier_a",
            "quantity": 40,
            "unit_price_minor": 1050,
            "total_minor": 42000,
            "currency": "CNY",
            "expected_arrival_at": "2026-10-15T08:00:00+00:00",
        },
    )
    message = order_message(action, "矿泉水 550ml", datetime(2026, 10, 12, tzinfo=UTC))
    assert message["reference"] == "PO-1A2B3C4D"
    assert message["requested_delivery_date"] == "2026-10-15"
    for part in ("PO-1A2B3C4D", "矿泉水 550ml", "40 件", "10.50 元/件", "420.00 元", "10月15日"):
        assert part in message["text"]["zh"]
    for part in ("PO-1A2B3C4D", "40 units", "CNY 10.50", "CNY 420.00", "15/10/2026"):
        assert part in message["text"]["en"]
    # The supplier reads a name and a local date; the SKU id stays a structured field.
    assert message["sku_id"] == "sku_001"
    assert all(
        "sku_001" not in text and "2026-10-15" not in text for text in message["text"].values()
    )
    # 20:00 UTC is the next morning for the owner: the wanted-by day is the local one.
    action.purchase_snapshot["expected_arrival_at"] = "2026-10-15T20:00:00+00:00"
    late = order_message(action, "矿泉水 550ml", datetime(2026, 10, 12, tzinfo=UTC))
    assert late["requested_delivery_date"] == "2026-10-16"


def test_a_supplier_date_is_a_local_day_at_the_planned_local_time():
    from datetime import UTC, datetime

    from app.execution.assisted import supplier_arrival

    action = SimpleNamespace(purchase_snapshot={"expected_arrival_at": "2026-10-15T20:00:00+00:00"})
    arrival = supplier_arrival(action, date(2026, 10, 17))
    assert arrival.astimezone(UTC) == datetime(2026, 10, 16, 20, tzinfo=UTC)
    assert supplier_arrival(action, None) is None


def test_rules_read_a_plain_reply_and_leave_mixed_wording_to_a_person():
    from app.execution.assisted import differences, gated, read_by_rules

    text = "收到，确认40件，单价10.00元/件，合计400元，10月15日送到，订单号 SO-7788"
    reading = gated(read_by_rules(text, TODAY), text)
    assert reading["decision"] == "accepted"
    assert (reading["quantity"], reading["unit_price_minor"], reading["total_minor"]) == (
        40,
        1000,
        40000,
    )
    assert reading["delivery_date"] == date(2026, 10, 15)
    assert reading["supplier_order_ref"] == "SO-7788"
    assert reading["quotes"]["quantity"] == "40件" and differences(reading, ORDER) == []

    fewer = gated(read_by_rules("可以，但只有30件，12块一件", TODAY), "可以，但只有30件，12块一件")
    assert differences(fewer, ORDER) == [
        {"field": "quantity", "ordered": 40, "replied": 30},
        {"field": "unit_price_minor", "ordered": 1000, "replied": 1200},
    ]
    declined = "Sorry, this item is out of stock."
    assert gated(read_by_rules(declined, TODAY), declined)["decision"] == "rejected"
    for unsure in ("抱歉回复晚了，确认40件", "稍等，我问一下仓库"):
        assert gated(read_by_rules(unsure, TODAY), unsure)["decision"] == "unclear"
    # A date without a year is taken in the business year, or the next one once it has passed.
    assert read_by_rules("1月5日送到", TODAY)["delivery_date"] == date(2027, 1, 5)
    # The order writes DD/MM/YYYY; a reply may echo it, with or without the year.
    assert read_by_rules("Confirmed, delivery 21/10/2026", TODAY)["delivery_date"] == date(
        2026, 10, 21
    )
    assert read_by_rules("OK, arriving 21/10", TODAY)["delivery_date"] == date(2026, 10, 21)
    assert read_by_rules("OK, 5/1", TODAY)["delivery_date"] == date(2027, 1, 5)
    assert read_by_rules("2026/10/21 送到", TODAY)["delivery_date"] == date(2026, 10, 21)
    assert "delivery_date" not in read_by_rules("40/40 units, 12/25 boxes", TODAY)


class Model:
    def __init__(self, answer):
        self.answer, self.seen = answer, None

    async def complete(self, messages, tools):
        self.seen = messages
        if isinstance(self.answer, Exception):
            raise self.answer
        return {"content": "```json\n" + json.dumps(self.answer, ensure_ascii=False) + "\n```"}


@pytest.mark.asyncio
async def test_a_model_reading_keeps_only_what_it_can_quote_from_the_reply():
    from app.execution.assisted import read_reply

    text = "好嘞老板，四十件没问题，周四给你送过去"
    model = Model(
        {
            "decision": "accepted",
            "quantity": 40,
            "unit_price_minor": 1000,
            "delivery_date": "2026-10-15",
            "quotes": {
                "decision": "没问题",
                "quantity": "四十件",
                # The reply never states a price: this excerpt is not in it.
                "unit_price_minor": "单价10元",
                "delivery_date": "周四给你送过去",
            },
        }
    )
    reading, read_by = await read_reply(text, {**ORDER, "text": {"zh": "..."}}, TODAY, model=model)
    assert read_by == "model" and reading["decision"] == "accepted"
    assert (reading["quantity"], reading["delivery_date"]) == (40, date(2026, 10, 15))
    assert reading["unit_price_minor"] is None and "unit_price_minor" not in reading["quotes"]
    sent = json.loads(model.seen[1]["content"])
    assert sent["business_date"] == "2026-10-12" and "text" not in sent["order"]

    # An acceptance the model cannot quote is not an acceptance.
    unquoted = Model({"decision": "accepted", "quotes": {"decision": "confirmed"}})
    assert (await read_reply(text, ORDER, TODAY, model=unquoted))[0]["decision"] == "unclear"
    # Null stands for "not stated", also in place of an excerpt; the stated fields are kept.
    nulls = Model(
        {
            "decision": "accepted",
            "quantity": 40,
            "unit_price_minor": None,
            "delivery_date": "2026-10-15",
            "supplier_order_ref": "",
            "quotes": {
                "decision": "没问题",
                "quantity": "四十件",
                "unit_price_minor": None,
                "delivery_date": "周四给你送过去",
                "supplier_order_ref": None,
            },
        }
    )
    reading, read_by = await read_reply(text, ORDER, TODAY, model=nulls)
    assert (read_by, reading["decision"], reading["quantity"]) == ("model", "accepted", 40)
    assert reading["delivery_date"] == date(2026, 10, 15) and reading["unit_price_minor"] is None
    # A model that fails or answers with something else leaves the rules reading.
    plain = "确认40件"
    for broken in (Model(RuntimeError("down")), Model({"decision": "maybe"})):
        reading, read_by = await read_reply(plain, ORDER, TODAY, model=broken)
        assert (read_by, reading["decision"], reading["quantity"]) == ("rules", "accepted", 40)


def test_an_order_sent_by_hand_is_late_only_after_its_delivery_day():
    from datetime import UTC, datetime

    from app.execution.assisted import past_due

    due = datetime(2026, 10, 22, 2, 0, tzinfo=UTC)  # 10:00 on 22/10 in Shanghai
    by_hand, simulated = SimpleNamespace(channel="assisted"), SimpleNamespace(channel="simulator")
    later_that_day = datetime(2026, 10, 22, 13, 0, tzinfo=UTC)  # 21:00 on 22/10
    assert not past_due(by_hand, due, later_that_day)
    assert past_due(by_hand, due, datetime(2026, 10, 22, 16, 0, tzinfo=UTC))  # 00:00 on 23/10
    # The simulator delivers at its ETA, so its orders keep the exact time.
    assert past_due(simulated, due, later_that_day)
