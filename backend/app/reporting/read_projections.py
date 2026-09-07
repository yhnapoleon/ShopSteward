from datetime import UTC, datetime, time, timedelta

from pydantic import TypeAdapter, ValidationError

from app.core.errors import AppError
from app.execution.schemas import PurchaseReceipt
from app.operations.schemas import BusinessEvent, SaleEvent, State
from app.reporting.read_schemas import (
    InboundItem,
    LedgerChanges,
    LedgerEntryView,
    SaleBucket,
    SaleRecord,
)

INT64_MAX = 9223372036854775807
_business_event = TypeAdapter(BusinessEvent)


def _invalid_stored_data():
    return AppError(
        503, "INVALID_STORED_DATA", "Stored data cannot be safely read", retryable=False
    )


def _checked_product(left: int, right: int) -> int:
    value = left * right
    if value > INT64_MAX:
        raise _invalid_stored_data()
    return value


def sale_view(row) -> SaleRecord:
    try:
        event = SaleEvent.model_validate(row.document)
        if row.event_id != event.event_id or row.sequence != event.sequence:
            raise ValueError("row identity mismatch")
        amount = _checked_product(event.payload.quantity, event.payload.unit_price_minor)
        return SaleRecord(
            event_id=event.event_id,
            sequence=event.sequence,
            sku_id=event.payload.sku_id,
            quantity=event.payload.quantity,
            unit_price_minor=event.payload.unit_price_minor,
            sales_amount_minor=amount,
            occurred_at=event.occurred_at,
            simulation_time=event.simulation_time,
        )
    except AppError:
        raise
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise _invalid_stored_data() from exc


def _checked_add(left: int, right: int) -> int:
    result = left + right
    if result < 0 or result > INT64_MAX:
        raise AppError(422, "AGGREGATE_OUT_OF_RANGE", "Aggregate exceeds supported range")
    return result


def day_buckets(start: datetime, end: datetime, records: list[SaleRecord]) -> list[SaleBucket]:
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    buckets = []
    bucket_start = start
    while bucket_start < end:
        if bucket_start.date() == datetime.max.date():
            bucket_end = end
        else:
            next_midnight = datetime.combine(bucket_start.date() + timedelta(days=1), time.min, UTC)
            bucket_end = min(next_midnight, end)
        count = quantity = amount = 0
        for record in records:
            instant = record.simulation_time.astimezone(UTC)
            if bucket_start <= instant < bucket_end:
                count = _checked_add(count, 1)
                quantity = _checked_add(quantity, record.quantity)
                amount = _checked_add(amount, record.sales_amount_minor)
        buckets.append(
            SaleBucket(
                **{
                    "from": bucket_start,
                    "to": bucket_end,
                    "record_count": count,
                    "recorded_quantity": quantity,
                    "recorded_sales_amount_minor": amount,
                }
            )
        )
        bucket_start = bucket_end
    return buckets


def inbound_view(inbound, action, simulation_time: datetime | None) -> InboundItem:
    try:
        snapshot = action.purchase_snapshot
        if (
            inbound.action_id != action.id
            or inbound.store_id != action.store_id
            or inbound.sku_id != snapshot["sku_id"]
            or not isinstance(snapshot.get("quantity"), int)
            or isinstance(snapshot.get("quantity"), bool)
            or inbound.ordered_qty != snapshot["quantity"]
            or not isinstance(inbound.ordered_qty, int)
            or isinstance(inbound.ordered_qty, bool)
            or not isinstance(inbound.received_qty, int)
            or isinstance(inbound.received_qty, bool)
            or inbound.ordered_qty < 1
            or inbound.received_qty < 0
            or inbound.received_qty > inbound.ordered_qty
        ):
            raise ValueError("inbound association mismatch")
        remaining = inbound.ordered_qty - inbound.received_qty
        status = (
            "NOT_RECEIVED"
            if inbound.received_qty == 0
            else "RECEIVED"
            if remaining == 0
            else "PARTIALLY_RECEIVED"
        )
        if status == "RECEIVED":
            overdue = False
        elif inbound.expected_arrival_at is None or simulation_time is None:
            overdue = None
        else:
            overdue = simulation_time > inbound.expected_arrival_at
        return InboundItem(
            action_id=inbound.action_id,
            mission_id=action.mission_id,
            sku_id=inbound.sku_id,
            external_order_id=action.external_order_id,
            ordered_quantity=inbound.ordered_qty,
            received_quantity=inbound.received_qty,
            remaining_quantity=remaining,
            expected_arrival_at=inbound.expected_arrival_at,
            arrival_status=status,
            is_overdue=overdue,
        )
    except (AttributeError, KeyError, TypeError, ValueError, ValidationError) as exc:
        raise _invalid_stored_data() from exc


