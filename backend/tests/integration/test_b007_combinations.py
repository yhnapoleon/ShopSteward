"""B0-07 combined failures, with real queue transactions and transport barriers."""

import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select, text
from test_execution import (
    Supplier,
    approve,
    decision,
    isolated_actions,  # noqa: F401
    planned,
    retry_now,
)
from test_missions import environment, headers, settings
from test_operations import event, ingest, state
from test_periodic import clean_queue, source_job  # noqa: F401
from test_planning_jobs import run_check, start

from app.alerts.models import AlertRow
from app.execution.jobs import make_handlers as execution_handlers
from app.execution.models import ActionRow, ApprovalRow
from app.missions.models import InboundRow, MissionRow, PlanRow, ScheduleRow
from app.operations.client import SimulationClient
from app.operations.jobs import make_handlers as source_handlers
from app.operations.models import LedgerEntry, SourceCursor, SourceSchedule
from app.planning.jobs import make_handlers as planning_handlers
from app.scheduling.dispatcher import dispatch_due
from app.scheduling.handlers import Handler
from app.scheduling.models import Job
from app.scheduling.runner import Runner

pytestmark = pytest.mark.integration


class AcceptedThenDisconnected:
    """Keep supplier truth while the real HTTP client receives a lost response."""

    def __init__(self):
        self.supplier = Supplier()
        self.sent = asyncio.Event()
        self.release_send = asyncio.Event()
        self.queried = asyncio.Event()
        self.release_query = asyncio.Event()
        self.release_query.set()
        self.queries = []
        self.events = []

    async def __call__(self, request):
        if request.method == "POST" and request.url.path == "/sim/v1/purchases":
            action_id = request.headers["Idempotency-Key"]
            await self.supplier.purchase(action_id, json.loads(request.content))
            self.sent.set()
            await self.release_send.wait()
            raise httpx.ReadError("Accepted purchase response disconnected", request=request)
        if request.method == "GET" and request.url.path.startswith("/sim/v1/purchases/"):
            action_id = request.url.path.rsplit("/", 1)[-1]
            self.queries.append(action_id)
            self.queried.set()
            await self.release_query.wait()
            receipt = await self.supplier.get_purchase(action_id)
            return httpx.Response(200 if receipt else 404, json=receipt)
        if request.method == "GET" and request.url.path.endswith("/events"):
            after = int(request.url.params["after_sequence"])
            return httpx.Response(
                200,
                json={
                    "events": self.events[after:],
                    "last_sequence": len(self.events),
                    "has_more": False,
                    "source_head_sequence": len(self.events),
                },
            )
        raise AssertionError(f"Unexpected supplier request: {request.method} {request.url.path}")


def controlled_client(db, seed, transport):
    config = settings(db, seed, simulation_token="b007-local-transport-credential")
    return config, SimulationClient(config, transport=httpx.MockTransport(transport))


async def active_risks(db, mission_id):
    async with db.session() as session:
        return {
            row.type: row.id
            for row in await session.scalars(
                select(AlertRow).where(
                    AlertRow.mission_id == mission_id, AlertRow.status != "RESOLVED"
                )
            )
        }


