from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from test_missions import clean_queue, environment, headers, settings  # noqa: F401
from test_planning_jobs import run_check, start

pytestmark = pytest.mark.integration


async def recovery_case(db, seed, client, *, daily=True):
    from app.missions.models import InboundRow, MissionRow
    from app.operations.models import OfferRow, StockRow, Store

    mission = await start(client, seed)
    clock = datetime.fromisoformat(seed["simulation_time"])
    async with db.session() as session, session.begin():
        store = await session.get(Store, seed["store_id"])
        store.cash_minor = 80000
        row = await session.get(MissionRow, mission["id"])
        row.policy = row.policy | {"cash_floor_minor": 50000}
        stock = await session.get(StockRow, (store.id, "sku_001"))
        stock.on_hand, stock.in_transit = 20, 50
        original = await session.get(OfferRow, (store.id, "sku_001", "supplier_001"))
        original.document = original.document | {
            "unit_price_minor": 900,
            "minimum_order_quantity": 40,
            "pack_size": 10,
            "lead_time_seconds": 172800,
        }
        for supplier, price, days in [("B", 1200, 2), ("C", 800, 4)]:
            session.add(
                OfferRow(
                    store_id=store.id,
                    sku_id="sku_001",
                    supplier_id=supplier,
                    document=original.document
                    | {
                        "supplier_id": supplier,
                        "unit_price_minor": price,
                        "minimum_order_quantity": 20,
                        "lead_time_seconds": days * 86400,
                    },
                )
            )
        session.add(
            InboundRow(
                action_id="original-" + store.id,
                store_id=store.id,
                sku_id="sku_001",
                ordered_qty=50,
                received_qty=0,
                expected_arrival_at=clock + timedelta(days=4),
            )
        )
    body = {
        "mission_id": mission["id"],
        "objective": "七天少缺货，保留原订单",
        "budget_minor": 30000,
    }
    if daily:
        body["daily_demand"] = [
            {"settlement_at": (clock + timedelta(days=i, hours=23)).isoformat(), "demand_qty": 10}
            for i in range(7)
        ]
    response = await client.post("/api/v1/operations-cases", json=body, headers=headers())
    assert response.status_code == 201, response.text
    return response.json()


