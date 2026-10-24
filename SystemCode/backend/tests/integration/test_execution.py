import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from test_missions import clean_queue, environment, headers, settings  # noqa: F401
from test_operations import event, ingest, state
from test_planning_jobs import run_check, start

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def isolated_actions(db):
    # The production orphan scanner deliberately sees every store. Test actions
    # must stop being recoverable when their isolated fake supplier goes away.
    async def clear():
        async with db.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE stores SET reserved_cash_minor=0, active_action_id=NULL "
                    "WHERE active_action_id IS NOT NULL"
                )
            )
            await session.execute(
                text(
                    "UPDATE missions SET current_action_id=NULL WHERE current_action_id IS NOT NULL"
                )
            )
            await session.execute(
                text(
                    "UPDATE actions SET status='CANCELLED' "
                    "WHERE status IN ('QUEUED','EXECUTING','UNKNOWN')"
                )
            )

    await clear()
    yield
    await clear()


async def planned(db, seed, client):
    mission = await start(client, seed)
    await run_check(db, seed)
    result = (await client.get(f"/api/v1/missions/{mission['id']}/plans", headers=headers())).json()
    return mission, result["items"][0]


def decision(plan, choice="approve"):
    return {
        "decision": choice,
        "expected_plan_version": plan["plan_version"],
        "expected_state_version": plan["state_version"],
        "proposal_hash": plan["proposal_hash"],
    }


async def approve(client, plan, **kwargs):
    response = await client.post(
        f"/api/v1/plans/{plan['id']}/decision",
        json=decision(plan),
        headers=kwargs.pop("headers", headers("approver")),
        **kwargs,
    )
    assert response.status_code == 202, response.text
    return response.json()


class Supplier:
    def __init__(self):
        self.calls = []
        self.receipts = {}
        self.drop_response = False
        self.reject = False

    async def purchase(self, action_id, payload):
        self.calls.append((action_id, payload))
        if action_id not in self.receipts:
            self.receipts[action_id] = {
                "action_id": action_id,
                "status": "REJECTED" if self.reject else "ACCEPTED",
                "external_order_id": None if self.reject else "order-" + action_id,
                "quantity": payload["quantity"],
                "total_minor": payload["expected_total_minor"],
                "currency": "CNY",
                "recorded_at": datetime.now(UTC).isoformat(),
                "reason": "Supplier rejected" if self.reject else None,
            }
        if self.drop_response:
            from app.core.errors import AppError

            raise AppError(503, "SIMULATION_UNAVAILABLE", "Lost response", retryable=True)
        return self.receipts[action_id]

    async def get_purchase(self, action_id):
        return self.receipts.get(action_id)


async def execute(db, seed, supplier):
    from app.execution.jobs import make_handlers
    from app.scheduling.runner import Runner

    runner = Runner(
        db, settings(db, seed), handlers=make_handlers(settings(db, seed), client=supplier)
    )
    assert await runner.run_once()


async def test_concurrent_approval_replay_exact_content_and_role_checks(db):
    from app.execution.models import ActionRow, ApprovalRow

    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        path = f"/api/v1/plans/{plan['id']}/decision"
        assert (
            await client.post(path, json=decision(plan), headers=headers("operator"))
        ).status_code == 403
        assert (
            await client.post(
                path, json=decision(plan) | {"approved_by": "admin"}, headers=headers("approver")
            )
        ).status_code == 422
        key_headers = headers("approver")
        responses = await asyncio.gather(
            *[client.post(path, json=decision(plan), headers=key_headers) for _ in range(3)]
        )
        assert all(r.status_code == 202 and r.json() == responses[0].json() for r in responses)
        assert (
            await client.post(path, json=decision(plan), headers=headers("approver"))
        ).status_code == 409
        assert (await state(db, seed))["reserved_cash_minor"] == 0
        async with db.session() as session:
            assert (
                len(
                    list(
                        await session.scalars(
                            select(ActionRow).where(ActionRow.plan_id == plan["id"])
                        )
                    )
                )
                == 1
            )
            assert (
                len(
                    list(
                        await session.scalars(
                            select(ApprovalRow).where(ApprovalRow.plan_id == plan["id"])
                        )
                    )
                )
                == 1
            )