async def test_distinct_approval_keys_two_workers_and_lost_response_reconcile_one_action(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        approval_start = asyncio.Barrier(3)
        request_headers = [headers("approver") for _ in range(3)]

        async def competing_approval(request_header):
            await approval_start.wait()
            return await client.post(
                f"/api/v1/plans/{plan['id']}/decision",
                json=decision(plan),
                headers=request_header,
            )

        responses = await asyncio.gather(*(competing_approval(h) for h in request_headers))
        assert sorted(response.status_code for response in responses) == [202, 409, 409]
        winner = next(
            index for index, response in enumerate(responses) if response.status_code == 202
        )
        accepted = responses[winner].json()
        action_id = accepted["action_id"]
        transport = AcceptedThenDisconnected()
        config, supplier_client = controlled_client(db, seed, transport)
        handlers = execution_handlers(config, client=supplier_client)
        workers = [Runner(db, config, handlers=handlers) for _ in range(2)]
        execution = asyncio.create_task(workers[0].run_once())
        try:
            await asyncio.wait_for(transport.sent.wait(), 5)
            assert not await workers[1].run_once()
            current = await state(db, seed)
            assert (current["cash_minor"], current["reserved_cash_minor"]) == (100000, 40000)
        finally:
            transport.release_send.set()
            await execution
        async with db.session() as session:
            assert (await session.get(ActionRow, action_id)).status == "UNKNOWN"

        # A command replay while money is reserved must still name the original Action/job.
        replay = await client.post(
            f"/api/v1/plans/{plan['id']}/decision",
            json=decision(plan),
            headers=request_headers[winner],
        )
        assert replay.status_code == 202 and replay.json() == accepted
        await retry_now(db, action_id)
        transport.release_query.clear()
        recovery = asyncio.create_task(workers[1].run_once())
        try:
            await asyncio.wait_for(transport.queried.wait(), 5)
            assert not await workers[0].run_once()
        finally:
            transport.release_query.set()
            await recovery
        assert not any(await asyncio.gather(*(worker.run_once() for worker in workers)))
        assert transport.queries == [action_id]
        assert [call[0] for call in transport.supplier.calls] == [action_id]
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["reserved_cash_minor"],
            current["stocks"][0]["in_transit"],
        ) == (60000, 0, 40)
        async with db.session() as session:
            action = await session.get(ActionRow, action_id)
            assert action.status == "SUCCEEDED" and action.reserved_minor == 0
            for model in (ActionRow, ApprovalRow):
                assert (
                    await session.scalar(
                        select(func.count()).select_from(model).where(model.plan_id == plan["id"])
                    )
                    == 1
                )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(LedgerEntry)
                    .where(
                        LedgerEntry.store_id == seed["store_id"],
                        LedgerEntry.effect_type == "PURCHASE_ACCEPTED",
                    )
                )
                == 1
            )


async def test_exhausted_source_retries_recover_on_later_interval_and_revalidate_alerts(db):
    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        await run_check(db, seed)
        original_risks = await active_risks(db, mission["id"])
        assert set(original_risks) == {"STOCKOUT_RISK"}
        offline = True
        calls = []

        async def transport(request):
            assert request.method == "GET" and request.url.path.endswith("/events")
            calls.append(int(request.url.params["after_sequence"]))
            if offline:
                return httpx.Response(503, json={"error": "controlled source outage"})
            return httpx.Response(
                200,
                json={
                    "events": [],
                    "last_sequence": 0,
                    "has_more": False,
                    "source_head_sequence": 0,
                },
            )

        config, source = controlled_client(db, seed, transport)
        handlers = source_handlers(config, client=source)
        runner = Runner(db, config, handlers={"sync_events": handlers["sync_events"]})
        queued = await source_job(db, seed, "b007-outage-" + seed["store_id"])
        before = await state(db, seed)
        async with db.session() as session:
            last_success = (
                await session.get(SourceCursor, seed["scenario_run_id"])
            ).last_success_at
        for attempt in range(1, 4):
            assert await runner.run_once()
            async with db.session() as session, session.begin():
                job = await session.get(Job, queued.id)
                assert job.attempt_count == attempt
                assert job.status == ("RETRY_WAIT" if attempt < 3 else "FAILED")
                assert job.error_code == "SIMULATION_UNAVAILABLE"
                cursor = await session.get(SourceCursor, seed["scenario_run_id"])
                assert cursor.last_sequence == 0 and cursor.last_success_at == last_success
                assert cursor.last_error == "SIMULATION_UNAVAILABLE"
                if attempt < 3:
                    job.available_at = await session.scalar(select(func.clock_timestamp()))
        assert not await runner.run_once()
        await source_job(db, seed, "b007-stale-" + seed["store_id"], job_type="check_freshness")
        assert await Runner(
            db, config, handlers={"check_freshness": handlers["check_freshness"]}
        ).run_once()
        assert set(await active_risks(db, mission["id"])) == {"STOCKOUT_RISK", "DATA_STALE"}

        offline = False
        async with db.session() as session, session.begin():
            now = await session.scalar(select(func.clock_timestamp()))
            # Dispatch exactly the later source occurrence, independent of suite wall time.
            for kind in ("sync_events", "check_freshness"):
                schedule = await session.get(SourceSchedule, (seed["scenario_run_id"], kind))
                schedule.next_run_at = now + timedelta(days=1)
            sync = await session.get(SourceSchedule, (seed["scenario_run_id"], "sync_events"))
            sync.next_run_at = now - timedelta(seconds=1)
            (await session.get(ScheduleRow, mission["schedule"]["id"])).next_run_at = (
                now + timedelta(days=1)
            )
        await asyncio.gather(dispatch_due(db), dispatch_due(db))
        async with db.session() as session:
            successors = list(
                await session.scalars(
                    select(Job).where(
                        Job.store_id == seed["store_id"],
                        Job.job_type == "sync_events",
                        Job.status == "READY",
                    )
                )
            )
            assert len(successors) == 1 and successors[0].id != queued.id
            assert successors[0].trigger_source == "INTERVAL"
        assert await runner.run_once()
        assert calls == [0, 0, 0, 0]
        assert await state(db, seed) == before
        async with db.session() as session:
            assert (await session.get(Job, queued.id)).status == "FAILED"
            cursor = await session.get(SourceCursor, seed["scenario_run_id"])
            assert cursor.last_error is None and cursor.last_sequence == 0
            assert cursor.last_success_at > last_success
            checks = list(
                await session.scalars(
                    select(Job).where(
                        Job.mission_id == mission["id"],
                        Job.job_type == "check_mission",
                        Job.status == "READY",
                    )
                )
            )
            assert len(checks) == 1
        # A fresh cursor alone cannot clear business risk or claim a completed recheck.
        assert set(await active_risks(db, mission["id"])) == {"STOCKOUT_RISK", "DATA_STALE"}
        await run_check(db, seed)
        assert await active_risks(db, mission["id"]) == original_risks