async def analyze(client, case):
    response = await client.post(
        f"/api/v1/operations-cases/{case['id']}/analyze",
        json={"expected_revision": case["current_revision"]},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    return response.json()


def adopt_body(case):
    proposal = case["proposal"]
    return {
        "expected_revision": case["current_revision"],
        "proposal_id": proposal["id"],
        "candidate_id": proposal["recommended_candidate_id"],
        "expected_mission_version": case["current_mission_version"],
        "expected_state_version": case["current_state_version"],
        "expected_current_plan_id": case["current_plan_id"],
        "proposal_hash": proposal["proposal_hash"],
    }


async def test_case_recovery_real_sources_materialize_approve_send_and_receipt(db):
    from test_execution import Supplier, approve, execute

    from app.execution.models import ActionRow
    from app.missions.models import MissionRow

    async with environment(db) as (seed, client):
        case = await analyze(client, await recovery_case(db, seed, client))
        assert case["status"] == "OPTIONS_READY"
        chosen = next(
            c
            for c in case["proposal"]["candidates"]
            if c["id"] == case["proposal"]["recommended_candidate_id"]
        )
        assert (chosen["supplier_id"], chosen["quantity"], chosen["lost_qty"]) == ("B", 20, 0)
        h = headers()
        path = f"/api/v1/operations-cases/{case['id']}/materialize"
        body = adopt_body(case)
        result = await client.post(path, json=body, headers=h)
        assert result.status_code == 200, result.text
        adopted = result.json()
        assert (await client.post(path, json=body, headers=h)).json() == adopted
        plan = (await client.get(f"/api/v1/plans/{adopted['plan_id']}", headers=headers())).json()
        assert plan["plan_kind"] == "recovery_v1"
        assert plan["proposed_purchase"]["total_minor"] == 24000
        async with db.session() as session:
            assert not list(
                await session.scalars(select(ActionRow).where(ActionRow.plan_id == plan["id"]))
            )
        # Ordinary periodic planning cannot overwrite the adopted recovery intent.
        await run_check(db, seed)
        current = (
            await client.get(f"/api/v1/missions/{case['mission_id']}", headers=headers())
        ).json()
        assert current["current_plan_id"] == plan["id"]
        await approve(client, plan)
        await execute(db, seed, Supplier())
        status = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        assert status["execution_status"] == "ACCEPTED"
        async with db.session() as session:
            mission = await session.get(MissionRow, case["mission_id"])
            assert mission.policy["supplier_id"] == "supplier_001"
            assert mission.planning_context is None


async def test_revision_stales_adoption_and_case_owner_is_required(db):
    async with environment(db) as (seed, client):
        case = await analyze(client, await recovery_case(db, seed, client))
        assert (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers("viewer"))
        ).status_code == 404
        response = await client.post(
            f"/api/v1/operations-cases/{case['id']}/revise",
            json={"expected_revision": 1, "budget_minor": 20000},
            headers=headers(),
        )
        assert response.status_code == 200, response.text
        revised = await analyze(client, response.json())
        assert revised["proposal"]["recommended_candidate_id"] == "wait"
        stale = await client.post(
            f"/api/v1/operations-cases/{case['id']}/materialize",
            json=adopt_body(case),
            headers=headers(),
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "CASE_REVISION_CONFLICT"


async def test_missing_daily_evidence_is_not_uniformly_invented(db):
    async with environment(db) as (seed, client):
        case = await analyze(client, await recovery_case(db, seed, client, daily=False))
        assert case["status"] == "NEEDS_INPUT" and case["proposal"] is None
        assert "DAILY_DEMAND_REQUIRED" in case["missing_inputs"]


async def adopted_case(db, seed, client):
    case = await analyze(client, await recovery_case(db, seed, client))
    result = await client.post(
        f"/api/v1/operations-cases/{case['id']}/materialize",
        json=adopt_body(case),
        headers=headers(),
    )
    assert result.status_code == 200, result.text
    case = result.json()
    plan = (await client.get(f"/api/v1/plans/{case['plan_id']}", headers=headers())).json()
    return case, plan


async def test_recovery_rechecks_supplier_offer_before_approval(db):
    from test_execution import decision

    from app.operations.models import OfferRow

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        async with db.session() as session, session.begin():
            offer = await session.get(OfferRow, (case["store_id"], case["sku_id"], "B"))
            offer.document = offer.document | {"offer_version": "changed", "unit_price_minor": 1250}
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision", json=decision(plan), headers=headers("approver")
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "OFFER_VERSION_CONFLICT"


async def test_queued_recovery_is_stale_after_user_revision_and_never_sent(db):
    from test_execution import Supplier, approve, execute

    from app.execution.models import ActionRow

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        accepted = await approve(client, plan)
        revised = await client.post(
            f"/api/v1/operations-cases/{case['id']}/revise",
            json={"expected_revision": 1, "budget_minor": 20000},
            headers=headers(),
        )
        assert revised.status_code == 200
        supplier = Supplier()
        await execute(db, seed, supplier)
        async with db.session() as session:
            action = await session.get(ActionRow, accepted["action_id"])
            assert action.status == "STALE" and action.last_error == "CASE_REVISION_CONFLICT"
        assert supplier.receipts == {}


async def test_unknown_receipt_retains_original_action_and_no_second_purchase(db):
    from test_execution import Supplier, approve, execute

    from app.execution.models import ActionRow
    from app.missions.models import MissionRow

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        supplier.drop_response = True
        await execute(db, seed, supplier)
        current = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        assert current["execution_status"] == "UNKNOWN"
        response = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "refresh"},
            headers=headers(),
        )
        current = await analyze(client, response.json())
        assert all(not c["executable"] for c in current["proposal"]["candidates"])
        async with db.session() as session:
            mission = await session.get(MissionRow, case["mission_id"])
            assert mission.current_action_id == accepted["action_id"]
            assert mission.planning_context["plan_id"] == plan["id"]
            actions = list(
                await session.scalars(select(ActionRow).where(ActionRow.mission_id == mission.id))
            )
            assert len(actions) == 1
        # End this test's fake unresolved supplier; the global orphan scanner is real.
        async with db.session() as session, session.begin():
            from app.execution.accounting import close_action
            from app.execution.repository import lock_action

            store, mission, _, action = await lock_action(session, accepted["action_id"])
            await close_action(session, store, mission, action, "CANCELLED", reason="TEST_CLEANUP")


