from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_execution import (
    Supplier,
    approve,
    clean_queue,  # noqa: F401
    environment,
    isolated_actions,  # noqa: F401
    planned,
    retry_now,
    settings,
    state,
)

pytestmark = pytest.mark.integration


async def test_external_acceptance_after_lease_loss_cannot_publish_until_orphan_reconciliation(db):
    from app.execution.jobs import make_handlers
    from app.execution.models import ActionRow
    from app.missions.models import InboundRow
    from app.operations.models import LedgerEntry
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        approved = await approve(client, plan)
        action_id, job_id = approved["action_id"], approved["job_run_id"]

        class CommittedThenLostLease(Supplier):
            def __init__(self):
                super().__init__()
                self.queries = []

            async def purchase(self, identifier, payload):
                # The supplier retains its acceptance before the backend loses its lease.
                receipt = await super().purchase(identifier, payload)
                async with db.session() as session, session.begin():
                    job = await session.get(Job, job_id)
                    job.lease_until = await session.scalar(
                        select(func.clock_timestamp())
                    ) - timedelta(seconds=1)
                    job.attempt_count = 3
                return receipt

            async def get_purchase(self, identifier):
                self.queries.append(identifier)
                return await super().get_purchase(identifier)

        supplier = CommittedThenLostLease()
        config = settings(db, seed)
        runner = Runner(db, config, handlers=make_handlers(config, client=supplier))
        assert await runner.run_once()
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["reserved_cash_minor"],
            current["stocks"][0]["in_transit"],
        ) == (100000, 40000, 0)
        async with db.session() as session:
            action = await session.get(ActionRow, action_id)
            assert action.status == "EXECUTING" and action.receipt is None
            assert action.external_order_id is None and action.reserved_minor == 40000
            assert (await session.get(Job, job_id)).status == "RUNNING"
            assert await session.get(InboundRow, (action_id, "sku_001")) is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(LedgerEntry)
                    .where(
                        LedgerEntry.store_id == seed["store_id"],
                        LedgerEntry.effect_type == "PURCHASE_ACCEPTED",
                    )
                )
                == 0
            )

        await retry_now(db, action_id)
        # First recovery retires the exhausted expired job; the next scan finds
        # the pending Action without an active job and reconstructs reconciliation.
        restarted = Runner(db, config, handlers=make_handlers(config, client=supplier))
        assert not await restarted.run_once()
        async with db.session() as session:
            assert (await session.get(Job, job_id)).status == "FAILED"
        assert await restarted.run_once()
        current = await state(db, seed)
        assert (
            current["cash_minor"],
            current["reserved_cash_minor"],
            current["stocks"][0]["in_transit"],
        ) == (60000, 0, 40)
        assert len(supplier.calls) == 1 and supplier.calls[0][0] == action_id
        assert supplier.queries == [action_id]
        async with db.session() as session:
            action = await session.get(ActionRow, action_id)
            assert action.status == "SUCCEEDED"
            assert action.external_order_id == supplier.receipts[action_id]["external_order_id"]
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


async def test_expired_preflight_lease_rolls_back_reservation_and_does_not_send(db):
    from app.execution.jobs import make_handlers
    from app.execution.models import ActionRow
    from app.missions.models import TimelineRow
    from app.scheduling.models import Job
    from app.scheduling.repository import claim

    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        approved = await approve(client, plan)
        config = settings(db, seed)
        before = await state(db, seed)
        async with db.session() as session, session.begin():
            job = await claim(
                session, lease_seconds=config.job_lease_seconds, job_types=["execute_purchase"]
            )
            assert job.id == approved["job_run_id"]
            job.lease_until = await session.scalar(select(func.clock_timestamp())) - timedelta(
                seconds=1
            )

        supplier = Supplier()
        handler = make_handlers(config, client=supplier)["execute_purchase"]
        assert await handler.run(db, job) == (None, None)
        assert supplier.calls == [] and supplier.receipts == {}
        assert await state(db, seed) == before
        async with db.session() as session:
            action = await session.get(ActionRow, approved["action_id"])
            assert (action.status, action.reserved_minor, action.reconcile_count) == (
                "QUEUED",
                0,
                0,
            )
            assert action.next_attempt_at is None and action.execution_state_version is None
            assert (await session.get(Job, job.id)).status == "RUNNING"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(TimelineRow)
                    .where(
                        TimelineRow.mission_id == mission["id"],
                        TimelineRow.type == "ACTION_EXECUTING",
                    )
                )
                == 0
            )


async def test_recovery_filters_active_jobs_before_batch_limit_so_orphan_101_is_not_starved(db):
    from app.execution.jobs import recover_actions
    from app.execution.models import ActionRow, ApprovalRow
    from app.missions.models import PlanRow
    from app.scheduling.models import Job
    from app.scheduling.repository import enqueue

    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        approved = await approve(client, plan)
        prefix = "recovery-" + uuid4().hex
        orphan_id = prefix + "-101"
        async with db.session() as session, session.begin():
            original_action = await session.get(ActionRow, approved["action_id"])
            original_approval = await session.get(ApprovalRow, original_action.approval_id)
            original_plan = await session.get(PlanRow, plan["id"])
            # These structurally valid rows exercise the scanner only. They are
            # never executed and do not alter the Mission's current Action gate.
            for index in range(1, 102):
                action_id = f"{prefix}-{index:03}"
                plan_id, approval_id = str(uuid4()), str(uuid4())
                version = original_plan.plan_version + index
                document = deepcopy(original_plan.document)
                document.update(id=plan_id, plan_version=version)
                session.add(
                    PlanRow(
                        id=plan_id,
                        mission_id=mission["id"],
                        plan_version=version,
                        state_version=original_plan.state_version,
                        input_hash=original_plan.input_hash,
                        status="APPROVED",
                        document=document,
                        created_at=original_plan.created_at,
                        expires_at=original_plan.expires_at,
                    )
                )
                await session.flush()
                session.add(
                    ApprovalRow(
                        id=approval_id,
                        plan_id=plan_id,
                        actor_id=original_approval.actor_id,
                        decision="approve",
                        proposal_hash=original_approval.proposal_hash,
                        state_version=original_approval.state_version,
                        decided_at=original_approval.decided_at,
                    )
                )
                await session.flush()
                session.add(
                    ActionRow(
                        id=action_id,
                        store_id=seed["store_id"],
                        mission_id=mission["id"],
                        plan_id=plan_id,
                        approval_id=approval_id,
                        status="UNKNOWN",
                        purchase_snapshot=deepcopy(original_action.purchase_snapshot),
                        request_snapshot=original_action.request_snapshot
                        | {"action_id": action_id},
                        reserved_minor=0,
                        manual_review=False,
                        reconcile_count=1,
                        created_at=original_action.created_at,
                        updated_at=original_action.updated_at,
                    )
                )
                if index <= 100:
                    await enqueue(
                        session,
                        job_type="reconcile_action",
                        store_id=seed["store_id"],
                        mission_id=mission["id"],
                        dedup_key=action_id,
                        payload={"action_id": action_id},
                    )

        await recover_actions(db)
        await recover_actions(db)
        async with db.session() as session:
            orphan_jobs = list(
                await session.scalars(
                    select(Job).where(
                        Job.payload["action_id"].astext == orphan_id,
                    )
                )
            )
            assert len(orphan_jobs) == 1
            assert (orphan_jobs[0].job_type, orphan_jobs[0].status) == ("reconcile_action", "READY")
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(
                        Job.store_id == seed["store_id"],
                        Job.job_type.in_(["execute_purchase", "reconcile_action"]),
                    )
                )
                == 102
            )
