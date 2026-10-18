"""A purchase the owner carries to the supplier: the order message out, the pasted reply back.

The system reaches no supplier here. It writes the approved purchase down as a message
the owner sends through their own channel, and reads the reply they paste into a receipt.
A model may read the reply; code keeps a field only when the excerpt it cites is in the
pasted text, and only a reply that agrees with the order confirms it. Until then the
order waits.
"""

import json
import re
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.hashing import digest
from app.execution.accounting import apply_receipt, close_action
from app.execution.repository import lock_action
from app.execution.schemas import RecordedArrival
from app.missions.models import InboundRow
from app.missions.repository import command, queue_check, timeline
from app.operations.models import LedgerEntry, ProductRow, StockRow
from app.sourcing.provider import configured, provider

FIELDS = ("quantity", "unit_price_minor", "total_minor", "delivery_date", "supplier_order_ref")
INSTRUCTION = (
    "You read a supplier's reply to a purchase order. Return one JSON object {decision, "
    "quantity, unit_price_minor, total_minor, delivery_date, supplier_order_ref, quotes}. "
    "decision is accepted when the supplier agrees to supply the order, rejected when it "
    "declines, unclear otherwise. quantity is in units; money is in fen (1 yuan = 100 fen); "
    "delivery_date is YYYY-MM-DD, resolved against the business date given; "
    "supplier_order_ref is the supplier's own order number. Use null for anything the reply "
    "does not state; never fill a value from the order. quotes maps decision and every "
    "non-null field to the exact excerpt of the reply it was read from."
)


class _Reading(BaseModel):
    model_config = ConfigDict(extra="ignore")
    decision: Literal["accepted", "rejected", "unclear"] = "unclear"
    quantity: int | None = Field(default=None, gt=0)
    unit_price_minor: int | None = Field(default=None, gt=0)
    total_minor: int | None = Field(default=None, gt=0)
    delivery_date: date | None = None
    supplier_order_ref: str | None = Field(default=None, min_length=1, max_length=64)
    quotes: dict[str, str] = Field(default_factory=dict)


def _yuan(minor):
    return f"{minor / 100:.2f}"


def order_message(action, product_name, now):
    """What was approved, as a message a person can send as it is."""
    purchase = action.purchase_snapshot
    reference = "PO-" + action.id.replace("-", "")[:8].upper()
    wanted = datetime.fromisoformat(purchase["expected_arrival_at"]).date().isoformat()
    name = product_name or purchase["sku_id"]
    unit, total = _yuan(purchase["unit_price_minor"]), _yuan(purchase["total_minor"])
    return {
        "reference": reference,
        "supplier_id": purchase["supplier_id"],
        "sku_id": purchase["sku_id"],
        "product_name": name,
        "quantity": purchase["quantity"],
        "unit_price_minor": purchase["unit_price_minor"],
        "total_minor": purchase["total_minor"],
        "currency": purchase["currency"],
        "requested_delivery_date": wanted,
        "text": {
            "zh": f"【订货单 {reference}】\n您好，想向贵司订货：\n"
            f"商品：{name}（货号 {purchase['sku_id']}）\n数量：{purchase['quantity']} 件\n"
            f"单价：{unit} 元/件\n合计：{total} 元\n希望送达：{wanted}\n"
            "请回复确认数量、单价和送达日期，谢谢。",
            "en": f"[Purchase order {reference}]\nHello, we would like to order:\n"
            f"Item: {name} (SKU {purchase['sku_id']})\nQuantity: {purchase['quantity']} units\n"
            f"Unit price: CNY {unit}\nTotal: CNY {total}\nDelivery wanted by: {wanted}\n"
            "Please reply to confirm the quantity, unit price and delivery date. Thank you.",
        },
        "generated_at": now.isoformat(),
    }


async def prepare(session, action, now):
    """Called once, when the purchase is registered as sent: the owner is now the channel."""
    product = await session.get(ProductRow, (action.store_id, action.purchase_snapshot["sku_id"]))
    action.order_message = order_message(action, (product.document or {}).get("name"), now)
    action.next_attempt_at = None


def squash(text):
    return "".join(text.split())