async def test_partial_actual_receipt_displays_remaining_quantity_without_claiming_goal(db):
    from test_execution import Supplier, approve, execute
    from test_operations import event, ingest

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        accepted = await approve(client, plan)
        await execute(db, seed, Supplier())
        await ingest(
            db,
            seed,
            [event(seed, 1, "GOODS_RECEIVED", action_id=accepted["action_id"], quantity=10)],
        )
        current = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        assert current["execution_status"] == "PARTIALLY_RECEIVED"
        assert current["status"] == "MONITORING"


async def test_a_cap_on_the_daily_plan_is_not_carried_into_an_emergency_restock(db):
    from app.missions.models import MissionRow

    async with environment(db) as (seed, client):
        case = await recovery_case(db, seed, client)
        # "Limit it to N" on the daily plan is written to the Mission's task constraints.
        async with db.session() as session, session.begin():
            mission = await session.get(MissionRow, case["mission_id"])
            mission.task_constraints = {"max_purchase_qty": 0}
        case = await analyze(client, case)
        assert case["max_purchase_qty"] is None
        assert case["proposal"]["recommended_candidate_id"] != "wait"
        assert any(c["executable"] and c["quantity"] > 0 for c in case["proposal"]["candidates"])


async def test_adopting_waiting_supersedes_unapproved_recovery_but_not_mission(db):
    from app.missions.models import MissionRow, PlanRow

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        result = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "adopt_waiting"},
            headers=headers(),
        )
        assert result.status_code == 200, result.text
        async with db.session() as session:
            old = await session.get(PlanRow, plan["id"])
            mission = await session.get(MissionRow, case["mission_id"])
            assert old.status == "SUPERSEDED"
            assert mission.current_plan_id is None and mission.planning_context is None
            assert mission.status == "ACTIVE"


async def test_opt_in_followup_is_durable_deduplicated_and_stops_when_disabled(db):
    from sqlalchemy import func

    from app.operations.models import Store
    from app.operations_cases.models import CaseEventRow
    from app.scheduling.models import Job

    async with environment(db) as (seed, client):
        case = await analyze(client, await recovery_case(db, seed, client))
        path = f"/api/v1/operations-cases/{case['id']}/control"
        enabled = await client.post(
            path, json={"expected_revision": 1, "operation": "enable_followup"}, headers=headers()
        )
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["followup_enabled"] is True
        from app.operations_cases.jobs import make_handlers
        from app.scheduling.runner import Runner

        runner = Runner(db, settings(db, seed), handlers=make_handlers(settings(db, seed)))
        assert await runner.run_once()
        async with db.session() as session, session.begin():
            observed = await session.scalar(
                select(func.count())
                .select_from(CaseEventRow)
                .where(CaseEventRow.case_id == case["id"], CaseEventRow.kind == "FOLLOWUP_OBSERVED")
            )
            assert observed == 1
            pending = await session.scalar(
                select(Job).where(
                    Job.job_type == "operations_case_followup",
                    Job.payload["case_id"].astext == case["id"],
                    Job.status == "READY",
                )
            )
            assert pending is not None
            pending.available_at = await session.scalar(select(func.clock_timestamp()))
        assert await runner.run_once()
        async with db.session() as session, session.begin():
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CaseEventRow)
                    .where(
                        CaseEventRow.case_id == case["id"], CaseEventRow.kind == "FOLLOWUP_OBSERVED"
                    )
                )
                == 1
            )
            store = await session.get(Store, case["store_id"])
            store.state_version += 1
            pending = await session.scalar(
                select(Job).where(
                    Job.job_type == "operations_case_followup",
                    Job.payload["case_id"].astext == case["id"],
                    Job.status == "READY",
                )
            )
            pending.available_at = await session.scalar(select(func.clock_timestamp()))
        assert await runner.run_once()
        current = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        assert current["status"] == "RECHECK_REQUIRED"
        disabled = await client.post(
            path, json={"expected_revision": 1, "operation": "disable_followup"}, headers=headers()
        )
        assert disabled.status_code == 200 and disabled.json()["followup_enabled"] is False
        assert not await runner.run_once()


async def test_fresh_revision_after_accepted_purchase_uses_new_source_snapshot(db):
    from test_execution import Supplier, approve, execute

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        await approve(client, plan)
        await execute(db, seed, Supplier())
        revised = await client.post(
            f"/api/v1/operations-cases/{case['id']}/revise",
            json={"expected_revision": 1, "budget_minor": 0},
            headers=headers(),
        )
        current = await analyze(client, revised.json())
        assert current["proposal"]["revision"] == 2
        assert current["stale"] is False
        assert current["execution_status"] == "ACCEPTED"


