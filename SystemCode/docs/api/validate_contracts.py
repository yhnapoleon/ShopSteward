"""Validate design contracts only; does not start or implement backend services."""

from __future__ import annotations

import json
import re
import copy
import hashlib
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate


ROOT = Path(__file__).resolve().parent
METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def plan_digest(plan):
    """Document-example check only; the future application owns its own implementation."""
    fields = ("mission_id", "plan_version", "input_snapshot", "candidates",
              "recommended_candidate_id", "proposed_purchase", "expires_at")
    payload = {"hash_version": "decision-v1", **{key: plan[key] for key in fields}}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def check_plan_example(plan):
    """Check the public finite-candidate example's cross-field promises, not runtime behavior."""
    snapshot = plan["input_snapshot"]
    state, policy, forecast, offer = [snapshot[key] for key in ("state", "policy", "forecast", "offer")]
    assert plan["state_version"] == state["state_version"]
    assert plan["forecast_version"] == forecast["forecast_version"]
    assert plan["policy_version"] == snapshot["policy_version"]
    assert plan["rule_version"] == snapshot["rule_version"]
    assert state["store_id"] == forecast["store_id"]
    assert policy["supplier_id"] == offer["supplier_id"]
    assert state["currency"] == offer["currency"]
    assert state["available_cash_minor"] == state["cash_minor"] - state["reserved_cash_minor"]
    stock = next(s for s in state["stocks"] if s["sku_id"] == offer["sku_id"])
    assert stock["sku_id"] == forecast["sku_id"]
    assert stock["remaining_demand"] == forecast["remaining_demand"]
    assert stock["forecast_version"] == forecast["forecast_version"]
    inbound = snapshot["inbound_items"]
    assert inbound == sorted(inbound, key=lambda row: (row["action_id"], row["sku_id"]))
    assert all(row["sku_id"] == stock["sku_id"] for row in inbound)
    assert sum(row["remaining_quantity"] for row in inbound) == stock["in_transit"]
    assert snapshot["eligible_inbound_qty"] == sum(row["remaining_quantity"] for row in inbound if row["eligible"])
    dt = datetime.fromisoformat
    for row in inbound:
        if row["eligible"]:
            assert row["expected_arrival_at"] is not None
            assert dt(row["expected_arrival_at"]) <= dt(forecast["horizon_end"])
    assert dt(offer["valid_from"]) <= dt(snapshot["evaluated_at"]) < dt(offer["valid_until"])
    assert dt(forecast["data_as_of"]) <= dt(snapshot["evaluated_at"]) < dt(forecast["valid_until"])
    assert dt(snapshot["last_successful_sync_at"]) <= dt(snapshot["evaluated_at"]) < dt(snapshot["source_fresh_until"])
    assert dt(snapshot["evaluated_at"]) < dt(plan["expires_at"]) <= min(dt(offer["valid_until"]), dt(forecast["valid_until"]))
    assert dt(forecast["horizon_start"]) <= dt(state["simulation_time"]) < dt(forecast["horizon_end"])
    candidates = plan["candidates"]
    assert candidates == sorted(candidates, key=lambda c: (c["quantity"], c["id"]))
    assert len({c["id"] for c in candidates}) == len(candidates)
    assert {c["quantity"] for c in candidates} == set(policy["candidate_quantities"])
    for candidate in candidates:
        quantity = candidate["quantity"]
        assert candidate["spend_minor"] == quantity * offer["unit_price_minor"]
        assert candidate["cash_after_minor"] == state["available_cash_minor"] - candidate["spend_minor"]
        assert candidate["shortage_qty"] == max(0, forecast["remaining_demand"] - stock["on_hand"] - snapshot["eligible_inbound_qty"] - quantity)
        pack_ok = quantity == 0 or (quantity >= offer["minimum_order_quantity"] and quantity % offer["pack_size"] == 0)
        assert candidate["feasible"] == (pack_ok and candidate["cash_after_minor"] >= policy["cash_floor_minor"])
    feasible = [c for c in candidates if c["feasible"]]
    selected = min(feasible, key=lambda c: (c["shortage_qty"], c["quantity"])) if feasible else None
    assert plan["recommended_candidate_id"] == (selected["id"] if selected else None)
    purchase = plan["proposed_purchase"]
    if selected is None or selected["quantity"] == 0:
        assert purchase is None
    else:
        assert purchase is not None
        assert purchase["store_id"] == state["store_id"]
        assert purchase["sku_id"] == stock["sku_id"]
        assert purchase["supplier_id"] == offer["supplier_id"]
        assert purchase["quantity"] == selected["quantity"]
        assert purchase["unit_price_minor"] == offer["unit_price_minor"]
        assert purchase["total_minor"] == selected["spend_minor"]
        assert purchase["currency"] == state["currency"]
        assert dt(state["simulation_time"]) <= dt(purchase["expected_arrival_at"]) <= dt(forecast["horizon_end"])
    assert plan["proposal_hash"] == plan_digest(plan)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def check_examples(doc):
    count = 0
    for node in walk(doc):
        if "schema" not in node:
            continue
        examples = []
        if "example" in node:
            examples.append(node["example"])
        named_examples = node.get("examples", {})
        if isinstance(named_examples, dict):
            examples.extend(
                item["value"]
                for item in named_examples.values()
                if isinstance(item, dict) and "value" in item
            )
        schema = {**node["schema"], "components": doc["components"]}
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for example in examples:
            validator.validate(example)
            count += 1
    return count


