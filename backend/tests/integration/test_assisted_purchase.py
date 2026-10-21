"""A purchase the owner sends by hand: the order message out, the pasted reply back."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text
from test_execution import Supplier, decision, execute, isolated_actions, planned  # noqa: F401
from test_missions import clean_queue, environment, headers  # noqa: F401
from test_operations import state

pytestmark = pytest.mark.integration


async def sent(db, seed, client):
    """Approve the plan for sending by hand and let the worker register it."""
    _, plan = await planned(db, seed, client)
    response = await client.post(
        f"/api/v1/plans/{plan['id']}/decision",
        json=decision(plan) | {"channel": "assisted"},
        headers=headers("approver"),
    )
    assert response.status_code == 202, response.text
    supplier = Supplier()
    await execute(db, seed, supplier)
    assert supplier.calls == []
    return await read(client, response.json()["action_id"])


async def read(client, action_id):
    return (await client.get(f"/api/v1/actions/{action_id}", headers=headers("viewer"))).json()


async def reply(client, action, words, role="approver", **kwargs):
    return await client.post(
        f"/api/v1/actions/{action['id']}/supplier-reply",
        json={"text": words},
        headers=kwargs.pop("headers", headers(role)),
    )


async def jobs(db):
    async with db.session() as session:
        return await session.scalar(
            text(
                "SELECT count(*) FROM job_runs WHERE status IN ('READY','RUNNING','RETRY_WAIT') "
                "AND job_type IN ('execute_purchase','reconcile_action')"
            )
        )


async def test_approval_writes_the_order_message_and_the_order_waits(db):
    from app.execution.jobs import recover_actions

    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        assert (action["status"], action["channel"]) == ("EXECUTING", "assisted")
        order = action["order_message"]
        assert (order["quantity"], order["total_minor"]) == (40, 40000)
        assert order["reference"] in order["text"]["zh"] and "40 件" in order["text"]["zh"]
        assert action["supplier_reply"] is None and action["receipt"] is None
        # The money is held, and nothing retries or polls while the owner waits.
        current = await state(db, seed)
        assert (current["cash_minor"], current["reserved_cash_minor"]) == (100000, 40000)
        await recover_actions(db)
        assert await jobs(db) == 0


async def test_a_confirming_reply_becomes_the_receipt_with_the_suppliers_date(db):
    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        order = action["order_message"]
        promised = date.fromisoformat(order["requested_delivery_date"]) + timedelta(days=1)
        words = f"收到，确认40件，单价10.00元/件，{promised.isoformat()}送到，订单号 SO-7788"
        assert (await reply(client, action, words, role="operator")).status_code == 403
        key = headers("approver")
        first = await reply(client, action, words, headers=key)
        assert first.status_code == 200, first.text
        done = first.json()
        assert (done["status"], done["external_order_id"]) == ("SUCCEEDED", "SO-7788")
        assert done["receipt"]["status"] == "ACCEPTED"
        answer = done["supplier_reply"]
        assert (answer["outcome"], answer["read_by"], answer["text"]) == (
            "confirmed",
            "rules",
            words,
        )
        assert answer["delivery_date"] == promised.isoformat()
        assert answer["quotes"]["quantity"] == "40件" and answer["differences"] == []
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["reserved_cash_minor"],
            current["stocks"][0]["in_transit"],
        ) == (60000, 0, 40)
        async with db.session() as session:
            arrival = await session.scalar(
                text("SELECT expected_arrival_at FROM inbound_items WHERE action_id=:id"),
                {"id": action["id"]},
            )
        assert arrival.date() == promised
        # The same submission replays; a second reply finds nothing waiting.
        assert (await reply(client, action, words, headers=key)).json()["status"] == "SUCCEEDED"
        assert (await reply(client, action, words)).status_code == 409
        assert (await state(db, seed))["cash_minor"] == 60000


async def test_a_reply_that_departs_from_the_order_leaves_it_waiting_and_a_refusal_closes_it(db):
    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        changed = (await reply(client, action, "可以，40件，单价12元/件")).json()
        assert changed["status"] == "EXECUTING"
        assert changed["supplier_reply"]["outcome"] == "needs_attention"
        assert changed["supplier_reply"]["differences"] == [
            {"field": "unit_price_minor", "ordered": 1000, "replied": 1200}
        ]
        vague = (await reply(client, action, "稍等，我问一下仓库")).json()
        assert (vague["status"], vague["supplier_reply"]["decision"]) == ("EXECUTING", "unclear")
        assert (await state(db, seed))["reserved_cash_minor"] == 40000
        refused = (await reply(client, action, "抱歉，这款缺货，供不了")).json()
        assert (refused["status"], refused["last_error"]) == ("FAILED", "SUPPLIER_REJECTED")
        assert refused["supplier_reply"]["outcome"] == "declined"
        current = await state(db, seed)
        assert (current["cash_minor"], current["reserved_cash_minor"]) == (100000, 0)
        assert current["stocks"][0]["in_transit"] == 0


async def test_a_partial_confirmation_is_taken_at_the_suppliers_quantity(db):
    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        path = f"/api/v1/actions/{action['id']}/partial-acceptance"
        # Nothing was offered in part yet.
        assert (await client.post(path, headers=headers("approver"))).status_code == 409
        partial = (await reply(client, action, "可以，但只有30件")).json()
        assert (partial["status"], partial["supplier_reply"]["outcome"]) == ("EXECUTING", "partial")
        assert partial["supplier_reply"]["differences"] == [
            {"field": "quantity", "ordered": 40, "replied": 30}
        ]
        assert (await state(db, seed))["reserved_cash_minor"] == 40000
        assert (await client.post(path, headers=headers("operator"))).status_code == 403
        key = headers("approver")
        taken = await client.post(path, headers=key)
        assert taken.status_code == 200, taken.text
        done = taken.json()
        assert (done["status"], done["receipt"]["quantity"], done["receipt"]["total_minor"]) == (
            "SUCCEEDED",
            30,
            30000,
        )
        # Only what was confirmed is paid and expected; the rest of the hold is released.
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["reserved_cash_minor"],
            current["stocks"][0]["in_transit"],
        ) == (70000, 0, 30)
        # The store stays readable: the inbound row and the ledger carry the accepted 30.
        scope = {"store_id": seed["store_id"]}
        inbound = await client.get("/api/v1/inbounds", params=scope, headers=headers("viewer"))
        assert inbound.status_code == 200, inbound.text
        assert [item["ordered_quantity"] for item in inbound.json()["items"]] == [30]
        ledger = await client.get(
            "/api/v1/ledger-entries",
            params=scope | {"effect_type": "PURCHASE_ACCEPTED"},
            headers=headers("viewer"),
        )
        assert ledger.status_code == 200, ledger.text
        assert [entry["changes"]["cash_delta_minor"] for entry in ledger.json()["items"]] == [
            -30000
        ]
        assert (await client.post(path, headers=key)).json()["status"] == "SUCCEEDED"
        assert (await client.post(path, headers=headers("approver"))).status_code == 409


async def test_an_unanswered_order_can_be_withdrawn(db):
    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        path = f"/api/v1/actions/{action['id']}/withdrawal"
        assert (await client.post(path, headers=headers("operator"))).status_code == 403
        withdrawn = await client.post(path, headers=headers("approver"))
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["status"] == "CANCELLED"
        current = await state(db, seed)
        assert (current["cash_minor"], current["reserved_cash_minor"]) == (100000, 0)
        assert (await client.post(path, headers=headers("approver"))).status_code == 409
        assert (await reply(client, action, "确认40件")).status_code == 409


async def test_goods_of_a_confirmed_order_reach_stock_when_the_owner_records_them(db):
    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        path = f"/api/v1/actions/{action['id']}/arrival"

        async def arrive(body, role="operator", **kwargs):
            return await client.post(path, json=body, headers=kwargs.get("key") or headers(role))

        # Nothing is confirmed yet, so nothing can have arrived.
        assert (await arrive({})).status_code == 409
        assert (await reply(client, action, "收到，确认40件，单价10.00元/件")).status_code == 200
        on_hand = (await state(db, seed))["stocks"][0]["on_hand"]
        assert (await arrive({}, role="viewer")).status_code == 403
        key = headers("operator")
        assert (await arrive({"quantity": 15}, key=key)).status_code == 200
        # The same submission replays; more than is still expected is refused.
        assert (await arrive({"quantity": 15}, key=key)).status_code == 200
        assert (await arrive({"quantity": 26})).status_code == 409
        stock = (await state(db, seed))["stocks"][0]
        assert (stock["on_hand"], stock["in_transit"]) == (on_hand + 15, 25)
        assert (await arrive({})).status_code == 200
        current = await state(db, seed)
        stock = current["stocks"][0]
        assert (stock["on_hand"], stock["in_transit"]) == (on_hand + 40, 0)
        assert current["cash_minor"] == 60000
        assert (await arrive({})).status_code == 409
        scope = {"store_id": seed["store_id"]}
        ledger = await client.get(
            "/api/v1/ledger-entries",
            params=scope | {"effect_type": "GOODS_RECEIVED"},
            headers=headers("viewer"),
        )
        assert ledger.status_code == 200, ledger.text
        assert [
            (entry["action_id"], entry["source_event_id"], entry["changes"]["on_hand_delta"])
            for entry in ledger.json()["items"]
        ] == [(action["id"], None, 25), (action["id"], None, 15)]
        inbound = await client.get("/api/v1/inbounds", params=scope, headers=headers("viewer"))
        assert [item["arrival_status"] for item in inbound.json()["items"]] == ["RECEIVED"]


async def test_next_day_does_not_wait_for_an_order_sent_by_hand(db):
    from app.scheduling.models import Job

    async with environment(db) as (seed, client):
        await sent(db, seed, client)
        response = await client.post(
            f"/dev/v1/scenarios/{seed['scenario_run_id']}/advance",
            json={"steps": 1},
            headers=headers("admin"),
        )
        assert response.status_code == 202, response.text
        async with db.session() as session:
            job = await session.get(Job, response.json()["job_run_id"])
            assert job.payload["skip_empty_delivery"] is True


async def test_an_order_sent_to_the_simulator_takes_no_pasted_reply(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision", json=decision(plan), headers=headers("approver")
        )
        action = await read(client, response.json()["action_id"])
        assert (action["channel"], action["order_message"]) == ("simulator", None)
        assert (await reply(client, action, "确认40件")).status_code == 409
        arrival = await client.post(
            f"/api/v1/actions/{action['id']}/arrival", json={}, headers=headers("operator")
        )
        assert arrival.status_code == 409


async def test_the_work_item_says_the_next_step_of_an_order_sent_by_hand_is_the_owners(db):
    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        opened = await client.post(
            f"/api/v1/missions/{action['mission_id']}/work-item", headers=headers()
        )
        assert opened.status_code == 200, opened.text
        path = f"/api/v1/work-items/{opened.json()['item']['id']}"

        async def business():
            return (await client.get(path, headers=headers())).json()["item"]["business"]

        waiting = await business()
        assert (waiting["code"], waiting["tone"], waiting["needs_attention"]) == (
            "AWAITING_SUPPLIER",
            "amber",
            True,
        )
        assert (await reply(client, action, "收到，确认40件，单价10.00元/件")).status_code == 200
        confirmed = await business()
        assert confirmed["code"] == "IN_TRANSIT" and "登记" in confirmed["detail"]


async def test_a_confirmed_order_sent_by_hand_stays_in_transit_through_its_delivery_day(db):
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    from test_missions import settings

    from app.missions.models import InboundRow
    from app.operations.models import Store
    from app.planning.snapshot import prepare

    zone = ZoneInfo("Asia/Shanghai")
    async with environment(db) as (seed, client):
        action = await sent(db, seed, client)
        assert (await reply(client, action, "收到，确认40件，单价10.00元/件")).status_code == 200
        # Delivery promised for tomorrow at 10:00; the business clock moves on to 16:21 that day,
        # and the owner has not recorded the goods yet.
        day = datetime.fromisoformat(seed["simulation_time"]).astimezone(zone).date()
        day = day.fromordinal(day.toordinal() + 1)
        async with db.session() as session, session.begin():
            inbound = await session.get(InboundRow, (action["id"], "sku_001"))
            inbound.expected_arrival_at = datetime.combine(day, time(10), zone)
            store = await session.get(Store, seed["store_id"])
            store.simulation_time = datetime.combine(day, time(16, 21), zone)
        prepared = await prepare(db, action["mission_id"], settings(db, seed))
        assert prepared.reason is None, prepared.reason
        assert prepared.snapshot.eligible_inbound_qty == 40
        # Once its delivery day is over, the order is late and no longer counted.
        async with db.session() as session, session.begin():
            store = await session.get(Store, seed["store_id"])
            after = day.fromordinal(day.toordinal() + 1)
            store.simulation_time = datetime.combine(after, time(9), zone)
        prepared = await prepare(db, action["mission_id"], settings(db, seed))
        assert prepared.snapshot.eligible_inbound_qty == 0