async def test_followup_recovers_lost_job_and_closes_unknown_after_goal_window(db):
    from sqlalchemy import func

    from app.operations.models import Store
    from app.operations_cases.jobs import make_handlers
    from app.operations_cases.models import CaseEventRow
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        case = await analyze(client, await recovery_case(db, seed, client))
        await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "enable_followup"},
            headers=headers(),
        )
        async with db.session() as session, session.begin():
            job = await session.scalar(
                select(Job).where(
                    Job.job_type == "operations_case_followup",
                    Job.payload["case_id"].astext == case["id"],
                    Job.status == "READY",
                )
            )
            job.status = "FAILED"
            store = await session.get(Store, case["store_id"])
            store.simulation_time += timedelta(days=8)
            store.state_version += 1
        runner = Runner(db, settings(db, seed), handlers=make_handlers(settings(db, seed)))
        assert await runner.run_once()
        current = (
            await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())
        ).json()
        assert current["status"] == "CLOSED" and current["followup_enabled"] is False
        async with db.session() as session:
            closed = await session.scalar(
                select(CaseEventRow).where(
                    CaseEventRow.case_id == case["id"], CaseEventRow.kind == "CASE_CLOSED"
                )
            )
            assert closed.payload["outcome"] == "unknown"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(
                        Job.job_type == "operations_case_followup",
                        Job.payload["case_id"].astext == case["id"],
                        Job.status.in_(["READY", "RUNNING", "RETRY_WAIT"]),
                    )
                )
                == 0
            )


async def test_selected_supplier_is_preserved_when_candidates_have_same_quantity(db):
    from test_execution import Supplier, approve, execute

    async with environment(db) as (seed, client):
        case = await analyze(client, await recovery_case(db, seed, client))
        payload = adopt_body(case) | {"candidate_id": "C_20"}
        response = await client.post(
            f"/api/v1/operations-cases/{case['id']}/materialize", json=payload, headers=headers()
        )
        assert response.status_code == 200, response.text
        current = response.json()
        assert current["plan_revision"] == 1 and current["plan_status"] == "PENDING_APPROVAL"
        plan = (await client.get(f"/api/v1/plans/{current['plan_id']}", headers=headers())).json()
        assert (
            plan["recommended_candidate_id"] == "B_20" and plan["selected_candidate_id"] == "C_20"
        )
        await approve(client, plan)
        supplier = Supplier()
        await execute(db, seed, supplier)
        assert supplier.calls[0][1]["supplier_id"] == "C"
        assert supplier.calls[0][1]["expected_total_minor"] == 16000


async def test_one_accepted_emergency_purchase_per_case_even_after_revision(db):
    from test_execution import Supplier, approve, execute

    from app.operations.models import Store

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        await approve(client, plan)
        await execute(db, seed, Supplier())
        async with db.session() as session, session.begin():
            store = await session.get(Store, case["store_id"])
            store.cash_minor = 120000
            store.state_version += 1
        revised = await client.post(
            f"/api/v1/operations-cases/{case['id']}/revise",
            json={"expected_revision": 1, "budget_minor": 30000},
            headers=headers(),
        )
        current = await analyze(client, revised.json())
        assert current["plan_revision"] == 1 and current["current_revision"] == 2
        assert current["plan_status"] == "APPROVED"
        for candidate in current["proposal"]["candidates"]:
            if candidate["quantity"]:
                assert not candidate["executable"]
                assert "EMERGENCY_PURCHASE_ALREADY_ACCEPTED" in candidate["rejection_reasons"]


async def case_view(client, case):
    return (await client.get(f"/api/v1/operations-cases/{case['id']}", headers=headers())).json()


async def check_again(db, seed, client, case):
    await client.post(f"/api/v1/missions/{case['mission_id']}/checks", json={}, headers=headers())
    await run_check(db, seed)


async def current_plan(client, case):
    path = f"/api/v1/missions/{case['mission_id']}"
    return (await client.get(path, headers=headers())).json()["current_plan_id"]


