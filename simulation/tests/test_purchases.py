import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from test_bootstrap import TOKEN, settings, validate_response

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def client_app():
    from simulator.main import create_app

    app = create_app(settings())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://sim",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as client,
    ):
        yield client, app


async def post(client, path, body, key=None):
    return await client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid4())})


async def seed_run(client):
    return (await post(client, "/sim/v1/runs", {"scenario": "SC01"})).json()


def purchase(seed, quantity=40, action_id=None):
    return {
        "action_id": action_id or str(uuid4()),
        "scenario_run_id": seed["scenario_run_id"],
        "store_id": seed["store_id"],
        "sku_id": "sku_001",
        "supplier_id": "supplier_001",
        "quantity": quantity,
        "expected_total_minor": quantity * 1000,
        "currency": "CNY",
    }


async def world(app, run_id):
    from simulator.models import Run

    async with app.state.db.session() as session:
        run = await session.get(Run, run_id)
        return deepcopy(run.world), run.last_sequence, run.step_index


async def test_purchase_is_durable_and_concurrent_replays_only_apply_once():
    async with client_app() as (client, app):
        seed = await seed_run(client)
        body = purchase(seed)
        key = str(uuid4())
        replies = await asyncio.gather(
            *[post(client, "/sim/v1/purchases", body, key if i % 2 else None) for i in range(6)]
        )
        assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
        receipt = replies[0].json()
        assert all(r.json() == receipt for r in replies)
        validate_response(receipt, "/sim/v1/purchases", "post", 200)
        assert receipt["status"] == "ACCEPTED"
        state, head, step = await world(app, seed["scenario_run_id"])
        assert (state["cash_minor"], state["stocks"][0]["in_transit"], head, step) == (
            60000,
            40,
            1,
            0,
        )
        conflict = await post(client, "/sim/v1/purchases", body | {"quantity": 20}, key)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert (await post(client, "/sim/v1/purchases", body | {"quantity": 20})).status_code == 409
        assert (await client.post("/sim/v1/purchases", json=body)).status_code == 422
    async with client_app() as (client, app):
        assert (await client.get(f"/sim/v1/purchases/{body['action_id']}")).json() == receipt
        assert (await post(client, "/sim/v1/purchases", body, key)).json() == receipt
        assert (await client.get(f"/sim/v1/purchases/{uuid4()}")).status_code == 404
        denied = await client.get(
            f"/sim/v1/purchases/{body['action_id']}", headers={"Authorization": "Bearer invalid"}
        )
        assert denied.status_code == 401
        page = (
            await client.get(f"/sim/v1/runs/{seed['scenario_run_id']}/events?after_sequence=0")
        ).json()
        payload = page["events"][0]["payload"]
        assert all(
            payload[k] == receipt[k]
            for k in ("action_id", "external_order_id", "quantity", "total_minor")
        )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"supplier_id": "missing"}, "OFFER_NOT_FOUND"),
        ({"sku_id": "missing"}, "OFFER_NOT_FOUND"),
        ({"quantity": 10, "expected_total_minor": 10000}, "MINIMUM_ORDER_QUANTITY"),
        ({"quantity": 21, "expected_total_minor": 21000}, "PACK_SIZE_MISMATCH"),
        ({"expected_total_minor": 1}, "PRICE_MISMATCH"),
        ({"quantity": 120, "expected_total_minor": 120000}, "INSUFFICIENT_CASH"),
    ],
)
async def test_rejections_are_queryable_and_have_no_world_effect(change, reason):
    async with client_app() as (client, app):
        seed = await seed_run(client)
        body = purchase(seed) | change
        before = await world(app, seed["scenario_run_id"])
        response = await post(client, "/sim/v1/purchases", body)
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert (receipt["status"], receipt["reason"]) == ("REJECTED", reason)
        validate_response(receipt, "/sim/v1/purchases", "post", 200)
        assert (await client.get(f"/sim/v1/purchases/{body['action_id']}")).json() == receipt
        assert (await post(client, "/sim/v1/purchases", body)).json() == receipt
        assert await world(app, seed["scenario_run_id"]) == before