def check_document(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    validate(doc)
    assert doc["openapi"] == "3.1.0"
    operation_ids = set()
    operations = 0
    for node in walk(doc):
        if "$ref" in node:
            reference = node["$ref"]
            assert reference.startswith("#/"), f"Nonlocal ref: {reference}"
            target = doc
            for component in reference[2:].split("/"):
                target = target[component.replace("~1", "/").replace("~0", "~")]
    for schema in doc["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)
    for path_name, path_item in doc["paths"].items():
        for method, operation in path_item.items():
            if method not in METHODS:
                continue
            operation_id = operation["operationId"]
            assert operation_id not in operation_ids, operation_id
            operation_ids.add(operation_id)
            operations += 1
            assert operation["x-phase"] in {"B0", "B1", "B2"}
            assert operation["x-implementation-status"] == "planned"
            parameters = operation.get("parameters", [])
            actual_path = {p["name"] for p in parameters if p["in"] == "path" and p["required"]}
            assert actual_path == set(re.findall(r"\{([^}]+)\}", path_name)), path_name
            if method in {"post", "patch", "put", "delete"}:
                exempt = operation.get("x-provider") in {"llm", "ml"}
                assert exempt or any(
                    p["in"] == "header" and p["name"] == "Idempotency-Key" and p["required"]
                    for p in parameters
                ), operation_id
            if "x-provider" in operation:
                assert operation.get("servers"), operation_id
    examples = check_examples(doc)
    print(f"PASS {path.name}: {operations} operations, {len(doc['components']['schemas'])} schemas, {examples} examples")
    return doc


def main():
    backend, services = [check_document(ROOT / name) for name in ("backend.openapi.json", "services.openapi.json")]
    shared = backend["components"]["schemas"].keys() & services["components"]["schemas"].keys()
    for name in shared:
        assert backend["components"]["schemas"][name] == services["components"]["schemas"][name], f"Shared schema drift: {name}"
    assert backend["paths"]["/api/v1/plans/{plan_id}/decision"]["post"]["security"] == [{"UserBearer": []}]
    assert backend["paths"]["/internal/v1/events/batches"]["post"]["security"] == [{"ServiceBearer": []}]
    print(f"PASS shared schemas: {len(shared)}; approval and event security boundaries")

    def valid(doc, name, value):
        schema = {"$ref": f"#/components/schemas/{name}", "components": doc["components"]}
        return Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(value)

    decision_op = backend["paths"]["/api/v1/plans/{plan_id}/decision"]["post"]
    decision = decision_op["requestBody"]["content"]["application/json"]["example"]
    assert not valid(backend, "PlanDecision", {**decision, "approved_by": "forged-user"})
    approved = decision_op["responses"]["202"]["content"]["application/json"]["example"]
    assert not valid(backend, "DecisionApproved", {**approved, "action_id": None})
    assert not valid(backend, "ScheduleUpdate", {"interval_seconds": 0, "enabled": True, "expected_schedule_version": 1})
    purchase = services["paths"]["/sim/v1/purchases"]["post"]["requestBody"]["content"]["application/json"]["example"]
    assert not valid(services, "PurchaseRequest", {**purchase, "quantity": -1})
    assert not valid(services, "PurchaseRequest", {**purchase, "expected_total_minor": 400.5})
    llm = services["paths"]["/v1/chat/completions"]["post"]["requestBody"]["content"]["application/json"]["example"]
    assert not valid(services, "LLMChatRequest", {**llm, "stream": True})
    print("PASS negative schema cases: forged approver, missing action, interval, quantity, money, unsupported streaming")

    plan = backend["paths"]["/api/v1/plans/{plan_id}"]["get"]["responses"]["200"]["content"]["application/json"]["example"]
    assert not valid(backend, "Plan", {**plan, "input_snapshot": plan["input_snapshot"]["state"]})
    assert not valid(backend, "Plan", {k: v for k, v in plan.items() if k != "proposed_purchase"})
    snapshot_without_offer = {k: v for k, v in plan["input_snapshot"].items() if k != "offer"}
    assert not valid(backend, "DecisionSnapshot", snapshot_without_offer)
    assert not valid(backend, "PlanDecision", {**decision, "proposal_hash": "sha256:placeholder"})
    receipt = services["paths"]["/sim/v1/purchases"]["post"]["responses"]["200"]["content"]["application/json"]["example"]
    for doc in (backend, services):
        assert not valid(doc, "PurchaseReceipt", {**receipt, "external_order_id": None})
        assert not valid(doc, "PurchaseReceipt", {**receipt, "status": "REJECTED", "reason": None})
        assert valid(doc, "PurchaseReceipt", {**receipt, "status": "REJECTED", "external_order_id": None, "reason": "INSUFFICIENT_CASH"})
        assert not valid(doc, "SalePayload", {"sku_id": "sku_001", "quantity": 0, "unit_price_minor": 2000})
    page = services["paths"]["/sim/v1/runs/{run_id}/events"]["get"]["responses"]["200"]["content"]["application/json"]["example"]
    assert not valid(services, "EventPage", {k: v for k, v in page.items() if k != "source_head_sequence"})
    run = services["paths"]["/sim/v1/runs"]["post"]["responses"]["201"]["content"]["application/json"]["example"]
    assert not valid(services, "ScenarioRun", {k: v for k, v in run.items() if k != "initial_catalog"})
    print("PASS v0.2 negative schema cases: snapshot, purchase, offer, digest, receipt, positive sale, cursor, initial catalog")

    plan_count = 0
    for value in walk(backend["paths"]):
        if {"input_snapshot", "plan_version", "proposal_hash"} <= value.keys():
            check_plan_example(value)
            plan_count += 1
    assert decision["proposal_hash"] == plan["proposal_hash"]
    inconsistent = copy.deepcopy(plan)
    inconsistent["candidates"][2]["spend_minor"] += 1
    inconsistent["proposal_hash"] = plan_digest(inconsistent)
    try:
        check_plan_example(inconsistent)
    except AssertionError:
        pass
    else:
        raise AssertionError("Example validation must reject inconsistent candidate amounts, even with a matching hash")
    assert run["initial_state"]["state_version"] == run["initial_forecast"]["input_state_version"] == 1
    assert run["initial_state"]["store_id"] == run["initial_catalog"]["store_id"] == run["store_id"]
    assert run["initial_state"]["reserved_cash_minor"] == 0
    print(f"PASS {plan_count} Plan examples: snapshot/candidate/purchase consistency and canonical SHA256; scenario initialization")


if __name__ == "__main__":
    main()