async def test_running_planner_event_burst_pause_resume_publishes_only_latest_successor(db):
    async with environment(db) as (seed, client):
        mission = await start(client, seed)
        config = settings(db, seed)
        handler = planning_handlers(config)["check_mission"]
        prepared, release = asyncio.Event(), asyncio.Event()

        async def blocked_calculation(database, job):
            result = await handler.run(database, job)
            prepared.set()
            await release.wait()
            return result

        runner = Runner(
            db,
            config,
            handlers={
                "check_mission": Handler(
                    blocked_calculation,
                    retry_safe=True,
                    apply=handler.apply,
                    after_complete=handler.after_complete,
                )
            },
        )
        calculating = asyncio.create_task(runner.run_once())
        try:
            await asyncio.wait_for(prepared.wait(), 5)
            await ingest(db, seed, [event(seed, n, quantity=1) for n in (1, 2)])
            path = f"/api/v1/missions/{mission['id']}/control"
            paused = await client.post(
                path, json={"operation": "pause", "expected_mission_version": 1}, headers=headers()
            )
            assert paused.status_code == 200 and paused.json()["mission_version"] == 2
            await ingest(db, seed, [event(seed, n, quantity=1) for n in (3, 4)])
            resumed = await client.post(
                path, json={"operation": "resume", "expected_mission_version": 2}, headers=headers()
            )
            assert resumed.status_code == 200 and resumed.json()["mission_version"] == 3
            burst = [event(seed, n, quantity=1) for n in (5, 6)]
            await ingest(db, seed, burst)
            await ingest(db, seed, burst)
            async with db.session() as session:
                jobs = list(
                    await session.scalars(select(Job).where(Job.mission_id == mission["id"]))
                )
                assert len(jobs) == 1 and jobs[0].status == "RUNNING"
                assert (jobs[0].target_state_version, jobs[0].target_mission_version) == (7, 3)
                assert (await session.get(MissionRow, mission["id"])).recheck_required
        finally:
            release.set()
            await calculating
        async with db.session() as session:
            assert not list(
                await session.scalars(select(PlanRow).where(PlanRow.mission_id == mission["id"]))
            )
            jobs = list(await session.scalars(select(Job).where(Job.mission_id == mission["id"])))
            assert sorted(job.status for job in jobs) == ["READY", "SUCCEEDED"]
            assert (
                next(job for job in jobs if job.status == "SUCCEEDED").result["check_status"]
                == "SKIPPED"
            )
            successor = next(job for job in jobs if job.status == "READY")
            assert (successor.target_state_version, successor.target_mission_version) == (7, 3)
        await run_check(db, seed)
        assert not await Runner(db, config, handlers=planning_handlers(config)).run_once()
        async with db.session() as session:
            plans = list(
                await session.scalars(select(PlanRow).where(PlanRow.mission_id == mission["id"]))
            )
            assert len(plans) == 1 and plans[0].state_version == 7
            snapshot = plans[0].document["input_snapshot"]
            assert snapshot["mission_version"] == 3
            assert snapshot["state"]["stocks"][0]["on_hand"] == 14
            assert snapshot["forecast"]["remaining_demand"] == 54
            row = await session.get(MissionRow, mission["id"])
            assert row.current_plan_id == plans[0].id and not row.recheck_required
            assert not row.manual_check_requested