async def test_full_sc01_advance_is_atomic_replayable_and_uses_actual_orders():
    async with client_app() as (client, app):
        seed = await seed_run(client)
        run_id = seed["scenario_run_id"]
        path = f"/sim/v1/runs/{run_id}/advance"
        blocked_key = str(uuid4())
        assert (await post(client, path, {"steps": 1}, blocked_key)).status_code == 409
        first = purchase(seed)
        assert (await post(client, "/sim/v1/purchases", first)).status_code == 200
        before = await world(app, run_id)
        failed = await post(client, path, {"steps": 4})
        assert failed.status_code == 409
        assert failed.json()["error"]["code"] == "SCENARIO_STEP_BLOCKED"
        assert await world(app, run_id) == before
        advanced = await post(client, path, {"steps": 1}, blocked_key)
        assert advanced.status_code == 200, advanced.text
        validate_response(advanced.json(), "/sim/v1/runs/{run_id}/advance", "post", 200)
        assert advanced.json()["last_sequence"] == 2
        middle = await post(client, path, {"steps": 2})
        assert middle.status_code == 200
        state, head, step = await world(app, run_id)
        assert (
            state["stocks"][0]["on_hand"],
            state["stocks"][0]["remaining_demand"],
            state["receivables_minor"],
            head,
            step,
        ) == (50, 70, 20000, 4, 3)
        second = purchase(seed, 20)
        assert (await post(client, "/sim/v1/purchases", second)).status_code == 200
        final = await post(client, path, {"steps": 1})
        assert final.status_code == 200
        assert final.json()["last_sequence"] == 6
        state, _, _ = await world(app, run_id)
        assert (
            state["cash_minor"],
            state["stocks"][0]["on_hand"],
            state["stocks"][0]["in_transit"],
        ) == (40000, 70, 0)
        assert (await post(client, path, {"steps": 1}, blocked_key)).json() == advanced.json()
        assert (await post(client, path, {"steps": 2}, blocked_key)).status_code == 409
        finished = await post(client, path, {"steps": 1})
        assert finished.json()["error"]["code"] == "SCENARIO_FINISHED"
        page = (await client.get(f"/sim/v1/runs/{run_id}/events?after_sequence=0")).json()
        validate_response(page, "/sim/v1/runs/{run_id}/events", "get", 200)
        assert [e["sequence"] for e in page["events"]] == [1, 2, 3, 4, 5, 6]
        demand = page["events"][3]
        assert datetime.fromisoformat(demand["payload"]["data_as_of"]) >= datetime.fromisoformat(
            page["events"][2]["occurred_at"]
        )
        assert datetime.fromisoformat(demand["payload"]["valid_until"]) > datetime.fromisoformat(
            demand["payload"]["data_as_of"]
        )
        assert datetime.fromisoformat(demand["payload"]["horizon_end"]) > datetime.fromisoformat(
            demand["payload"]["horizon_start"]
        )
        assert (
            await post(client, "/sim/v1/runs", {"scenario": "SC01"}, str(uuid4()))
        ).status_code == 201


async def test_receipt_stage_sorts_orders_and_receives_actual_quantity_with_concurrent_advance():
    async with client_app() as (client, app):
        seed = await seed_run(client)
        prefix = str(uuid4())
        orders = [purchase(seed, 20, prefix + "z"), purchase(seed, 60, prefix + "a")]
        for body in orders:
            assert (await post(client, "/sim/v1/purchases", body)).status_code == 200
        path = f"/sim/v1/runs/{seed['scenario_run_id']}/advance"
        key = str(uuid4())
        responses = await asyncio.gather(*[post(client, path, {"steps": 1}, key) for _ in range(4)])
        assert all(r.status_code == 200 for r in responses)
        assert all(r.json() == responses[0].json() for r in responses)
        state, head, step = await world(app, seed["scenario_run_id"])
        assert (state["stocks"][0]["on_hand"], state["stocks"][0]["in_transit"], head, step) == (
            100,
            0,
            4,
            1,
        )
        page = (
            await client.get(f"/sim/v1/runs/{seed['scenario_run_id']}/events?after_sequence=2")
        ).json()
        assert [(e["payload"]["action_id"], e["payload"]["quantity"]) for e in page["events"]] == [
            (prefix + "a", 60),
            (prefix + "z", 20),
        ]
        other = await seed_run(client)
        assert (
            await post(
                client, f"/sim/v1/runs/{other['scenario_run_id']}/advance", {"steps": 1}, key
            )
        ).status_code == 409
        same_action = purchase(other, action_id=orders[0]["action_id"])
        assert (await post(client, "/sim/v1/purchases", same_action)).status_code == 409


async def test_expired_quote_and_eta_outside_horizon_are_rejected():
    from simulator.models import Run

    async with client_app() as (client, app):
        for expired in (True, False):
            seed = await seed_run(client)
            async with app.state.db.session() as session, session.begin():
                run = await session.get(Run, seed["scenario_run_id"], with_for_update=True)
                if expired:
                    snapshot = deepcopy(run.initial_snapshot)
                    snapshot["initial_catalog"]["offers"][0]["valid_until"] = (
                        datetime.fromisoformat(seed["simulation_time"]) - timedelta(seconds=1)
                    ).isoformat()
                    run.initial_snapshot = snapshot
                else:
                    state = deepcopy(run.world)
                    state["simulation_time"] = seed["initial_forecast"]["horizon_end"]
                    run.world = state
            response = await post(client, "/sim/v1/purchases", purchase(seed))
            assert response.status_code == 200
            assert response.json()["status"] == "REJECTED"
            assert response.json()["reason"] == (
                "OFFER_EXPIRED" if expired else "ETA_OUTSIDE_SCENARIO"
            )