def _action_for(action_by_id, action_id, store_id, sku_id):
    action = action_by_id.get(action_id)
    if (
        action is None
        or action.id != action_id
        or action.store_id != store_id
        or action.purchase_snapshot.get("sku_id") != sku_id
    ):
        raise ValueError("ledger action association mismatch")
    return action


def ledger_view(row, action_by_id: dict) -> LedgerEntryView:
    try:
        common = dict(
            id=row.id,
            state_version=row.state_version,
            effect_type=row.effect_type,
            source_event_id=row.source_event_id,
        )
        if row.effect_type == "INIT":
            state = State.model_validate(row.document)
            if (
                state.store_id != row.store_id
                or state.state_version != row.state_version
                or row.source_event_id is not None
            ):
                raise ValueError("INIT row mismatch")
            return LedgerEntryView(
                **common,
                sku_id=None,
                action_id=None,
                occurred_at=state.data_as_of,
                simulation_time=state.simulation_time,
                changes=None,
                opening_state=state,
                remaining_demand_after=None,
            )
        if row.effect_type == "PURCHASE_ACCEPTED":
            receipt = PurchaseReceipt.model_validate(row.document)
            if receipt.status != "ACCEPTED":
                raise ValueError("purchase ledger receipt is not accepted")
            action = action_by_id.get(receipt.action_id)
            if action is None or action.id != receipt.action_id or action.store_id != row.store_id:
                raise ValueError("purchase action association mismatch")
            sku_id = action.purchase_snapshot["sku_id"]
            if (
                action.purchase_snapshot.get("quantity") != receipt.quantity
                or action.purchase_snapshot.get("total_minor") != receipt.total_minor
                or action.purchase_snapshot.get("currency") != receipt.currency
            ):
                raise ValueError("purchase receipt mismatch")
            return LedgerEntryView(
                **common,
                sku_id=sku_id,
                action_id=receipt.action_id,
                occurred_at=receipt.recorded_at,
                simulation_time=None,
                changes=LedgerChanges(
                    cash_delta_minor=-receipt.total_minor,
                    receivables_delta_minor=0,
                    on_hand_delta=0,
                    in_transit_delta=receipt.quantity,
                ),
                opening_state=None,
                remaining_demand_after=None,
            )
        event = _business_event.validate_python(row.document)
        if (
            event.event_type != row.effect_type
            or event.event_id != row.source_event_id
            or event.store_id != row.store_id
        ):
            raise ValueError("event row mismatch")
        payload = event.payload
        action_id = getattr(payload, "action_id", None)
        if row.effect_type == "GOODS_RECEIVED":
            _action_for(action_by_id, action_id, row.store_id, payload.sku_id)
            changes = LedgerChanges(
                cash_delta_minor=0,
                receivables_delta_minor=0,
                on_hand_delta=payload.quantity,
                in_transit_delta=-payload.quantity,
            )
            remaining = None
        elif row.effect_type == "SALE_RECORDED":
            amount = _checked_product(payload.quantity, payload.unit_price_minor)
            changes = LedgerChanges(
                cash_delta_minor=0,
                receivables_delta_minor=amount,
                on_hand_delta=-payload.quantity,
                in_transit_delta=0,
            )
            remaining = None
        elif row.effect_type == "DEMAND_REVISED":
            changes = LedgerChanges(
                cash_delta_minor=0, receivables_delta_minor=0, on_hand_delta=0, in_transit_delta=0
            )
            remaining = payload.remaining_demand
        else:
            raise ValueError("unsupported ledger effect")
        return LedgerEntryView(
            **common,
            sku_id=payload.sku_id,
            action_id=action_id,
            occurred_at=event.occurred_at,
            simulation_time=event.simulation_time,
            changes=changes,
            opening_state=None,
            remaining_demand_after=remaining,
        )
    except AppError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, ValidationError) as exc:
        raise _invalid_stored_data() from exc
