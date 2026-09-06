from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.alerts.repository import reconcile
from app.alerts.rules import Finding
from app.execution.models import EvidenceRow
from app.execution.repository import PENDING
from app.execution.schemas import PurchaseReceipt
from app.missions.models import InboundRow
from app.missions.repository import timeline
from app.operations.models import LedgerEntry, StockRow
from app.operations.repository import digest


async def action_alert(session, store, mission, action, reason=None):
    findings = (
        [
            Finding(
                "ACTION_EXCEPTION",
                "CRITICAL" if action.manual_review else "WARNING",
                "采购结果需要核对：" + reason,
                {"action_id": action.id, "reason": reason},
            )
        ]
        if reason
        else []
    )
    await reconcile(
        session,
        mission,
        findings,
        {"ACTION_EXCEPTION"},
        store.state_version,
        action.plan_id,
        action_id=action.id,
    )


async def close_action(session, store, mission, action, status, *, reason=None):
    if action.reserved_minor:
        store.reserved_cash_minor -= action.reserved_minor
        action.reserved_minor = 0
        store.state_version += 1
    action.status, action.last_error = status, reason
    action.next_attempt_at = None
    action.updated_at = await session.scalar(select(func.clock_timestamp()))
    if store.active_action_id == action.id:
        store.active_action_id = None
    if mission.current_action_id == action.id:
        mission.current_action_id = None
    await timeline(
        session,
        mission,
        "ACTION_" + status,
        reason or status,
        references=[{"type": "action", "id": action.id}],
    )


async def record_conflict(session, store, mission, action, raw, reason="RECEIPT_CONFLICT"):
    now = await session.scalar(select(func.clock_timestamp()))
    document = {"reason": reason, "response": raw}
    await session.execute(
        insert(EvidenceRow)
        .values(
            id=digest([action.id, document]),
            action_id=action.id,
            document=document,
            recorded_at=now,
        )
        .on_conflict_do_nothing()
    )
    action.manual_review = True
    if action.status in PENDING:
        action.status = "UNKNOWN"
    action.last_error = reason
    action.updated_at = now
    await action_alert(session, store, mission, action, reason)


async def apply_receipt(session, store, mission, action, raw):
    try:
        receipt = PurchaseReceipt.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        await record_conflict(session, store, mission, action, raw, "INVALID_SOURCE_RESPONSE")
        return False
    purchase = action.purchase_snapshot
    accepted = receipt.status == "ACCEPTED"
    inconsistent = (
        receipt.action_id != action.id
        or receipt.currency != purchase["currency"]
        or (
            accepted
            and (receipt.quantity != action.quantity or receipt.total_minor != action.amount_minor)
        )
    )
    if action.status == "SUCCEEDED":
        inconsistent |= not accepted or receipt.external_order_id != action.external_order_id
        if not inconsistent:
            return False
    elif action.status not in {"EXECUTING", "UNKNOWN"}:
        inconsistent = True
    if inconsistent:
        await record_conflict(session, store, mission, action, raw)
        return False
    if action.manual_review:
        # Conflicting evidence requires explicit operator investigation, never silent overwrites.
        return False
    if receipt.status == "PENDING":
        action.status = "UNKNOWN"
        action.last_error = "SUPPLIER_PENDING"
        await action_alert(session, store, mission, action, action.last_error)
        return False
    if receipt.status == "REJECTED":
        action.receipt = receipt.model_dump(mode="json")
        await close_action(session, store, mission, action, "FAILED", reason="SUPPLIER_REJECTED")
        await action_alert(session, store, mission, action, "SUPPLIER_REJECTED")
        return False
    effect_id = digest([action.id, "PURCHASE_ACCEPTED"])
    if await session.get(LedgerEntry, effect_id):
        return False
    stock = await session.get(StockRow, (store.id, purchase["sku_id"]))
    if store.cash_minor - receipt.total_minor < store.reserved_cash_minor - action.reserved_minor:
        await record_conflict(session, store, mission, action, raw, "ACCOUNTING_CONFLICT")
        return False
    if stock.in_transit + receipt.quantity > 9223372036854775807:
        await record_conflict(session, store, mission, action, raw, "QUANTITY_OUT_OF_RANGE")
        return False
    store.cash_minor -= receipt.total_minor
    store.reserved_cash_minor -= action.reserved_minor
    action.reserved_minor = 0
    stock.in_transit += receipt.quantity
    store.state_version += 1
    store.data_as_of = max(filter(None, [store.data_as_of, receipt.recorded_at]))
    action.receipt = receipt.model_dump(mode="json")
    action.external_order_id = receipt.external_order_id
    session.add(
        InboundRow(
            action_id=action.id,
            store_id=store.id,
            sku_id=stock.sku_id,
            ordered_qty=receipt.quantity,
            received_qty=0,
            expected_arrival_at=datetime.fromisoformat(purchase["expected_arrival_at"]),
        )
    )
    session.add(
        LedgerEntry(
            id=effect_id,
            store_id=store.id,
            effect_type="PURCHASE_ACCEPTED",
            state_version=store.state_version,
            document=action.receipt,
        )
    )
    await close_action(session, store, mission, action, "SUCCEEDED")
    await action_alert(session, store, mission, action)
    await session.flush()
    return True
