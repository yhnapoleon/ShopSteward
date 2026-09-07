import pytest
from test_missions import environment, headers
from test_planning_jobs import clean_jobs, run_check, start  # noqa: F401

pytestmark = pytest.mark.integration


async def prepared(client, db, seed):
    mission = await start(client, seed)
    await run_check(db, seed)
    current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
    plan = (
        await client.get(f"/api/v1/plans/{current['current_plan_id']}", headers=headers())
    ).json()
    return current, plan


async def test_revision_replays_without_spending_and_invalidates_old_approval(db):
    async with environment(db) as (seed, client):
        mission, old = await prepared(client, db, seed)
        url = f"/api/v1/plans/{old['id']}/revision"
        payload = {"expected_mission_version": mission["mission_version"], "max_purchase_qty": 20}
        auth = headers(key="revision-once")
        result = await client.post(url, json=payload, headers=auth)
        assert result.status_code == 200, result.text
        plan = result.json()
        assert plan["proposed_purchase"]["quantity"] == 20
        assert plan["input_snapshot"]["state"]["cash_minor"] == 100000
        assert (await client.post(url, json=payload, headers=auth)).json() == plan
        state = (
            await client.get(
                "/api/v1/dashboard", params={"store_id": seed["store_id"]}, headers=headers()
            )
        ).json()
        assert state["state"]["cash_minor"] == 100000
        assert state["state"]["stocks"][0]["in_transit"] == 0
        approve = await client.post(
            f"/api/v1/plans/{old['id']}/decision",
            headers=headers("approver"),
            json={
                "decision": "approve",
                "expected_plan_version": old["plan_version"],
                "expected_state_version": old["state_version"],
                "proposal_hash": old["proposal_hash"],
            },
        )
        assert approve.status_code == 409
        assert (
            await client.post(url, json={**payload, "max_purchase_qty": 40}, headers=auth)
        ).status_code == 409


async def test_revision_requires_operator_and_current_mission_version(db):
    async with environment(db) as (seed, client):
        mission, old = await prepared(client, db, seed)
        url = f"/api/v1/plans/{old['id']}/revision"
        payload = {"expected_mission_version": mission["mission_version"], "max_purchase_qty": 20}
        assert (await client.post(url, json=payload, headers=headers("viewer"))).status_code == 403
        assert (
            await client.post(
                url, json={**payload, "expected_mission_version": 99}, headers=headers()
            )
        ).status_code == 409
        first = (await client.post(url, json=payload, headers=headers())).json()
        current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        reset = await client.post(
            f"/api/v1/plans/{first['id']}/revision",
            headers=headers(),
            json={
                "expected_mission_version": current["mission_version"],
                "max_purchase_qty": None,
            },
        )
        assert reset.status_code == 200
        assert reset.json()["proposed_purchase"]["quantity"] == 40
