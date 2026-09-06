from datetime import timedelta

from sqlalchemy import exists, func, or_, select

from app.core.errors import AppError
from app.execution.accounting import action_alert, apply_receipt, close_action
from app.execution.models import ActionRow
from app.execution.repository import PENDING, lock_action, queue_action, validate_current
from app.missions.repository import queue_check, timeline
from app.operations.client import SimulationClient
from app.operations.repository import digest
from app.scheduling.handlers import Handler
from app.scheduling.models import Job
from app.scheduling.repository import enqueue, renew


async def recover_actions(db):
    # Separate from JobRun recovery: never hold a job lock before a store lock.
    async with db.session() as session:
        ids = list(
            await session.scalars(
                select(ActionRow.id)
                .where(
                    ActionRow.status.in_(PENDING),
                    ActionRow.manual_review.is_(False),
                    or_(
                        ActionRow.next_attempt_at.is_(None),
                        ActionRow.next_attempt_at <= func.clock_timestamp(),
                    ),
                    ~exists(
                        select(Job.id).where(
                            Job.payload["action_id"].astext == ActionRow.id,
                            Job.job_type.in_(["execute_purchase", "reconcile_action"]),
                            Job.status.in_(["READY", "RUNNING", "RETRY_WAIT"]),
                        )
                    ),
                )
                .order_by(ActionRow.store_id, ActionRow.id)
                .limit(100)
            )
        )
    for identifier in ids:
        async with db.session() as session, session.begin():
            _, _, _, action = await lock_action(session, identifier)
            if action.status in PENDING and not action.manual_review:
                await queue_action(session, action)


def make_handlers(settings, *, client=None):
    client = client or SimulationClient(settings)

    async def run(db, job):
        async with db.session() as session, session.begin():
            store, mission, plan, action = await lock_action(session, job.payload["action_id"])
            if action.status not in PENDING or action.manual_review:
                return None, None
            send = action.status == "QUEUED"
            if send:
                try:
                    await validate_current(session, store, mission, plan, settings)
                    if store.active_action_id != action.id:
                        raise AppError(
                            409, "ACTION_IN_PROGRESS", "Store gate does not match Action"
                        )
                except AppError as exc:
                    await close_action(session, store, mission, action, "STALE", reason=exc.code)
                    if mission.status == "ACTIVE":
                        await queue_check(session, store, mission, key="stale-" + action.id)
                    if not await renew(
                        session, job.id, job.lease_token, settings.job_lease_seconds
                    ):
                        await session.rollback()
                    return None, None
                store.reserved_cash_minor += action.amount_minor
                action.reserved_minor = action.amount_minor
                store.state_version += 1
                action.execution_state_version = store.state_version
                action.status = "EXECUTING"
                await timeline(
                    session,
                    mission,
                    "ACTION_EXECUTING",
                    "采购已登记发送，资金暂时预留。",
                    references=[{"type": "action", "id": action.id}],
                )
            now = await session.scalar(select(func.clock_timestamp()))
            action.reconcile_count += 1
            delay = [5, 10, 30, 60][min(action.reconcile_count - 1, 3)]
            action.next_attempt_at = now + timedelta(seconds=delay)
            action.updated_at = now
            payload, identifier = dict(action.request_snapshot), action.id
            if not await renew(session, job.id, job.lease_token, settings.job_lease_seconds):
                await session.rollback()
                return None, None
        try:
            if not send:
                receipt = await client.get_purchase(identifier)
                if receipt is not None:
                    return receipt, None
            # Simulator explicitly guarantees same-ID, same-body replay even after a404 race.
            return await client.purchase(identifier, payload), None
        except AppError as exc:
            return None, exc.code

    async def apply(session, job, prepared):
        raw, error = prepared
        store, mission, _, action = await lock_action(session, job.payload["action_id"])
        if raw is not None:
            await apply_receipt(session, store, mission, action, raw)
        elif error and action.status in {"EXECUTING", "UNKNOWN"} and not action.manual_review:
            action.status, action.last_error = "UNKNOWN", error
            await action_alert(session, store, mission, action, error)
        return {
            "summary": "Purchase action " + action.status,
            "references": [{"type": "action", "id": action.id}],
            "output_state_version": store.state_version,
        }

    async def after_complete(session, job, result):
        store, mission, _, action = await lock_action(session, job.payload["action_id"])
        if action.status in PENDING and not action.manual_review:
            await queue_action(session, action)
        elif action.status in {"SUCCEEDED", "FAILED"}:
            await enqueue(
                session,
                job_type="sync_events",
                store_id=store.id,
                dedup_key=digest(["action-sync", job.id]),
                payload={"scenario_run_id": store.scenario_run_id},
            )
            if mission.status == "ACTIVE":
                await queue_check(session, store, mission, key="action-check-" + job.id)

    handler = Handler(run, retry_safe=True, apply=apply, after_complete=after_complete)
    return {"execute_purchase": handler, "reconcile_action": handler}