async def timeline_types(client, case):
    response = await client.get(
        f"/api/v1/missions/{case['mission_id']}/timeline",
        params={"limit": 100},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    return [entry["type"] for entry in response.json()["items"]]


async def test_adopted_plan_waits_its_own_window_counted_from_adoption(db):
    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        proposal = (await case_view(client, case))["proposal"]
        window = datetime.fromisoformat(plan["expires_at"]) - datetime.fromisoformat(
            proposal["created_at"]
        )
        assert window >= timedelta(seconds=settings(db, seed).recovery_ttl_seconds)
        assert proposal["expires_at"] < plan["expires_at"]


async def test_case_resolves_with_its_outcome_once_the_emergency_goods_arrive(db):
    from test_execution import Supplier, approve, execute
    from test_operations import event, ingest

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        candidates = {c["id"]: c for c in plan["candidates"]}
        accepted = await approve(client, plan)
        await execute(db, seed, Supplier())
        current = await case_view(client, case)
        assert (current["status"], current["stale"]) == ("MONITORING", False)
        assert current["purchases"] == [
            {
                "action_id": accepted["action_id"],
                "supplier_id": "B",
                "status": "SUCCEEDED",
                "planned_qty": 20,
                "accepted_qty": 20,
                "received_qty": 0,
            }
        ]
        await ingest(
            db,
            seed,
            [event(seed, 1, "GOODS_RECEIVED", action_id=accepted["action_id"], quantity=20)],
        )
        current = await case_view(client, case)
        assert current["status"] == "RESOLVED" and current["routine_paused"] is False
        assert current["outcome"] == {
            "path": "purchase",
            "planned_qty": 20,
            "purchased_qty": 20,
            "received_qty": 20,
            "spend_minor": 24000,
            "lost_qty_before": candidates["wait"]["lost_qty"],
            "lost_qty_after": candidates["B_20"]["lost_qty"],
            "action_ids": [accepted["action_id"]],
            "purchases": [
                {
                    "action_id": accepted["action_id"],
                    "supplier_id": "B",
                    "planned_qty": 20,
                    "purchased_qty": 20,
                    "received_qty": 20,
                    "spend_minor": 24000,
                }
            ],
        }
        assert candidates["wait"]["lost_qty"] > candidates["B_20"]["lost_qty"]
        assert "CASE_RESOLVED" in await timeline_types(client, case)


async def test_followup_leaves_a_case_whose_purchase_was_accepted_monitoring(db):
    from test_execution import Supplier, approve, execute

    from app.operations_cases.jobs import make_handlers
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        enabled = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "enable_followup"},
            headers=headers(),
        )
        assert enabled.status_code == 200, enabled.text
        await approve(client, plan)
        await execute(db, seed, Supplier())
        runner = Runner(db, settings(db, seed), handlers=make_handlers(settings(db, seed)))
        assert await runner.run_once()
        # Its own purchase moved cash and stock on; that is the decision, not a new question.
        current = await case_view(client, case)
        assert (current["status"], current["stale"]) == ("MONITORING", False)
        assert current["recheck_reason"] is None


async def test_routine_check_keeps_an_outdated_emergency_plan_out_and_says_why(db):
    from app.missions.models import PlanRow
    from app.operations.models import Store

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        async with db.session() as session, session.begin():
            store = await session.get(Store, case["store_id"])
            store.state_version += 1
        await run_check(db, seed)
        assert await current_plan(client, case) is None
        async with db.session() as session:
            assert (await session.get(PlanRow, plan["id"])).status == "SUPERSEDED"
        current = await case_view(client, case)
        assert current["status"] == "RECHECK_REQUIRED"
        assert current["recheck_reason"] == "BUSINESS_STATE_CHANGED"
        assert current["routine_paused"] is True
        assert "CASE_RECHECK_REQUIRED" in await timeline_types(client, case)
        # Later checks keep leaving the item to the case.
        await check_again(db, seed, client, case)
        assert await current_plan(client, case) is None


async def test_an_emergency_case_holds_routine_advice_from_its_start_until_it_ends(db):
    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        routine = await current_plan(client, {"mission_id": mission["id"]})
        assert routine is not None
        response = await client.post(
            "/api/v1/operations-cases",
            json={
                "mission_id": mission["id"],
                "objective": "缺的找别家补上",
                "budget_minor": 30000,
            },
            headers=headers(),
        )
        assert response.status_code == 201, response.text
        case = response.json()
        # From its start, before any option is chosen, the case holds the item.
        assert (case["routine_paused"], case["current_plan_id"]) == (True, None)
        plan = await client.get(f"/api/v1/plans/{routine}", headers=headers())
        assert plan.json()["status"] == "SUPERSEDED"
        await check_again(db, seed, client, case)
        assert await current_plan(client, case) is None
        ended = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "cancel"},
            headers=headers(),
        )
        assert ended.status_code == 200, ended.text
        assert ended.json()["routine_paused"] is False
        await check_again(db, seed, client, case)
        assert await current_plan(client, case) is not None


