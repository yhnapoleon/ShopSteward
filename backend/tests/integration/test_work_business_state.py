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
