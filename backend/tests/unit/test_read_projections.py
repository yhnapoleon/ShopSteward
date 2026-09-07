from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.reporting.read_projections import day_buckets, inbound_view, ledger_view, sale_view

UTC = UTC
T0 = datetime(2026, 9, 7, 12, tzinfo=UTC)


def sale_document(**overrides):
    value = {
        "event_id": "sale-1",
        "sequence": 3,
        "schema_version": "1.0",
        "store_id": "store-1",
        "event_type": "SALE_RECORDED",
        "occurred_at": "2026-09-07T01:00:00Z",
        "simulation_time": "2026-09-08T02:00:00Z",
        "payload": {"sku_id": "sku-1", "quantity": 2, "unit_price_minor": 125},
    }
    value.update(overrides)
    return value


def event_document(kind, payload, *, event_id="event-1"):
    return {
        "event_id": event_id,
        "sequence": 4,
        "schema_version": "1.0",
        "store_id": "store-1",
        "event_type": kind,
        "occurred_at": "2026-09-07T01:00:00Z",
        "simulation_time": "2026-09-09T02:00:00Z",
        "payload": payload,
    }


def assert_stored_data_error(call):
    with pytest.raises(AppError) as caught:
        call()
    assert (caught.value.status, caught.value.code, caught.value.retryable) == (
        503,
        "INVALID_STORED_DATA",
        False,
    )


def test_sale_view_validates_and_derives_amount():
    row = SimpleNamespace(event_id="sale-1", sequence=3, document=sale_document())

    result = sale_view(row)

    assert result.model_dump(mode="json") == {
        "event_id": "sale-1",
        "sequence": 3,
        "sku_id": "sku-1",
        "quantity": 2,
        "unit_price_minor": 125,
        "sales_amount_minor": 250,
        "occurred_at": "2026-09-07T01:00:00Z",
        "simulation_time": "2026-09-08T02:00:00Z",
    }


@pytest.mark.parametrize(
    "row",
    [
        SimpleNamespace(event_id="wrong", sequence=3, document=sale_document()),
        SimpleNamespace(event_id="sale-1", sequence=4, document=sale_document()),
        SimpleNamespace(
            event_id="sale-1", sequence=3, document=sale_document(event_type="DEMAND_REVISED")
        ),
        SimpleNamespace(event_id="sale-1", sequence=3, document={"event_type": "SALE_RECORDED"}),
    ],
)
def test_sale_view_rejects_corrupt_or_mismatched_storage(row):
    assert_stored_data_error(lambda: sale_view(row))


def test_sale_view_rejects_derived_amount_outside_int64():
    document = sale_document()
    document["payload"] = {"sku_id": "sku-1", "quantity": 2, "unit_price_minor": 2**62}
    assert_stored_data_error(
        lambda: sale_view(SimpleNamespace(event_id="sale-1", sequence=3, document=document))
    )


def test_day_buckets_intersects_utc_days_and_keeps_empty_buckets():
    start = datetime(2026, 9, 7, 12, tzinfo=UTC)
    end = datetime(2026, 9, 9, 6, tzinfo=UTC)
    record = sale_view(SimpleNamespace(event_id="sale-1", sequence=3, document=sale_document()))

    result = day_buckets(start, end, [record])

    assert [(b.from_, b.to) for b in result] == [
        (start, datetime(2026, 9, 8, tzinfo=UTC)),
        (datetime(2026, 9, 8, tzinfo=UTC), datetime(2026, 9, 9, tzinfo=UTC)),
        (datetime(2026, 9, 9, tzinfo=UTC), end),
    ]
    assert [
        (b.record_count, b.recorded_quantity, b.recorded_sales_amount_minor) for b in result
    ] == [
        (0, 0, 0),
        (1, 2, 250),
        (0, 0, 0),
    ]


def test_day_buckets_rejects_aggregate_int64_overflow():
    record = sale_view(SimpleNamespace(event_id="sale-1", sequence=3, document=sale_document()))
    record.quantity = 2**63 - 1
    record.sales_amount_minor = 2**63 - 1
    with pytest.raises(AppError) as caught:
        day_buckets(T0, T0.replace(day=8), [record, record])
    assert (caught.value.status, caught.value.code) == (422, "AGGREGATE_OUT_OF_RANGE")


