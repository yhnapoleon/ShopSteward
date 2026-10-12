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
        changed = (await reply(client, action, "可以，但只有30件")).json()
        assert changed["status"] == "EXECUTING"
        assert changed["supplier_reply"]["outcome"] == "needs_attention"
        assert changed["supplier_reply"]["differences"] == [
            {"field": "quantity", "ordered": 40, "replied": 30}
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


async def test_an_order_sent_to_the_simulator_takes_no_pasted_reply(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision", json=decision(plan), headers=headers("approver")
        )
        action = await read(client, response.json()["action_id"])
        assert (action["channel"], action["order_message"]) == ("simulator", None)
        assert (await reply(client, action, "确认40件")).status_code == 409
