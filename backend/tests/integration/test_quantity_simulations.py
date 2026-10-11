"""Real PG and API invariants for independent comparisons and their result history."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_missions import clean_queue, environment, headers  # noqa: F401
from test_operations import state

from app.execution.models import ActionRow
from app.missions.models import MissionRow, PlanRow
from app.operations.models import ForecastRow, LedgerEntry
from app.work_items.models import WorkItem, WorkMessageRow

pytestmark = pytest.mark.integration


def request(**updates):
    return (
        dict(
            expected_state_version=1,
            sku_id="sku_001",
            supplier_id="supplier_001",
            cash_floor_minor=30000,
            candidate_quantities=[0, 20, 40, 80],
        )
        | updates
    )


async def simulate(client, seed, *, body=None, role="operator", key=None):
    response = await client.post(
        f"/api/v1/stores/{seed['store_id']}/simulations",
        json=body or request(),
        headers=headers(role, key),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def fingerprint(db, seed):
    async with db.session() as session:
        counts = [
            await session.scalar(
                select(func.count()).select_from(model).where(model.store_id == seed["store_id"])
            )
            for model in (MissionRow, ActionRow, ForecastRow, LedgerEntry)
        ]
        plans = await session.scalar(
            select(func.count())
            .select_from(PlanRow)
            .join(MissionRow)
            .where(MissionRow.store_id == seed["store_id"])
        )
    return await state(db, seed), counts, plans


async def test_no_mission_comparison_is_durable_exact_and_has_zero_business_effects(db):
    async with environment(db) as (seed, client):
        before = await fingerprint(db, seed)
        key = str(uuid4())
        detail = await simulate(client, seed, key=key)
        item = detail["item"]
        calculation = item["result"]["calculation"]
        assert item["mission_id"] is None
        assert calculation["recommended_candidate_id"] == "candidate_40"
        assert [
            (
                c["quantity"],
                c["spend_minor"],
                c["cash_after_minor"],
                c["shortage_qty"],
                c["feasible"],
            )
            for c in calculation["candidates"]
        ] == [
            (0, 0, 100000, 40, True),
            (20, 20000, 80000, 20, True),
            (40, 40000, 60000, 0, True),
            (80, 80000, 20000, 0, False),
        ]
        assert (await simulate(client, seed, key=key))["item"]["id"] == item["id"]
        assert await fingerprint(db, seed) == before
        restored = (await client.get(f"/api/v1/work-items/{item['id']}", headers=headers())).json()
        assert restored["item"]["result"] == item["result"]
        provenance = item["result"]["provenance"]
        assert provenance["work_version"] == 1
        assert provenance["state_version"] == 1
        assert provenance["source_type"] == "simulation"
        assert provenance["result_id"] == restored["messages"][-1]["id"]
        export = (
            await client.get(
                f"/api/v1/work-items/{item['id']}/results/{provenance['result_id']}",
                headers=headers(),
            )
        ).json()
        assert export["result"] == item["result"]
        assert export["is_latest_result"] and not export["stale_reasons"]


async def test_trial_policy_changes_results_but_does_not_change_official_demand(db):
    async with environment(db) as (seed, client):
        before = await fingerprint(db, seed)
        trial = await simulate(
            client, seed, body=request(cash_floor_minor=75000, remaining_demand=100, horizon_days=7)
        )
        assert trial["item"]["result"]["calculation"]["recommended_candidate_id"] == "candidate_20"
        assert trial["item"]["mission_request"] is None
        assert "用户明确假设" in " ".join(trial["item"]["result"]["assumptions"])
        response = await client.post(
            f"/api/v1/work-items/{trial['item']['id']}/mission",
            json={"expected_version": 1},
            headers=headers(),
        )
        assert response.status_code == 409
        assert await fingerprint(db, seed) == before


async def test_cash_floor_can_leave_no_feasible_candidate_without_fake_recommendation(db):
    async with environment(db) as (seed, client):
        trial = await simulate(client, seed, body=request(cash_floor_minor=100001))
        result = trial["item"]["result"]
        assert result["calculation"]["recommended_candidate_id"] is None
        assert all(not c["feasible"] for c in result["calculation"]["candidates"])
        assert "所有候选均不满足约束" in result["content"]


@pytest.mark.parametrize(
    "updates",
    [
        {"candidate_quantities": [20, 40]},
        {"candidate_quantities": [0, 20, 20]},
        {"candidate_quantities": [0, True]},
        {"candidate_quantities": [0, 1.5]},
        {"candidate_quantities": [0, "20"]},
        {"remaining_demand": 10},
        {"horizon_days": 7},
        {"purchase_delay_seconds": 172800},
        {"cash_floor_minor": -1},
        {"currency": "USD"},
    ],
)
async def test_invalid_or_unsupported_dimensions_are_rejected_before_persistence(db, updates):
    async with environment(db) as (seed, client):
        response = await client.post(
            f"/api/v1/stores/{seed['store_id']}/simulations",
            json=request(**updates),
            headers=headers(),
        )
        assert response.status_code == 422, response.text
        async with db.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(WorkItem)
                    .where(WorkItem.store_id == seed["store_id"])
                )
                == 0
            )


async def test_owner_authorization_rechecked_for_result_and_service_cannot_impersonate_user(db):
    async with environment(db) as (seed, client):
        trial = await simulate(client, seed, role="viewer")
        item = trial["item"]
        path = (
            f"/api/v1/work-items/{item['id']}/results/{item['result']['provenance']['result_id']}"
        )
        assert (await client.get(path, headers=headers("operator"))).status_code == 404
        assert (await client.get(path, headers=headers("viewer"))).status_code == 200
        assert (await client.get(path)).status_code == 401
        assert (
            await client.post(
                f"/api/v1/work-items/{item['id']}/mission",
                json={"expected_version": 1},
                headers=headers("viewer"),
            )
        ).status_code == 403
        assert (
            await client.post(
                "/api/v1/stores/another-store/simulations",
                json=request(),
                headers=headers("viewer"),
            )
        ).status_code == 404


async def test_explicit_conversion_rechecks_then_uses_original_mission_and_plan_path(db):
    from test_planning_jobs import run_check

    async with environment(db) as (seed, client):
        trial = await simulate(client, seed, body=request(cash_floor_minor=75000))
        item = trial["item"]
        path = f"/api/v1/work-items/{item['id']}/mission"
        key = str(uuid4())
        response = await client.post(path, json={"expected_version": 1}, headers=headers(key=key))
        assert response.status_code == 200, response.text
        mission = response.json()["item"]["mission"]
        assert mission["policy"]["cash_floor_minor"] == 75000
        replay = await client.post(path, json={"expected_version": 1}, headers=headers(key=key))
        assert replay.json()["item"]["mission_id"] == mission["id"]
        await run_check(db, seed)
        restored = (await client.get(f"/api/v1/work-items/{item['id']}", headers=headers())).json()[
            "item"
        ]
        assert restored["business"]["code"] == "PENDING_APPROVAL"
        assert restored["business"]["can_confirm"]
        plan = (
            await client.get(f"/api/v1/plans/{restored['business']['plan_id']}", headers=headers())
        ).json()
        assert plan["proposed_purchase"]["quantity"] == 20
        assert (await state(db, seed))["cash_minor"] == 100000


async def test_real_purchase_invalidates_old_trial_without_destroying_its_result(db):
    from test_execution import Supplier, approve, execute, planned

    async with environment(db) as (seed, client):
        trial = await simulate(client, seed)
        item = trial["item"]
        _, plan = await planned(db, seed, client)
        await approve(client, plan)
        supplier = Supplier()
        await execute(db, seed, supplier)
        assert len(supplier.calls) == 1
        assert (await state(db, seed))["cash_minor"] == 60000
        converted = await client.post(
            f"/api/v1/work-items/{item['id']}/mission",
            json={"expected_version": 1},
            headers=headers(),
        )
        assert (
            converted.status_code == 409 and converted.json()["error"]["code"] == "SIMULATION_STALE"
        )
        exported = (
            await client.get(
                f"/api/v1/work-items/{item['id']}/results/{item['result']['provenance']['result_id']}",
                headers=headers(),
            )
        ).json()
        assert "经营状态已变化" in exported["stale_reasons"]
        assert exported["result"] == item["result"]
        before = await fingerprint(db, seed)
        await simulate(
            client,
            seed,
            body=request(expected_state_version=(await state(db, seed))["state_version"]),
        )
        assert await fingerprint(db, seed) == before


async def test_legacy_results_are_exportable_without_invented_source_metadata(db):
    from test_work_items import create

    async with environment(db) as (seed, client):
        detail = await create(client, seed)
        item_id, message_id = detail["item"]["id"], str(uuid4())
        result = {
            "kind": "answer",
            "title": "旧结果",
            "content": "旧正文",
            "columns": [],
            "rows": [],
        }
        async with db.session() as session, session.begin():
            item = await session.get(WorkItem, item_id)
            item.result = result
            session.add(
                WorkMessageRow(
                    id=message_id,
                    item_id=item_id,
                    role="assistant",
                    content="旧正文",
                    demonstration=True,
                    result=result,
                )
            )
        exported = (
            await client.get(
                f"/api/v1/work-items/{item_id}/results/{message_id}", headers=headers()
            )
        ).json()
        assert exported["demonstration"]
        assert exported["result"]["provenance"]["data_as_of"] is None
        assert exported["result"]["provenance"]["work_version"] is None


async def test_recalculate_stays_in_same_work_with_immutable_history_and_version_fence(db):
    async with environment(db) as (seed, client):
        first = (await simulate(client, seed))["item"]
        changed = request(cash_floor_minor=75000, work_item_id=first["id"], expected_work_version=1)
        second = (await simulate(client, seed, body=changed))["item"]
        assert second["id"] == first["id"] and second["version"] == 2
        assert second["result"]["calculation"]["recommended_candidate_id"] == "candidate_20"
        old_path = (
            f"/api/v1/work-items/{first['id']}/results/{first['result']['provenance']['result_id']}"
        )
        old = (await client.get(old_path, headers=headers())).json()
        assert old["result"] == first["result"] and not old["is_latest_result"]
        stale_write = await client.post(
            f"/api/v1/stores/{seed['store_id']}/simulations", json=changed, headers=headers()
        )
        assert stale_write.status_code == 409
        items = (
            await client.get(f"/api/v1/work-items?store_id={seed['store_id']}", headers=headers())
        ).json()["items"]
        assert len(items) == 1