def test_day_buckets_supports_interval_within_maximum_datetime_day():
    start = datetime(9999, 12, 31, tzinfo=UTC)
    end = datetime(9999, 12, 31, 1, tzinfo=UTC)

    result = day_buckets(start, end, [])

    assert len(result) == 1
    assert (result[0].from_, result[0].to) == (start, end)


def test_inbound_view_derives_partial_and_strict_overdue_status():
    inbound = SimpleNamespace(
        action_id="action-1",
        store_id="store-1",
        sku_id="sku-1",
        ordered_qty=10,
        received_qty=4,
        expected_arrival_at=T0,
    )
    action = SimpleNamespace(
        id="action-1",
        store_id="store-1",
        mission_id="mission-1",
        external_order_id="order-1",
        purchase_snapshot={"sku_id": "sku-1", "quantity": 10},
    )

    at_eta = inbound_view(inbound, action, T0)
    late = inbound_view(inbound, action, T0.replace(hour=13))

    assert (at_eta.arrival_status, at_eta.remaining_quantity, at_eta.is_overdue) == (
        "PARTIALLY_RECEIVED",
        6,
        False,
    )
    assert late.is_overdue is True


def test_inbound_view_returns_false_for_received_and_null_for_unknown_clock():
    action = SimpleNamespace(
        id="action-1",
        store_id="store-1",
        mission_id="mission-1",
        external_order_id=None,
        purchase_snapshot={"sku_id": "sku-1", "quantity": 10},
    )
    complete = SimpleNamespace(
        action_id="action-1",
        store_id="store-1",
        sku_id="sku-1",
        ordered_qty=10,
        received_qty=10,
        expected_arrival_at=None,
    )
    pending = SimpleNamespace(**{**complete.__dict__, "received_qty": 0})

    assert inbound_view(complete, action, None).is_overdue is False
    assert inbound_view(pending, action, None).is_overdue is None


def test_inbound_view_rejects_ordered_quantity_different_from_action_snapshot():
    inbound = SimpleNamespace(
        action_id="action-1",
        store_id="store-1",
        sku_id="sku-1",
        ordered_qty=9,
        received_qty=0,
        expected_arrival_at=None,
    )
    action = SimpleNamespace(
        id="action-1",
        store_id="store-1",
        mission_id="mission-1",
        external_order_id="order-1",
        purchase_snapshot={"sku_id": "sku-1", "quantity": 10},
    )

    assert_stored_data_error(lambda: inbound_view(inbound, action, None))


@pytest.mark.parametrize(
    "field,value", [("action_id", "wrong"), ("store_id", "wrong"), ("sku_id", "wrong")]
)
def test_inbound_view_rejects_mismatched_associations(field, value):
    inbound = SimpleNamespace(
        action_id="action-1",
        store_id="store-1",
        sku_id="sku-1",
        ordered_qty=10,
        received_qty=0,
        expected_arrival_at=None,
    )
    action = SimpleNamespace(
        id="action-1",
        store_id="store-1",
        mission_id="mission-1",
        external_order_id=None,
        purchase_snapshot={"sku_id": "sku-1", "quantity": 10},
    )
    setattr(inbound, field, value)
    assert_stored_data_error(lambda: inbound_view(inbound, action, None))


def test_ledger_view_maps_init_state_without_changes():
    state = {
        "store_id": "store-1",
        "state_version": 1,
        "currency": "CNY",
        "cash_minor": 1000,
        "reserved_cash_minor": 0,
        "available_cash_minor": 1000,
        "receivables_minor": 0,
        "stocks": [],
        "data_as_of": "2026-09-07T01:00:00Z",
        "simulation_time": "2026-09-07T00:00:00Z",
    }
    row = SimpleNamespace(
        id="ledger-1",
        store_id="store-1",
        state_version=1,
        effect_type="INIT",
        source_event_id=None,
        document=state,
    )

    result = ledger_view(row, {})

    assert result.sku_id is None and result.changes is None
    assert result.opening_state.store_id == "store-1"
    assert result.occurred_at == datetime(2026, 9, 7, 1, tzinfo=UTC)
    assert result.simulation_time == datetime(2026, 9, 7, tzinfo=UTC)