NO = re.compile(
    r"无法|不能|不可以|不行|没货|没有货|无货|缺货|断货|抱歉|不好意思|供不了|接不了|"
    r"cannot|can't|unable|out of stock|sorry",
    re.IGNORECASE,
)
YES = re.compile(
    r"确认|收到|可以|没问题|好的|安排|\bok\b|\bokay\b|confirm|will deliver|\byes\b", re.IGNORECASE
)
AMOUNT = r"(\d+(?:\.\d{1,2})?)"
PATTERNS = {
    "quantity": re.compile(r"(\d+)\s*(?:件|个|pcs|pieces|units)", re.IGNORECASE),
    "unit_price_minor": re.compile(
        rf"(?:单价|unit price)\D{{0,6}}{AMOUNT}|{AMOUNT}\s*(?:元|块)\s*(?:/|每|一)\s*(?:件|个)",
        re.IGNORECASE,
    ),
    "total_minor": re.compile(rf"(?:合计|总计|总价|共计|total)\D{{0,6}}{AMOUNT}", re.IGNORECASE),
    "supplier_order_ref": re.compile(
        r"(?:订单号|单号|order\s*(?:no\.?|number|#))\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,40})",
        re.IGNORECASE,
    ),
}
DATES = (
    re.compile(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})"),
    re.compile(r"()(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?"),
)


