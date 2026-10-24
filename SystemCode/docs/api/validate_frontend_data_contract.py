"""Validate planned frontend read contracts and fixtures, without starting services."""

import json
from copy import deepcopy
from datetime import datetime
from itertools import pairwise
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from validate_contracts import check_document

ROOT = Path(__file__).resolve().parent


def validate_semantics(model, value):
    """Cross-field fixture promises that JSON Schema alone cannot establish."""
    if model == "SaleRecord":
        assert (
            value["sales_amount_minor"] == value["quantity"] * value["unit_price_minor"]
        )
    elif model == "SaleSummary":
        start, end = [datetime.fromisoformat(value[k]) for k in ("from", "to")]
        assert 0 < (end - start).total_seconds() <= 90 * 86400
        buckets = value["buckets"]
        assert (
            buckets
            and buckets[0]["from"] == value["from"]
            and buckets[-1]["to"] == value["to"]
        )
        for previous, following in pairwise(buckets):
            assert previous["to"] == following["from"]
        for bucket in buckets:
            left, right = [datetime.fromisoformat(bucket[k]) for k in ("from", "to")]
            assert 0 < (right - left).total_seconds() <= 86400
        for key in ("record_count", "recorded_quantity", "recorded_sales_amount_minor"):
            assert value[key] == sum(bucket[key] for bucket in buckets)
    elif model == "InboundItem":
        ordered, received = value["ordered_quantity"], value["received_quantity"]
        assert 0 <= received <= ordered
        assert value["remaining_quantity"] == ordered - received
        expected = (
            "RECEIVED"
            if received == ordered
            else "PARTIALLY_RECEIVED"
            if received
            else "NOT_RECEIVED"
        )
        assert value["arrival_status"] == expected
        if expected == "RECEIVED":
            assert value["is_overdue"] is False


def main():
    document = check_document(ROOT / "frontend-data.openapi.json")
    runtime = json.loads(
        (ROOT / "backend.runtime.openapi.json").read_text(encoding="utf-8")
    )
    shared = {
        "Action",
        "PurchaseReceipt",
        "ProposedPurchase",
        "State",
        "Stock",
        "Freshness",
        "Error",
        "ErrorDetail",
    }
    for name in shared:
        assert (
            document["components"]["schemas"][name]
            == runtime["components"]["schemas"][name]
        ), name
    expected_paths = {
        "/api/v1/" + suffix
        for suffix in (
            "me",
            "stores",
            "sales",
            "sales/summary",
            "actions",
            "inbounds",
            "ledger-entries",
        )
    }
    assert set(document["paths"]) == expected_paths
    status = json.loads(
        (ROOT / "implementation-status.json").read_text(encoding="utf-8")
    )
    implemented = set(status["implemented_operation_ids"])
    examples = {}
    for path, item in document["paths"].items():
        assert set(item) == {"get"}, path
        operation = item["get"]
        assert operation["operationId"] in implemented
        actual = runtime["paths"][path]["get"]
        assert actual["operationId"] == operation["operationId"]
        assert actual["x-implementation-status"] == "implemented"
        assert actual["security"] == [{"UserBearer": []}]
        assert operation["security"] == [{"UserBearer": []}]
        assert "requestBody" not in operation
        body = operation["responses"]["200"]["content"]["application/json"]
        name = body["schema"]["$ref"].rsplit("/", 1)[1]
        examples[name] = body["examples"]["sc01"]["value"]
        Draft202012Validator(
            {
                "$ref": f"#/components/schemas/{name}",
                "components": runtime["components"],
            },
            format_checker=FormatChecker(),
        ).validate(examples[name])

    sale = examples["SaleList"]["items"][0]
    validate_semantics("SaleRecord", sale)
    validate_semantics("SaleSummary", examples["SaleSummary"])
    for row in examples["InboundList"]["items"]:
        validate_semantics("InboundItem", row)
    summary = examples["SaleSummary"]
    assert summary["record_count"] == len(examples["SaleList"]["items"])
    assert summary["recorded_quantity"] == sum(
        s["quantity"] for s in examples["SaleList"]["items"]
    )
    assert summary["recorded_sales_amount_minor"] == sum(
        s["sales_amount_minor"] for s in examples["SaleList"]["items"]
    )
    ledger = examples["LedgerEntryList"]["items"]
    initial = next(
        row["opening_state"] for row in ledger if row["effect_type"] == "INIT"
    )
    changes = [row["changes"] for row in ledger if row["changes"] is not None]
    assert (
        initial["cash_minor"] + sum(row["cash_delta_minor"] for row in changes) == 40000
    )
    assert (
        initial["receivables_minor"]
        + sum(row["receivables_delta_minor"] for row in changes)
        == 20000
    )
    assert (
        initial["stocks"][0]["on_hand"] + sum(row["on_hand_delta"] for row in changes)
        == 70
    )
    assert (
        initial["stocks"][0]["in_transit"]
        + sum(row["in_transit_delta"] for row in changes)
        == 0
    )
    assert (
        len([row for row in ledger if row["effect_type"] == "PURCHASE_ACCEPTED"]) == 2
    )
    assert (
        len(
            {
                row["action_id"]
                for row in ledger
                if row["effect_type"] == "PURCHASE_ACCEPTED"
            }
        )
        == 2
    )
    assert all(
        row["simulation_time"] is None
        for row in ledger
        if row["effect_type"] == "PURCHASE_ACCEPTED"
    )

    def rejected(name, value):
        schema = {
            "$ref": "#/components/schemas/" + name,
            "components": document["components"],
        }
        assert not Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).is_valid(value), name

    rejected("SaleRecord", {**sale, "quantity": 0})
    rejected("SaleRecord", {**sale, "unit_price_minor": 0.1})
    rejected("SaleRecord", {k: v for k, v in sale.items() if k != "event_id"})
    rejected("SaleSummary", {**summary, "coverage": "COMPLETE"})
    rejected("SaleSummary", {**summary, "recorded_sales_amount_minor": -1})
    rejected(
        "CurrentUser", {**examples["CurrentUser"], "token": "not-a-real-credential"}
    )
    rejected(
        "InboundItem",
        {**examples["InboundList"]["items"][0], "arrival_status": "SUCCEEDED"},
    )
    opening_row = next(row for row in ledger if row["effect_type"] == "INIT")
    rejected("LedgerEntryView", {**opening_row, "opening_state": None})
    rejected("ReadContext", {**examples["SaleList"]["context"], "source_sequence": -1})
    rejected("SaleRecord", {**sale, "occurred_at": "2026-09-07T00:00:00"})

    invalid_cases = []
    bad = deepcopy(sale)
    bad["sales_amount_minor"] += 1
    invalid_cases.append(("SaleRecord", bad))
    bad = deepcopy(summary)
    bad["recorded_quantity"] += 1
    invalid_cases.append(("SaleSummary", bad))
    bad = deepcopy(summary)
    bad["buckets"][1]["from"] = "2026-09-08T01:00:00Z"
    invalid_cases.append(("SaleSummary", bad))
    bad = deepcopy(examples["InboundList"]["items"][0])
    bad["remaining_quantity"] = 1
    invalid_cases.append(("InboundItem", bad))
    for model, value in invalid_cases:
        try:
            validate_semantics(model, value)
        except AssertionError:
            continue
        raise AssertionError("Cross-field invalid fixture accepted: " + model)
    print(
        f"PASS {len(shared)} unchanged runtime schemas, 7 implemented GETs, fixture arithmetic and SC01 ledger"
    )
    print(
        "PASS 10 schema negatives and 4 cross-field negatives; no application or database executed"
    )


if __name__ == "__main__":
    main()
