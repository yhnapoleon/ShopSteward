"""Cards follow actual plans/actions, including paused and unresolved work."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from test_execution import Supplier, approve, execute, planned
from test_missions import clean_queue, environment, headers  # noqa: F401

from app.execution.models import ActionRow
from app.missions.models import MissionRow, PlanRow

pytestmark = pytest.mark.integration


async def open_work(client, mission):
    response = await client.post(f"/api/v1/missions/{mission['id']}/work-item", headers=headers())
    assert response.status_code == 200, response.text
    return response.json()["item"]


async def read(client, item):
    detail = (await client.get(f"/api/v1/work-items/{item['id']}", headers=headers())).json()[
        "item"
    ]
    listing = (
        await client.get(f"/api/v1/work-items?store_id={item['store_id']}", headers=headers())
    ).json()
    card = next(i for i in listing["items"] if i["id"] == item["id"])
    assert card["business"]["code"] == detail["business"]["code"]
    assert card["business"]["plan_version"] == detail["business"]["plan_version"]
    return detail["business"]


async def test_pending_queued_unknown_paused_and_received_states_are_business_driven(db):
    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        item = await open_work(client, mission)
        assert (await read(client, item))["code"] == "PENDING_APPROVAL"
        assert (await read(client, item))["can_confirm"]
        approved = await approve(client, plan)
        assert (await read(client, item))["code"] == "QUEUED"
        async with db.session() as s, s.begin():
            action = await s.get(ActionRow, approved["action_id"])
            action.status = "UNKNOWN"
            m = await s.get(MissionRow, mission["id"])
            m.status = "PAUSED"
        state = await read(client, item)
        assert state["code"] == "UNKNOWN" and state["priority"] == 0
        assert not state["can_confirm"]
        # Restore the controlled queue action for the real receipt/accounting path.
        async with db.session() as s, s.begin():
            action = await s.get(ActionRow, approved["action_id"])
            action.status = "QUEUED"
            m = await s.get(MissionRow, mission["id"])
            m.status = "ACTIVE"
        await execute(db, seed, Supplier())
        assert (await read(client, item))["code"] == "IN_TRANSIT"
        async with db.session() as s, s.begin():
            m = await s.get(MissionRow, mission["id"])
            m.status = "PAUSED"
        assert (await read(client, item))["code"] == "PAUSED"


async def test_expiry_without_a_work_version_change_removes_confirmation(db):
    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        item = await open_work(client, mission)
        assert (await read(client, item))["can_confirm"]
        async with db.session() as session, session.begin():
            p = await session.get(PlanRow, plan["id"])
            p.expires_at = await session.scalar(select(func.clock_timestamp())) - timedelta(
                seconds=1
            )
        current = await read(client, item)
        assert current["code"] == "PLAN_STALE" and not current["can_confirm"]
        detail = (await client.get(f"/api/v1/work-items/{item['id']}", headers=headers())).json()
        assert detail["item"]["version"] == item["version"]


async def test_an_emergency_plan_awaiting_confirmation_reads_like_any_pending_plan(db):
    from test_operations_cases import adopted_case

    from app.operations.models import Store

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        item = await open_work(client, {"id": case["mission_id"]})
        state = await read(client, item)
        assert (state["code"], state["plan_id"]) == ("PENDING_APPROVAL", plan["id"])
        assert state["can_confirm"]
        sent = await client.post(
            f"/api/v1/work-items/{item['id']}/messages",
            json={"content": "这份应急方案先别动"},
            headers=headers(),
        )
        assert sent.status_code == 200, sent.text
        # Its own inputs decide when it can no longer be confirmed, as approval checks them.
        async with db.session() as session, session.begin():
            store = await session.get(Store, case["store_id"])
            store.state_version += 1
        state = await read(client, item)
        assert state["code"] == "PLAN_STALE" and not state["can_confirm"]


async def test_an_order_sent_by_hand_with_no_reply_past_its_date_is_overdue(db):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from test_execution import decision

    from app.operations.models import Store

    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision",
            json=decision(plan) | {"channel": "assisted"},
            headers=headers("approver"),
        )
        assert response.status_code == 202, response.text
        await execute(db, seed, Supplier())
        item = await open_work(client, mission)
        assert (await read(client, item))["code"] == "AWAITING_SUPPLIER"
        async with db.session() as session, session.begin():
            action = await session.get(ActionRow, response.json()["action_id"])
            wanted = datetime.fromisoformat(action.purchase_snapshot["expected_arrival_at"])
        # A delivery day is promised, not an hour: past the time on that day it still waits.
        local = wanted.astimezone(ZoneInfo("Asia/Shanghai"))
        for moment, code in (
            (local.replace(hour=23, minute=59), "AWAITING_SUPPLIER"),
            (local.replace(hour=0, minute=0) + timedelta(days=1), "SUPPLIER_OVERDUE"),
        ):
            async with db.session() as session, session.begin():
                store = await session.get(Store, mission["store_id"])
                store.simulation_time = moment
            assert (await read(client, item))["code"] == code
        state = await read(client, item)
        assert (state["code"], state["needs_attention"]) == ("SUPPLIER_OVERDUE", True)