async def test_purchase_receipt_event_and_goods_are_accounted_once(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        await execute(db, seed, supplier)
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["reserved_cash_minor"],
            current["stocks"][0]["in_transit"],
        ) == (60000, 0, 40)
        action_id = accepted["action_id"]
        receipt = supplier.receipts[action_id]
        purchase = event(seed, 1, "PURCHASE_ACCEPTED")
        purchase["payload"] = {
            "action_id": action_id,
            "external_order_id": receipt["external_order_id"],
            "sku_id": "sku_001",
            "quantity": 40,
            "total_minor": 40000,
        }
        goods = event(seed, 2, "GOODS_RECEIVED", action_id=action_id)
        await ingest(db, seed, [purchase, goods])
        await ingest(db, seed, [purchase, goods])
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["stocks"][0]["on_hand"],
            current["stocks"][0]["in_transit"],
        ) == (60000, 60, 0)
        action = (
            await client.get(f"/api/v1/actions/{action_id}", headers=headers("viewer"))
        ).json()
        assert action["status"] == "SUCCEEDED" and action["receipt"]["status"] == "ACCEPTED"
        async with db.session() as session:
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


async def test_unknown_retains_reserve_then_queries_original_without_rebuy(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        supplier.drop_response = True
        await execute(db, seed, supplier)
        current = await state(db, seed)
        assert (current["cash_minor"], current["reserved_cash_minor"]) == (100000, 40000)
        action = (
            await client.get(f"/api/v1/actions/{accepted['action_id']}", headers=headers())
        ).json()
        assert action["status"] == "UNKNOWN"
        async with db.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE job_runs SET available_at=clock_timestamp() "
                    "WHERE job_type='reconcile_action'"
                )
            )
        await execute(db, seed, supplier)
        assert len(supplier.calls) == 1
        assert (await state(db, seed))["cash_minor"] == 60000


async def retry_now(db, action_id):
    async with db.session() as session, session.begin():
        await session.execute(
            text(
                "UPDATE job_runs SET available_at=clock_timestamp() "
                "WHERE payload->>'action_id'=:id AND status IN ('READY','RETRY_WAIT')"
            ),
            {"id": action_id},
        )
        await session.execute(
            text("UPDATE actions SET next_attempt_at=clock_timestamp() WHERE id=:id"),
            {"id": action_id},
        )


async def test_reject_is_terminal_and_replay_cannot_change_decision(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        path = f"/api/v1/plans/{plan['id']}/decision"
        key_headers = headers("approver")
        first = await client.post(path, json=decision(plan, "reject"), headers=key_headers)
        assert first.status_code == 200 and first.json()["action_id"] is None
        assert (
            await client.post(path, json=decision(plan, "reject"), headers=key_headers)
        ).json() == first.json()
        changed = await client.post(path, json=decision(plan), headers=key_headers)
        assert changed.status_code == 409
        assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        async with db.session() as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM actions WHERE plan_id=:id"), {"id": plan["id"]}
                )
                == 0
            )


async def test_zero_recommendation_cannot_create_purchase(db):
    from test_missions import body

    async with environment(db) as (seed, client):
        content = body(seed)
        content["policy"]["candidate_quantities"] = [0]
        mission = (await client.post("/api/v1/missions", json=content, headers=headers())).json()
        await run_check(db, seed)
        plan = (
            await client.get(f"/api/v1/missions/{mission['id']}/plans", headers=headers())
        ).json()["items"][0]
        assert plan["proposed_purchase"] is None
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision", json=decision(plan), headers=headers("approver")
        )
        assert (
            response.status_code == 422
            and response.json()["error"]["code"] == "NO_PURCHASE_PROPOSED"
        )