async def test_waiting_holds_routine_orders_until_the_case_ends(db):
    async with environment(db) as (seed, client):
        case = await analyze(client, await recovery_case(db, seed, client))
        # The open case already holds the item: the Mission's first check gives no advice.
        await run_check(db, seed)
        assert await current_plan(client, case) is None
        path = f"/api/v1/operations-cases/{case['id']}/control"
        waited = await client.post(
            path, json={"expected_revision": 1, "operation": "adopt_waiting"}, headers=headers()
        )
        assert waited.status_code == 200, waited.text
        assert waited.json()["routine_paused"] is True
        assert await current_plan(client, case) is None
        await check_again(db, seed, client, case)
        assert await current_plan(client, case) is None
        assert "CASE_DECISION" in await timeline_types(client, case)
        ended = await client.post(
            path, json={"expected_revision": 1, "operation": "cancel"}, headers=headers()
        )
        assert ended.status_code == 200, ended.text
        await run_check(db, seed)
        assert await current_plan(client, case) is not None


async def test_rejected_emergency_plan_is_not_replaced_by_a_routine_order(db):
    from test_execution import decision

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision",
            json=decision(plan, "reject"),
            headers=headers("approver"),
        )
        assert response.status_code == 200, response.text
        await check_again(db, seed, client, case)
        assert await current_plan(client, case) == plan["id"]
        current = await case_view(client, case)
        assert (current["status"], current["plan_status"]) == ("OPTIONS_READY", "REJECTED")
        assert current["routine_paused"] is True


async def test_part_of_an_emergency_order_can_be_taken_and_the_rest_bought_elsewhere(db):
    from test_execution import Supplier, decision, execute

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision",
            json=decision(plan) | {"channel": "assisted"},
            headers=headers("approver"),
        )
        assert response.status_code == 202, response.text
        action_id = response.json()["action_id"]
        await execute(db, seed, Supplier())
        replied = await client.post(
            f"/api/v1/actions/{action_id}/supplier-reply",
            json={"text": "可以，但只有10件"},
            headers=headers("approver"),
        )
        assert replied.json()["supplier_reply"]["outcome"] == "partial", replied.text
        taken = await client.post(
            f"/api/v1/actions/{action_id}/partial-acceptance", headers=headers("approver")
        )
        assert taken.status_code == 200, taken.text
        current = await case_view(client, case)
        assert current["status"] == "MONITORING"
        assert [(p["planned_qty"], p["accepted_qty"]) for p in current["purchases"]] == [(20, 10)]
        refreshed = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "refresh"},
            headers=headers(),
        )
        current = await analyze(client, refreshed.json())
        topups = [c for c in current["proposal"]["candidates"] if c["executable"]]
        assert topups
        assert all(
            "EMERGENCY_PURCHASE_ALREADY_ACCEPTED" not in c["rejection_reasons"]
            for c in current["proposal"]["candidates"]
        )
        adopted = await client.post(
            f"/api/v1/operations-cases/{case['id']}/materialize",
            json=adopt_body(current) | {"candidate_id": topups[0]["id"]},
            headers=headers(),
        )
        assert adopted.status_code == 200, adopted.text


async def test_routine_check_settles_a_case_whose_goods_arrived_before_it_could(db):
    from test_execution import Supplier, approve, execute

    from app.missions.models import InboundRow
    from app.operations.models import StockRow

    async with environment(db) as (seed, client):
        case, plan = await adopted_case(db, seed, client)
        accepted = await approve(client, plan)
        await execute(db, seed, Supplier())
        # Goods recorded before cases settled themselves: full inbound, case still following.
        async with db.session() as session, session.begin():
            inbound = await session.get(InboundRow, (accepted["action_id"], case["sku_id"]))
            stock = await session.get(StockRow, (case["store_id"], case["sku_id"]))
            stock.in_transit -= inbound.ordered_qty
            stock.on_hand += inbound.ordered_qty
            inbound.received_qty = inbound.ordered_qty
        await check_again(db, seed, client, case)
        assert (await case_view(client, case))["status"] == "RESOLVED"
        assert await current_plan(client, case) not in (None, plan["id"])