def read_by_rules(text, today):
    """The reading a plain, well-formed reply supports without a model."""
    found = {"decision": "unclear", "quotes": {}}
    for name, pattern in PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        value = next(group for group in match.groups() if group)
        if name.endswith("_minor"):
            value = round(float(value) * 100)
        found[name] = int(value) if name == "quantity" else value
        found["quotes"][name] = match.group(0)
    for pattern in DATES:
        match = pattern.search(text)
        if not match:
            continue
        try:
            day = date(int(match.group(1) or today.year), int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        if not match.group(1) and day < today - timedelta(days=30):
            day = day.replace(year=day.year + 1)
        found["delivery_date"], found["quotes"]["delivery_date"] = day, match.group(0)
        break
    refused, agreed = NO.search(text), YES.search(text)
    # Words of both kinds ("sorry for the late reply, confirmed") are left to a person.
    if refused and not agreed:
        found["decision"], found["quotes"]["decision"] = "rejected", refused.group(0)
    elif agreed and not refused:
        found["decision"], found["quotes"]["decision"] = "accepted", agreed.group(0)
    return found


def gated(raw, text):
    """A reading whose every kept field quotes the reply; anything unquoted is dropped."""
    try:
        reading = _Reading.model_validate(raw)
    except ValidationError:
        return None
    body = squash(text)

    def backed(name):
        quote = reading.quotes.get(name, "")
        return bool(squash(quote)) and squash(quote) in body

    kept = {name: getattr(reading, name) if backed(name) else None for name in FIELDS}
    decision = reading.decision if backed("decision") else "unclear"
    return {
        "decision": decision,
        **kept,
        "quotes": {
            name: reading.quotes[name]
            for name in ("decision", *FIELDS)
            if backed(name) and (name != "decision" or decision != "unclear")
        },
    }


def reader(settings):
    """The configured model, or None: reading a reply must also work without one.

    The reply is read where supplier documents are read; without that, by the Agent's model.
    """
    where = provider(settings)
    if not configured(settings):
        where = {
            "base_url": settings.agent_base_url,
            "key_file": settings.agent_api_key_file,
            "model": settings.agent_model,
            "api_mode": settings.agent_api_mode,
        }
    if not where["key_file"] or not where["model"]:
        return None
    from shopsteward_agent import OpenAIModel
    from shopsteward_agent.context import ModelProfile

    profile = ModelProfile(
        profile_id="supplier-reply",
        model_id=where["model"],
        api_mode=where["api_mode"],
        reasoning_effort=settings.agent_reasoning_effort,
        max_input_tokens=settings.agent_max_input_tokens,
        max_output_tokens=settings.agent_max_output_tokens,
        timeout_s=settings.agent_model_timeout_seconds,
    )
    return OpenAIModel(
        base_url=where["base_url"],
        model=profile.model_id,
        profile=profile,
        key_file=where["key_file"],
    )


async def read_reply(text, order, today, model=None):
    """(reading, who read it). A model that fails or cites nothing falls back to the rules."""
    if model is not None:
        try:
            answer = await model.complete(
                [
                    {"role": "system", "content": INSTRUCTION},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "business_date": today.isoformat(),
                                "order": {k: v for k, v in order.items() if k != "text"},
                                "reply": text,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                [],
            )
            content = answer["content"]
            reading = gated(json.loads(content[content.find("{") : content.rfind("}") + 1]), text)
            if reading is not None:
                return reading, "model"
        except Exception:  # noqa: BLE001 - any reader failure leaves the rules reading
            pass
    return gated(read_by_rules(text, today), text) or gated({}, text), "rules"


def differences(reading, order):
    """Where an accepting reply departs from the order; such a reply confirms nothing."""
    return [
        {"field": name, "ordered": order[name], "replied": reading[name]}
        for name in ("quantity", "unit_price_minor", "total_minor")
        if reading[name] is not None and reading[name] != order[name]
    ]


def partly(reading, order, found):
    """An accepting reply that only supplies fewer units, at the ordered price."""
    quantity = reading["quantity"]
    return (
        reading["decision"] == "accepted"
        and quantity is not None
        and 0 < quantity < order["quantity"]
        and all(
            d["field"] == "quantity"
            or (
                d["field"] == "total_minor" and d["replied"] == quantity * order["unit_price_minor"]
            )
            for d in found
        )
    )


def waiting(action):
    return action.channel == "assisted" and action.status == "EXECUTING"


async def record_reply(session, action_id, text, reading, read_by, principal, key):
    """Turn a read reply into a receipt, or leave the order waiting with the reason."""
    store, mission, _, action = await lock_action(session, action_id)
    receipt, replay = await command(
        session, principal, "record_supplier_reply", key, {"action_id": action_id, "text": text}
    )
    if replay:
        return action
    if not waiting(action) or action.manual_review:
        raise AppError(409, "ACTION_NOT_WAITING", "This order is not waiting for a supplier reply")
    now = await session.scalar(select(func.clock_timestamp()))
    order, found = action.order_message, differences(reading, action.order_message)
    outcome = (
        "declined"
        if reading["decision"] == "rejected"
        else "confirmed"
        if reading["decision"] == "accepted" and not found
        else "partial"
        if partly(reading, order, found)
        else "needs_attention"
    )
    day = reading["delivery_date"]
    action.supplier_reply = {
        "text": text,
        "read_by": read_by,
        "outcome": outcome,
        "decision": reading["decision"],
        **{name: reading[name] for name in FIELDS if name != "delivery_date"},
        "delivery_date": day and day.isoformat(),
        "quotes": reading["quotes"],
        "differences": found,
        "recorded_at": now.isoformat(),
        "recorded_by": principal,
    }
    action.updated_at = now
    references = [{"type": "action", "id": action.id}]
    if outcome == "partial":
        await timeline(
            session,
            mission,
            "SUPPLIER_REPLY_PARTIAL",
            f"供应商只确认了 {reading['quantity']}/{order['quantity']} 件。"
            "可以按对方数量成交，或撤回订单；在你决定前，订单保持待确认。",
            actor=principal,
            references=references,
        )
        receipt.response = {"action_id": action.id}
        return action
    if outcome == "needs_attention":
        await timeline(
            session,
            mission,
            "SUPPLIER_REPLY_UNCLEAR",
            "供应商的回复还不能确认这笔订单，订单保持待确认。",
            actor=principal,
            references=references,
        )
        receipt.response = {"action_id": action.id}
        return action
    raw = {
        "action_id": action.id,
        "status": "ACCEPTED" if outcome == "confirmed" else "REJECTED",
        "external_order_id": (reading["supplier_order_ref"] or order["reference"])
        if outcome == "confirmed"
        else None,
        "quantity": order["quantity"] if outcome == "confirmed" else 0,
        "total_minor": order["total_minor"] if outcome == "confirmed" else 0,
        "currency": order["currency"],
        "recorded_at": now.isoformat(),
        "reason": None if outcome == "confirmed" else "Supplier declined in the pasted reply",
    }
    wanted = datetime.fromisoformat(action.purchase_snapshot["expected_arrival_at"])
    # The supplier's own date replaces the planned one; the next check plans around it.
    await apply_receipt(
        session,
        store,
        mission,
        action,
        raw,
        expected_arrival_at=datetime.combine(day, wanted.timetz()) if day else None,
    )
    if mission.status == "ACTIVE":
        await queue_check(session, store, mission, key="supplier-reply-" + action.id)
    receipt.response = {"action_id": action.id}
    return action


async def withdraw(session, action_id, principal, key):
    """Take back an order the supplier has not confirmed; the reserved cash is released."""
    store, mission, _, action = await lock_action(session, action_id)
    receipt, replay = await command(
        session, principal, "withdraw_assisted_order", key, {"action_id": action_id}
    )
    if replay:
        return action
    if not waiting(action) or action.manual_review:
        raise AppError(409, "ACTION_NOT_WAITING", "This order is not waiting for a supplier reply")
    await close_action(session, store, mission, action, "CANCELLED", reason="WITHDRAWN_BY_OWNER")
    if mission.status == "ACTIVE":
        await queue_check(session, store, mission, key="withdrawn-" + action.id)
    receipt.response = {"action_id": action.id}
    return action


async def accept_partial(session, action_id, principal, key):
    """Take the quantity the supplier confirmed: only that is paid for and expected, the rest
    of the reserved cash is released, and an emergency case records what is still missing."""
    store, mission, plan, action = await lock_action(session, action_id)
    receipt, replay = await command(
        session, principal, "accept_partial_supply", key, {"action_id": action_id}
    )
    if replay:
        return action
    reply = action.supplier_reply or {}
    if not waiting(action) or action.manual_review or reply.get("outcome") != "partial":
        raise AppError(
            409,
            "PARTIAL_SUPPLY_NOT_OFFERED",
            "Only a reply that confirms part of a waiting order can be accepted as it is",
        )
    now = await session.scalar(select(func.clock_timestamp()))
    order, quantity = action.order_message, reply["quantity"]
    raw = {
        "action_id": action.id,
        "status": "ACCEPTED",
        "external_order_id": reply["supplier_order_ref"] or order["reference"],
        "quantity": quantity,
        "total_minor": quantity * order["unit_price_minor"],
        "currency": order["currency"],
        "recorded_at": now.isoformat(),
        "reason": None,
    }
    wanted = datetime.fromisoformat(action.purchase_snapshot["expected_arrival_at"])
    day = reply["delivery_date"] and date.fromisoformat(reply["delivery_date"])
    if not await apply_receipt(
        session,
        store,
        mission,
        action,
        raw,
        expected_arrival_at=datetime.combine(day, wanted.timetz()) if day else None,
        partial=True,
    ):
        receipt.response = {"action_id": action.id}
        return action
    missing = order["quantity"] - quantity
    await timeline(
        session,
        mission,
        "PURCHASE_PARTIALLY_ACCEPTED",
        f"按供应商确认的 {quantity} 件成交，比订单少 {missing} 件；多预留的资金已释放。",
        actor=principal,
        references=[{"type": "action", "id": action.id}],
    )
    intent = plan.document.get("recovery_intent")
    if intent:
        from app.operations_cases.models import CaseRow
        from app.operations_cases.repository import event as case_event

        case = await session.get(CaseRow, intent["case_id"], with_for_update=True)
        if case:
            await case_event(
                session,
                case,
                "RECOVERY_PARTIALLY_FILLED",
                {"action_id": action.id, "accepted_qty": quantity, "missing_qty": missing},
            )
    if mission.status == "ACTIVE":
        await queue_check(session, store, mission, key="partial-" + action.id)
    receipt.response = {"action_id": action.id}
    return action


async def record_arrival(session, action_id, quantity, principal, key):
    """Goods the owner saw arrive: no source reports them for an order sent by hand."""
    store, mission, _, action = await lock_action(session, action_id)
    receipt, replay = await command(
        session,
        principal,
        "record_goods_arrival",
        key,
        {"action_id": action_id, "quantity": quantity},
    )
    if replay:
        return action
    sku = action.purchase_snapshot["sku_id"]
    inbound = await session.get(InboundRow, (action.id, sku))
    if action.channel != "assisted" or action.status != "SUCCEEDED" or inbound is None:
        raise AppError(
            409, "ARRIVAL_NOT_EXPECTED", "Only a confirmed order sent by its owner takes an arrival"
        )
    stock = await session.get(StockRow, (store.id, sku))
    outstanding = inbound.ordered_qty - inbound.received_qty
    arrived = outstanding if quantity is None else quantity
    if not 0 < arrived <= outstanding or stock.in_transit < arrived:
        raise AppError(409, "GOODS_QUANTITY_CONFLICT", "More goods than this order still expects")
    now = await session.scalar(select(func.clock_timestamp()))
    inbound.received_qty += arrived
    stock.in_transit -= arrived
    stock.on_hand += arrived
    store.state_version += 1
    store.data_as_of = max(filter(None, [store.data_as_of, now]))
    action.updated_at = now
    effect_id = digest([action.id, "GOODS_RECEIVED", inbound.received_qty])
    session.add(
        LedgerEntry(
            id=effect_id,
            store_id=store.id,
            effect_type="GOODS_RECEIVED",
            state_version=store.state_version,
            document=RecordedArrival(
                source="owner",
                payload={"action_id": action.id, "sku_id": sku, "quantity": arrived},
                occurred_at=now,
                simulation_time=store.simulation_time,
                recorded_by=principal,
            ).model_dump(mode="json"),
        )
    )
    await session.flush()
    references = [{"type": "action", "id": action.id}]
    await timeline(
        session,
        mission,
        "PURCHASE_RECEIVED",
        f"店主登记到货 {arrived} 件，累计 {inbound.received_qty}/{inbound.ordered_qty} 件。",
        actor=principal,
        references=references,
    )
    from app.learning.capture import mission_event

    await mission_event(session, mission, "PURCHASE_RECEIVED", effect_id, None, references)
    from app.operations_cases.lifecycle import settle_mission

    await settle_mission(session, mission)
    if mission.status == "ACTIVE":
        await queue_check(session, store, mission, key="arrival-" + effect_id)
    receipt.response = {"action_id": action.id}
    return action