@pytest.mark.parametrize("operation", ["pause", "cancel"])
async def test_lifecycle_change_and_arrival_win_before_lost_purchase_response(db, operation):
    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        action_id = accepted["action_id"]
        transport = AcceptedThenDisconnected()
        config, supplier_client = controlled_client(db, seed, transport)
        runner = Runner(db, config, handlers=execution_handlers(config, client=supplier_client))
        sending = asyncio.create_task(runner.run_once())
        try:
            await asyncio.wait_for(transport.sent.wait(), 5)
            response = await client.post(
                f"/api/v1/missions/{mission['id']}/control",
                json={"operation": operation, "expected_mission_version": 1},
                headers=headers("operator" if operation == "pause" else "approver"),
            )
            assert response.status_code == 200, response.text
            receipt = transport.supplier.receipts[action_id]
            purchase = event(seed, 1, "PURCHASE_ACCEPTED")
            purchase["payload"] = {
                "action_id": action_id,
                "external_order_id": receipt["external_order_id"],
                "sku_id": "sku_001",
                "quantity": 40,
                "total_minor": 40000,
            }
            transport.events = [purchase, event(seed, 2, "GOODS_RECEIVED", action_id=action_id)]
            await source_job(db, seed, "b007-arrival-" + action_id)
            sync = source_handlers(config, client=supplier_client)["sync_events"]
            assert await Runner(db, config, handlers={"sync_events": sync}).run_once()
            async with db.session() as session:
                assert (await session.get(ActionRow, action_id)).status == "SUCCEEDED"
                assert (await session.get(Job, accepted["job_run_id"])).status == "RUNNING"
        finally:
            transport.release_send.set()
            await sending
        # Replaying the complete source history after the late timeout cannot buy/debit twice.
        await ingest(db, seed, transport.events)
        assert not await runner.run_once()
        assert [call[0] for call in transport.supplier.calls] == [action_id]
        assert transport.queries == [action_id]
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["reserved_cash_minor"],
            current["stocks"][0]["on_hand"],
            current["stocks"][0]["in_transit"],
        ) == (60000, 0, 60, 0)
        async with db.session() as session:
            action = await session.get(ActionRow, action_id)
            assert action.status == "SUCCEEDED" and action.last_error is None
            inbound = await session.get(InboundRow, (action_id, "sku_001"))
            assert (inbound.ordered_qty, inbound.received_qty) == (40, 40)
            row = await session.get(MissionRow, mission["id"])
            assert row.status == ("PAUSED" if operation == "pause" else "CANCELLED")
            assert row.current_action_id is None
            assert (await session.get(SourceCursor, seed["scenario_run_id"])).last_sequence == 2
            assert not list(
                await session.scalars(
                    select(Job).where(
                        Job.mission_id == mission["id"],
                        Job.job_type == "check_mission",
                        Job.status.in_(["READY", "RUNNING", "RETRY_WAIT"]),
                    )
                )
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM ledger_entries WHERE store_id=:id "
                        "AND effect_type='PURCHASE_ACCEPTED'"
                    ),
                    {"id": seed["store_id"]},
                )
                == 1
            )