async def timeline_said(client, case, kind):
    response = await client.get(
        f"/api/v1/missions/{case['mission_id']}/timeline",
        params={"limit": 100},
        headers=headers(),
    )
    return [entry["summary"] for entry in response.json()["items"] if entry["type"] == kind]


async def sent_by_hand(db, seed, client, reply):
    """The adopted plan approved as an order the owner sends; the supplier's reply pasted back."""
    from test_execution import Supplier, decision, execute

    case, plan = await adopted_case(db, seed, client)
    response = await client.post(
        f"/api/v1/plans/{plan['id']}/decision",
        json=decision(plan) | {"channel": "assisted"},
        headers=headers("approver"),
    )
    assert response.status_code == 202, response.text
    action_id = response.json()["action_id"]
    await execute(db, seed, Supplier())
    replied = await client.post(
        f"/api/v1/actions/{action_id}/supplier-reply",
        json={"text": reply},
        headers=headers("approver"),
    )
    assert replied.status_code == 200, replied.text
    return case, action_id, replied.json()["supplier_reply"]["outcome"]


async def taken_in_part(db, seed, client):
    """B confirms 10 of the 20 ordered; the owner takes them and records them arriving."""
    case, action_id, outcome = await sent_by_hand(db, seed, client, "可以，但只有10件")
    assert outcome == "partial"
    taken = await client.post(
        f"/api/v1/actions/{action_id}/partial-acceptance", headers=headers("approver")
    )
    assert taken.status_code == 200, taken.text
    arrived = await client.post(f"/api/v1/actions/{action_id}/arrival", json={}, headers=headers())
    assert arrived.status_code == 200, arrived.text
    return case


async def test_goods_of_a_part_filled_order_leave_the_case_open_until_the_rest_is_decided(db):
    from test_execution import Supplier, approve, execute
    from test_operations import event, ingest

    async with environment(db) as (seed, client):
        case = await taken_in_part(db, seed, client)
        current = await case_view(client, case)
        # Everything bought is in, yet the rest may still be bought: nothing settles.
        assert (current["status"], current["outcome"]) == ("MONITORING", None)
        assert current["excluded_supplier_ids"] == ["B"]
        refreshed = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "refresh"},
            headers=headers(),
        )
        options = await analyze(client, refreshed.json())
        assert "B" not in {c["supplier_id"] for c in options["proposal"]["candidates"]}
        rest = next(
            c for c in options["proposal"]["candidates"] if c["executable"] and c["quantity"]
        )
        adopted = await client.post(
            f"/api/v1/operations-cases/{case['id']}/materialize",
            json=adopt_body(options) | {"candidate_id": rest["id"]},
            headers=headers(),
        )
        assert adopted.status_code == 200, adopted.text
        plan = (
            await client.get(f"/api/v1/plans/{adopted.json()['plan_id']}", headers=headers())
        ).json()
        second = await approve(client, plan)
        await execute(db, seed, Supplier())
        received = event(
            seed, 1, "GOODS_RECEIVED", action_id=second["action_id"], quantity=rest["quantity"]
        )
        await ingest(db, seed, [received])
        current = await case_view(client, case)
        assert current["status"] == "RESOLVED"
        each = current["outcome"]["purchases"]
        assert [(p["supplier_id"], p["planned_qty"], p["purchased_qty"]) for p in each] == [
            ("B", 20, 10),
            (rest["supplier_id"], rest["quantity"], rest["quantity"]),
        ]
        total = 10 + rest["quantity"]
        assert current["outcome"]["purchased_qty"] == total
        said = await timeline_said(client, case, "CASE_RESOLVED")
        assert said and said[0].startswith(f"应急事项已解决：2 笔应急补货共 {total} 件已全部到货")


async def test_stopping_after_a_part_filled_order_settles_with_what_arrived(db):
    async with environment(db) as (seed, client):
        case = await taken_in_part(db, seed, client)
        path = f"/api/v1/operations-cases/{case['id']}/control"
        refreshed = await client.post(
            path, json={"expected_revision": 1, "operation": "refresh"}, headers=headers()
        )
        await analyze(client, refreshed.json())
        waited = await client.post(
            path, json={"expected_revision": 2, "operation": "adopt_waiting"}, headers=headers()
        )
        assert waited.status_code == 200, waited.text
        current = waited.json()
        assert (current["status"], current["routine_paused"]) == ("RESOLVED", False)
        outcome = current["outcome"]
        assert (outcome["path"], outcome["planned_qty"], outcome["purchased_qty"]) == (
            "purchase",
            20,
            10,
        )
        assert outcome["received_qty"] == 10


