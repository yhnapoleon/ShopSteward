"""Real PG assertions for source facts, replay, mode and order ownership."""

import asyncio
from uuid import uuid4

import pytest
from test_purchases import client_app, post, purchase, seed_run, world

pytestmark = pytest.mark.asyncio


async def sandbox(client, **parameters):
    response = await post(
        client,
        "/sim/v1/runs",
        {"scenario": "SANDBOX", "label": "控制台测试", "parameters": parameters},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def detail(client, run_id):
    response = await client.get(f"/sim/v1/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def trigger(client, run_id, body, key=None):
    return await post(client, f"/sim/v1/runs/{run_id}/triggers", body, key)


async def test_sandbox_parameters_persist_and_creation_replays_original_seed():
    async with client_app() as (client, app):
        seed = await sandbox(client, cash_minor=55000, on_hand=12, remaining_demand=45)
        run_id = seed["scenario_run_id"]
        current = await detail(client, run_id)
        assert (current["state"]["cash_minor"], current["state"]["stocks"][0]["on_hand"]) == (
            55000,
            12,
        )
        assert current["scenario"] == "SANDBOX" and current["label"] == "控制台测试"
        assert seed["initial_forecast"]["predicted_quantity"] == 45
        assert current["orders"] == []
        before = await world(app, run_id)
        assert (await detail(client, run_id)) == current
        assert await world(app, run_id) == before
    async with client_app() as (client, app):
        assert (await detail(client, run_id))["state"] == current["state"]
        listing = await client.get("/sim/v1/runs?limit=100")
        assert any(row["scenario_run_id"] == run_id for row in listing.json()["items"])


async def test_concurrent_sale_replay_has_one_effect_and_old_sequence_is_rejected():
    async with client_app() as (client, app):
        seed = await sandbox(client)
        run_id, key = seed["scenario_run_id"], str(uuid4())
        body = {"kind": "sale", "expected_sequence": 0, "quantity": 5, "unit_price_minor": 2000}
        replies = await asyncio.gather(*[trigger(client, run_id, body, key) for _ in range(5)])
        assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
        receipt = replies[0].json()
        assert all(r.json() == receipt for r in replies)
        state, head, _ = await world(app, run_id)
        assert (head, state["cash_minor"], state["receivables_minor"]) == (1, 100000, 10000)
        assert (state["stocks"][0]["on_hand"], state["stocks"][0]["remaining_demand"]) == (15, 55)
        assert receipt["first_sequence"] == receipt["last_sequence"] == 1
        assert len(receipt["events"]) == 1
        assert (await trigger(client, run_id, body)).json()["error"]["code"] == "SOURCE_CHANGED"
        conflict = await trigger(client, run_id, body | {"quantity": 6}, key)
        assert conflict.status_code == 409
    async with client_app() as (client, app):
        assert (await trigger(client, run_id, body, key)).json() == receipt
        assert (await detail(client, run_id))["last_sequence"] == 1


async def test_invalid_sales_roll_back_time_state_and_sequence_then_demand_can_change():
    async with client_app() as (client, app):
        seed = await sandbox(client, on_hand=3)
        run_id = seed["scenario_run_id"]
        before = await world(app, run_id)
        key = str(uuid4())
        body = {
            "kind": "sale",
            "expected_sequence": 0,
            "quantity": 4,
            "unit_price_minor": 2000,
            "advance_seconds": 3600,
        }
        assert (await trigger(client, run_id, body, key)).status_code == 409
        assert await world(app, run_id) == before
        for quantity in [0, -1, True, 1.5]:
            assert (await trigger(client, run_id, body | {"quantity": quantity})).status_code == 422
        demand = await trigger(
            client, run_id, {"kind": "demand", "expected_sequence": 0, "remaining_demand": 0}
        )
        assert demand.status_code == 200, demand.text
        # Actual sales may exceed the forecast: demand is not a stock constraint.
        sold = await trigger(client, run_id, body | {"expected_sequence": 1, "quantity": 3}, key)
        assert sold.status_code == 200, sold.text
        state, head, _ = await world(app, run_id)
        assert (state["stocks"][0]["on_hand"], state["stocks"][0]["remaining_demand"], head) == (
            0,
            0,
            2,
        )
        assert state["receivables_minor"] == 6000


async def test_partial_and_full_receipt_use_actual_order_and_reject_foreign_or_excess():
    async with client_app() as (client, app):
        seed, other = await sandbox(client), await sandbox(client)
        run_id = seed["scenario_run_id"]
        order = purchase(seed)
        assert (await post(client, "/sim/v1/purchases", order)).json()["status"] == "ACCEPTED"
        before = await world(app, run_id)
        base = {"kind": "receipt", "expected_sequence": 1, "action_id": order["action_id"]}
        assert (
            await trigger(client, other["scenario_run_id"], base | {"expected_sequence": 0})
        ).status_code == 404
        assert (await trigger(client, run_id, base | {"quantity": 41})).status_code == 409
        assert await world(app, run_id) == before
        assert (await trigger(client, run_id, base | {"quantity": 15})).status_code == 200
        current = await detail(client, run_id)
        assert current["orders"][0]["remaining_quantity"] == 25
        assert (
            current["state"]["stocks"][0]["on_hand"],
            current["state"]["stocks"][0]["in_transit"],
        ) == (35, 25)
        assert (await trigger(client, run_id, base | {"expected_sequence": 2})).status_code == 200
        state, head, _ = await world(app, run_id)
        assert (
            state["cash_minor"],
            state["stocks"][0]["on_hand"],
            state["stocks"][0]["in_transit"],
            head,
        ) == (60000, 60, 0, 3)
        assert (await trigger(client, run_id, base | {"expected_sequence": 3})).status_code == 409


async def test_modes_are_separate_and_invalid_configuration_is_rejected():
    async with client_app() as (client, app):
        original, manual = await seed_run(client), await sandbox(client)
        response = await trigger(
            client,
            original["scenario_run_id"],
            {"kind": "demand", "expected_sequence": 0, "remaining_demand": 70},
        )
        assert response.status_code == 409
        assert (
            await post(client, f"/sim/v1/runs/{manual['scenario_run_id']}/advance", {"steps": 1})
        ).status_code == 409
        for body in [
            {"scenario": "SC01", "parameters": {"cash_minor": 1}},
            {"scenario": "SANDBOX", "parameters": {"cash_minor": -1}},
            {"scenario": "SANDBOX", "parameters": {"in_transit": 5}},
            {"scenario": "SANDBOX", "parameters": {"horizon_days": 1, "lead_time_seconds": 172800}},
        ]:
            assert (await post(client, "/sim/v1/runs", body)).status_code == 422


async def test_run_pagination_and_service_authentication():
    async with client_app() as (client, app):
        seed = await sandbox(client)
        a = (await client.get("/sim/v1/runs?limit=1")).json()
        b = (
            await client.get("/sim/v1/runs", params={"limit": 1, "before": a["next_cursor"]})
        ).json()
        assert a["items"][0]["scenario_run_id"] != b["items"][0]["scenario_run_id"]
        assert (await client.get("/sim/v1/runs?before=garbage")).status_code == 422
        assert (
            await client.get(
                f"/sim/v1/runs/{seed['scenario_run_id']}", headers={"Authorization": "Bearer bad"}
            )
        ).status_code == 401


async def test_elapsed_horizon_trigger_does_not_change_world():
    async with client_app() as (client, app):
        seed = await sandbox(client, horizon_days=1, lead_time_seconds=0)
        run_id = seed["scenario_run_id"]
        before = await world(app, run_id)
        r = await trigger(
            client,
            run_id,
            {
                "kind": "demand",
                "expected_sequence": 0,
                "remaining_demand": 80,
                "advance_seconds": 86400,
            },
        )
        assert r.status_code == 409
        assert await world(app, run_id) == before