@pytest.mark.parametrize(
    "change,code",
    [
        ("state", "STATE_VERSION_CONFLICT"),
        ("expiry", "PLAN_EXPIRED"),
        ("source", "DATA_STALE"),
        ("hash", "PROPOSAL_HASH_CONFLICT"),
    ],
)
async def test_approval_rechecks_current_inputs(db, change, code):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        body = decision(plan)
        async with db.session() as session, session.begin():
            if change == "state":
                await session.execute(
                    text("UPDATE stores SET state_version=state_version+1 WHERE id=:id"),
                    {"id": seed["store_id"]},
                )
            elif change == "expiry":
                await session.execute(
                    text(
                        "UPDATE plans SET expires_at=clock_timestamp()-interval '1 second' "
                        "WHERE id=:id"
                    ),
                    {"id": plan["id"]},
                )
            elif change == "source":
                await session.execute(
                    text("UPDATE source_cursors SET last_success_at=NULL WHERE store_id=:id"),
                    {"id": seed["store_id"]},
                )
            else:
                body["proposal_hash"] = "sha256:" + "a" * 64
        response = await client.post(
            f"/api/v1/plans/{plan['id']}/decision", json=body, headers=headers("approver")
        )
        assert response.status_code == 409 and response.json()["error"]["code"] == code, (
            response.text
        )


async def test_sale_between_approval_and_send_stales_without_reserving(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        await ingest(db, seed, [event(seed)])
        supplier = Supplier()
        await execute(db, seed, supplier)
        action = (
            await client.get(f"/api/v1/actions/{accepted['action_id']}", headers=headers())
        ).json()
        assert action["status"] == "STALE" and supplier.calls == []
        assert (await state(db, seed))["reserved_cash_minor"] == 0


async def test_explicit_rejection_releases_funds_and_raises_action_alert(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        supplier.reject = True
        await execute(db, seed, supplier)
        action = (
            await client.get(f"/api/v1/actions/{accepted['action_id']}", headers=headers())
        ).json()
        assert action["status"] == "FAILED"
        current = await state(db, seed)
        assert (current["cash_minor"], current["reserved_cash_minor"]) == (100000, 0)
        alerts = (
            await client.get(
                "/api/v1/alerts", params={"store_id": seed["store_id"]}, headers=headers()
            )
        ).json()
        assert any(
            a["type"] == "ACTION_EXCEPTION" and a["facts"]["action_id"] == action["id"]
            for a in alerts["items"]
        )


async def test_missing_query_resends_only_original_snapshot(db):
    from app.core.errors import AppError

    class Missing(Supplier):
        async def purchase(self, action_id, payload):
            if not self.calls:
                self.calls.append((action_id, dict(payload)))
                raise AppError(503, "SIMULATION_UNAVAILABLE", "Request lost")
            return await super().purchase(action_id, payload)

    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Missing()
        await execute(db, seed, supplier)
        await retry_now(db, accepted["action_id"])
        await execute(db, seed, supplier)
        assert len(supplier.calls) == 2 and supplier.calls[0] == supplier.calls[1]
        assert (await state(db, seed))["cash_minor"] == 60000


@pytest.mark.parametrize("sent", [False, True])
async def test_cancel_stops_unsent_but_preserves_late_sent_receipt(db, sent):
    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        supplier.drop_response = True
        if sent:
            await execute(db, seed, supplier)
        path = f"/api/v1/missions/{mission['id']}/control"
        response = await client.post(
            path,
            json={"operation": "complete", "expected_mission_version": 1},
            headers=headers("approver"),
        )
        assert response.status_code == 409
        response = await client.post(
            path,
            json={"operation": "cancel", "expected_mission_version": 1},
            headers=headers("approver"),
        )
        assert response.status_code == 200, response.text
        if sent:
            await retry_now(db, accepted["action_id"])
        await execute(db, seed, supplier)
        action = (
            await client.get(f"/api/v1/actions/{accepted['action_id']}", headers=headers())
        ).json()
        assert action["status"] == ("SUCCEEDED" if sent else "CANCELLED")
        assert len(supplier.calls) == int(sent)


async def test_conflicting_receipt_keeps_evidence_and_reservation(db):
    class Wrong(Supplier):
        async def purchase(self, action_id, payload):
            return (await super().purchase(action_id, payload)) | {"quantity": 41}

    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        await execute(db, seed, Wrong())
        current = await state(db, seed)
        assert (current["cash_minor"], current["reserved_cash_minor"]) == (100000, 40000)
        async with db.session() as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM action_evidence WHERE action_id=:id"),
                    {"id": accepted["action_id"]},
                )
                == 1
            )
            assert await session.scalar(
                text("SELECT manual_review FROM actions WHERE id=:id"),
                {"id": accepted["action_id"]},
            )