async def test_a_declined_order_is_no_longer_the_case_order_and_its_supplier_is_left_out(db):
    async with environment(db) as (seed, client):
        case, action_id, outcome = await sent_by_hand(db, seed, client, "抱歉，这批没货了")
        assert outcome == "declined"
        current = await case_view(client, case)
        assert (current["action_id"], current["execution_status"]) == (None, "FAILED")
        assert [(p["action_id"], p["status"]) for p in current["purchases"]] == [
            (action_id, "FAILED")
        ]
        assert current["status"] == "RECHECK_REQUIRED"
        assert current["excluded_supplier_ids"] == ["B"]
        path = f"/api/v1/operations-cases/{case['id']}"
        # Analyzing the same revision again would change nothing; the Case says what to do.
        again = await client.post(
            path + "/analyze", json={"expected_revision": 1}, headers=headers()
        )
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "CASE_REFRESH_REQUIRED"
        # The owner also leaves C out; the choice carries over to later revisions.
        await client.post(
            path + "/revise",
            json={"expected_revision": 1, "excluded_supplier_ids": ["C"]},
            headers=headers(),
        )
        revised = await client.post(
            path + "/revise",
            json={"expected_revision": 2, "budget_minor": 25000},
            headers=headers(),
        )
        options = await analyze(client, revised.json())
        assert options["excluded_supplier_ids"] == ["B", "C"]
        offered = {c["supplier_id"] for c in options["proposal"]["candidates"]}
        assert offered <= {None, "supplier_001"}


async def test_waiting_with_no_original_order_on_the_way_ends_the_case_at_once(db):
    from app.missions.models import InboundRow
    from app.operations.models import StockRow

    async with environment(db) as (seed, client):
        case = await recovery_case(db, seed, client)
        async with db.session() as session, session.begin():
            original = await session.get(InboundRow, ("original-" + seed["store_id"], "sku_001"))
            await session.delete(original)
            stock = await session.get(StockRow, (seed["store_id"], "sku_001"))
            stock.in_transit = 0
        case = await analyze(client, case)
        waited = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "adopt_waiting"},
            headers=headers(),
        )
        assert waited.status_code == 200, waited.text
        current = waited.json()
        assert (current["status"], current["routine_paused"]) == ("RESOLVED", False)
        outcome = current["outcome"]
        assert outcome["path"] == "waiting"
        assert outcome["lost_qty_after"] == outcome["lost_qty_before"]
        said = await timeline_said(client, case, "CASE_RESOLVED")
        assert said and said[0].startswith("应急事项已结束：没有在途的原订单，这次不补货")
        assert "CASE_DECISION" not in await timeline_types(client, case)
        # Daily suggestions come back without the owner ending anything.
        await run_check(db, seed)
        assert await current_plan(client, case) is not None


async def test_one_open_emergency_case_per_item(db):
    async with environment(db) as (seed, client):
        case = await recovery_case(db, seed, client)
        body = {"mission_id": case["mission_id"], "objective": "再开一件", "budget_minor": 1000}
        second = await client.post("/api/v1/operations-cases", json=body, headers=headers())
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CASE_ALREADY_OPEN"
        ended = await client.post(
            f"/api/v1/operations-cases/{case['id']}/control",
            json={"expected_revision": 1, "operation": "cancel"},
            headers=headers(),
        )
        assert ended.status_code == 200, ended.text
        again = await client.post("/api/v1/operations-cases", json=body, headers=headers())
        assert again.status_code == 201, again.text


async def test_a_scenario_written_before_the_clock_moved_is_dated_from_the_analysis(db):
    from app.operations.models import Store

    async with environment(db) as (seed, client):
        case = await recovery_case(db, seed, client)
        async with db.session() as session, session.begin():
            store = await session.get(Store, seed["store_id"])
            store.simulation_time += timedelta(days=1, hours=2)
            store.state_version += 1
            clock = store.simulation_time
        current = await analyze(client, case)
        assert current["status"] == "OPTIONS_READY", current["missing_inputs"]
        days = current["proposal"]["candidates"][0]["daily"]
        first = datetime.fromisoformat(days[0]["settlement_at"])
        assert clock <= first < clock + timedelta(days=1)
        # The quantities stay the owner's, day by day.
        assert [d["demand_qty"] for d in days] == [10] * 7
