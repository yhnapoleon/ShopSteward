from sqlalchemy import select

from app.core.errors import AppError
from app.execution.accounting import apply_receipt, record_conflict
from app.execution.models import ActionRow
from app.execution.repository import lock_action
from app.missions.models import InboundRow
from app.operations.models import Store


class EventActionConflict(AppError):
    def __init__(self, action_id, raw, reason="RECEIPT_CONFLICT"):
        super().__init__(409, reason, "Event conflicts with the approved purchase")
        self.action_id, self.raw = action_id, raw


async def persist_conflict(session, error):
    store, mission, _, action = await lock_action(session, error.action_id)
    await record_conflict(session, store, mission, action, error.raw, error.code)


async def prepare_receipts(db, batch, client):
    """Read missing confirmations before entering the atomic event transaction."""
    identifiers = {
        event.payload.action_id for event in batch.events if event.event_type == "GOODS_RECEIVED"
    }
    async with db.session() as session:
        pending = (
            list(
                await session.scalars(
                    select(ActionRow.id)
                    .join(Store, Store.id == ActionRow.store_id)
                    .where(
                        ActionRow.id.in_(identifiers),
                        Store.scenario_run_id == batch.scenario_run_id,
                        ActionRow.status.in_(["EXECUTING", "UNKNOWN"]),
                        ActionRow.manual_review.is_(False),
                    )
                )
            )
            if identifiers
            else []
        )
    receipts = {}
    for identifier in pending:
        receipts[identifier] = await client.get_purchase(identifier)
    return receipts


async def apply_purchase_event(session, store, stock, event, receipts):
    payload = event.payload
    initial = await session.get(ActionRow, payload.action_id)
    if (
        initial is None
        or initial.store_id != store.id
        or initial.purchase_snapshot["sku_id"] != stock.sku_id
        or initial.status not in {"EXECUTING", "UNKNOWN", "SUCCEEDED", "FAILED"}
        or initial.execution_state_version is None
    ):
        raise AppError(409, "ACTION_NOT_CONFIRMED", "Event requires an approved, sent local action")
    _, mission, _, action = await lock_action(session, initial.id)
    if event.event_type == "PURCHASE_ACCEPTED":
        raw = {
            "action_id": action.id,
            "status": "ACCEPTED",
            "external_order_id": payload.external_order_id,
            "quantity": payload.quantity,
            "total_minor": payload.total_minor,
            "currency": store.currency,
            "recorded_at": event.occurred_at.isoformat(),
            "reason": None,
        }
        await apply_receipt(session, store, mission, action, raw)
        if action.manual_review:
            raise EventActionConflict(action.id, event.model_dump(mode="json"), action.last_error)
        return False  # The shared Action effect owns its ledger entry and version.
    if action.status != "SUCCEEDED" and receipts.get(action.id) is not None:
        await apply_receipt(session, store, mission, action, receipts[action.id])
    if action.manual_review:
        raise EventActionConflict(action.id, event.model_dump(mode="json"), action.last_error)
    if action.status != "SUCCEEDED":
        raise AppError(
            409, "ACTION_NOT_CONFIRMED", "Receipt query must confirm purchase before goods"
        )
    inbound = await session.get(InboundRow, (action.id, stock.sku_id))
    if (
        inbound is None
        or inbound.received_qty + payload.quantity > inbound.ordered_qty
        or stock.in_transit < payload.quantity
    ):
        raise EventActionConflict(
            action.id, event.model_dump(mode="json"), "GOODS_QUANTITY_CONFLICT"
        )
    if stock.on_hand + payload.quantity > 9223372036854775807:
        raise EventActionConflict(action.id, event.model_dump(mode="json"), "QUANTITY_OUT_OF_RANGE")
    inbound.received_qty += payload.quantity
    stock.in_transit -= payload.quantity
    stock.on_hand += payload.quantity
    return True