async def test_partial_goods_overreceipt_rolls_back_entire_batch(db):
    from app.core.errors import AppError

    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        await execute(db, seed, Supplier())
        first = event(seed, 1, "GOODS_RECEIVED", action_id=accepted["action_id"], quantity=15)
        await ingest(db, seed, [first])
        before = await state(db, seed)
        with pytest.raises(AppError, match="conflicts"):
            await ingest(
                db,
                seed,
                [
                    event(seed, 2),
                    event(seed, 3, "GOODS_RECEIVED", action_id=accepted["action_id"], quantity=26),
                ],
            )
        assert await state(db, seed) == before
        await ingest(
            db,
            seed,
            [event(seed, 2, "GOODS_RECEIVED", action_id=accepted["action_id"], quantity=25)],
        )
        assert (await state(db, seed))["stocks"][0]["on_hand"] == 60


@pytest.mark.parametrize("conflict", [False, True])
async def test_source_goods_prefetch_and_conflict_evidence_survive_batch_rollback(db, conflict):
    from app.operations.jobs import make_handlers
    from app.operations.schemas import EventPage
    from app.scheduling.repository import enqueue
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        supplier.drop_response = True
        await execute(db, seed, supplier)
        before = await state(db, seed)
        events = [
            event(
                seed,
                1,
                "GOODS_RECEIVED",
                action_id=accepted["action_id"],
                quantity=41 if conflict else 40,
            )
        ]

        class Source:
            async def events(self, run_id, after):
                return EventPage(
                    events=events, last_sequence=1, source_head_sequence=1, has_more=False
                )

            async def get_purchase(self, identifier):
                # A separate connection can lock the store during HTTP preparation.
                async with db.session() as session, session.begin():
                    await session.execute(
                        text("SELECT id FROM stores WHERE id=:id FOR UPDATE NOWAIT"),
                        {"id": seed["store_id"]},
                    )
                return await supplier.get_purchase(identifier)

        async with db.session() as session, session.begin():
            await enqueue(
                session,
                job_type="sync_events",
                store_id=seed["store_id"],
                dedup_key=str(uuid4()),
                payload={"scenario_run_id": seed["scenario_run_id"]},
            )
        handler = make_handlers(settings(db, seed), client=Source())["sync_events"]
        await Runner(db, settings(db, seed), handlers={"sync_events": handler}).run_once()
        after = await state(db, seed)
        async with db.session() as session:
            sequence = await session.scalar(
                text("SELECT last_sequence FROM source_cursors WHERE store_id=:id"),
                {"id": seed["store_id"]},
            )
            evidence = await session.scalar(
                text("SELECT count(*) FROM action_evidence WHERE action_id=:id"),
                {"id": accepted["action_id"]},
            )
        if conflict:
            assert after == before and sequence == 0 and evidence == 1
        else:
            assert sequence == 1 and evidence == 0
            assert (
                after["cash_minor"],
                after["reserved_cash_minor"],
                after["stocks"][0]["on_hand"],
                after["stocks"][0]["in_transit"],
            ) == (60000, 0, 60, 0)