def test_ledger_view_maps_receipt_and_uses_no_simulation_time():
    receipt = {
        "action_id": "action-1",
        "status": "ACCEPTED",
        "external_order_id": "order-1",
        "quantity": 10,
        "total_minor": 300,
        "currency": "CNY",
        "recorded_at": "2026-09-07T03:00:00Z",
        "reason": None,
    }
    row = SimpleNamespace(
        id="ledger-2",
        store_id="store-1",
        state_version=2,
        effect_type="PURCHASE_ACCEPTED",
        source_event_id=None,
        document=receipt,
    )
    action = SimpleNamespace(
        id="action-1",
        store_id="store-1",
        purchase_snapshot={
            "sku_id": "sku-1",
            "quantity": 10,
            "total_minor": 300,
            "currency": "CNY",
        },
    )

    result = ledger_view(row, {"action-1": action})

    assert (result.sku_id, result.action_id, result.simulation_time) == ("sku-1", "action-1", None)
    assert result.changes.model_dump() == {
        "cash_delta_minor": -300,
        "receivables_delta_minor": 0,
        "on_hand_delta": 0,
        "in_transit_delta": 10,
    }


@pytest.mark.parametrize(
    "kind,payload,expected",
    [
        (
            "GOODS_RECEIVED",
            {"action_id": "action-1", "sku_id": "sku-1", "quantity": 3},
            (0, 0, 3, -3, None),
        ),
        (
            "SALE_RECORDED",
            {"sku_id": "sku-1", "quantity": 2, "unit_price_minor": 125},
            (0, 250, -2, 0, None),
        ),
        (
            "DEMAND_REVISED",
            {
                "sku_id": "sku-1",
                "remaining_demand": 7,
                "forecast_version": "v2",
                "data_as_of": "2026-09-07T01:00:00Z",
                "valid_until": "2026-09-10T01:00:00Z",
                "horizon_start": "2026-09-08T00:00:00Z",
                "horizon_end": "2026-09-10T00:00:00Z",
            },
            (0, 0, 0, 0, 7),
        ),
    ],
)
def test_ledger_view_maps_typed_events(kind, payload, expected):
    row = SimpleNamespace(
        id="ledger-3",
        store_id="store-1",
        state_version=3,
        effect_type=kind,
        source_event_id="event-1",
        document=event_document(kind, payload),
    )
    action = SimpleNamespace(
        id="action-1", store_id="store-1", purchase_snapshot={"sku_id": "sku-1"}
    )

    result = ledger_view(row, {"action-1": action})

    changes = result.changes
    assert (
        changes.cash_delta_minor,
        changes.receivables_delta_minor,
        changes.on_hand_delta,
        changes.in_transit_delta,
        result.remaining_demand_after,
    ) == expected


def test_ledger_view_rejects_event_row_identity_mismatch():
    row = SimpleNamespace(
        id="ledger-3",
        store_id="store-1",
        state_version=3,
        effect_type="SALE_RECORDED",
        source_event_id="other",
        document=event_document(
            "SALE_RECORDED",
            {
                "sku_id": "sku-1",
                "quantity": 2,
                "unit_price_minor": 125,
            },
        ),
    )
    assert_stored_data_error(lambda: ledger_view(row, {}))


def test_ledger_view_rejects_missing_or_mismatched_purchase_action():
    receipt = {
        "action_id": "action-1",
        "status": "ACCEPTED",
        "external_order_id": "order-1",
        "quantity": 10,
        "total_minor": 300,
        "currency": "CNY",
        "recorded_at": "2026-09-07T03:00:00Z",
        "reason": None,
    }
    row = SimpleNamespace(
        id="ledger-2",
        store_id="store-1",
        state_version=2,
        effect_type="PURCHASE_ACCEPTED",
        source_event_id=None,
        document=receipt,
    )
    assert_stored_data_error(lambda: ledger_view(row, {}))
    wrong = SimpleNamespace(id="action-1", store_id="other", purchase_snapshot={"sku_id": "sku-1"})
    assert_stored_data_error(lambda: ledger_view(row, {"action-1": wrong}))
