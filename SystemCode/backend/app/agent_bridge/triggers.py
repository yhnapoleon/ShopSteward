import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert

from app.agent_bridge.models import AgentRun, Conversation, Trigger
from app.agent_bridge.repository import promote
from app.alerts.models import AlertRow
from app.core.hashing import digest
from app.execution.models import ActionRow
from app.missions.models import InboundRow, MissionRow, PlanRow

logger = logging.getLogger("shopsteward")
# A burst of changes (a synced day, then the Mission check it wakes) is explained once.
FOLLOWUP_SETTLE_SECONDS = 5
FOLLOWUP_FAILURE_LIMIT = 3


async def record_event(session, mission_id, source_key, references):
    # Inserting a trigger only key-share locks the conversation, so business
    # transactions holding store/Mission locks never wait on an Agent run.
    conversations = (
        await session.scalars(
            select(Conversation.id).where(
                Conversation.mission_id == mission_id, Conversation.followup_enabled.is_(True)
            )
        )
    ).all()
    for identifier in conversations:
        await session.execute(
            insert(Trigger)
            .values(conversation_id=identifier, source_key=source_key, references=references)
            .on_conflict_do_nothing()
        )


async def record_store_change(session, store):
    """Synced business events moved the store (a new day of sales) without a Mission event."""
    missions = (
        await session.scalars(
            select(MissionRow.id).where(
                MissionRow.store_id == store.id, MissionRow.status == "ACTIVE"
            )
        )
    ).all()
    for mission_id in missions:
        await record_event(
            session,
            mission_id,
            f"store-state:{store.id}:{store.state_version}",
            [{"type": "store", "id": store.id, "version": str(store.state_version)}],
        )


async def followup_closed(session, conversation, run):
    """A follow-up that ended without publishing is not redone for the same state.

    Its triggers and fingerprint count as handled, so only a later business change
    starts another one. Consecutive failures pause follow-up; the failed runs keep
    the error codes, and turning follow-up on again allows one more attempt.
    """
    conversation.consumed_trigger = max(conversation.consumed_trigger, run.trigger_watermark)
    if run.trigger_fingerprint:
        conversation.last_fingerprint = run.trigger_fingerprint
    if run.status != "FAILED":
        return
    recent = (
        await session.scalars(
            select(AgentRun.status)
            .where(AgentRun.conversation_id == conversation.id, AgentRun.trigger == "FOLLOWUP")
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(FOLLOWUP_FAILURE_LIMIT)
        )
    ).all()
    if len(recent) == FOLLOWUP_FAILURE_LIMIT and set(recent) == {"FAILED"}:
        conversation.followup_enabled = False
        conversation.followup_version += 1
        logger.warning(
            "agent_followup_paused",
            extra={"conversation_id": conversation.id, "error_code": run.error_code},
        )


async def dispatch_followups(db, settings):
    if not settings.agent_enabled:
        return
    async with db.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp()))
        # A recorded business change makes an idle conversation due once it has
        # settled; the interval remains the fallback for unrecorded changes.
        changed = exists().where(
            Trigger.conversation_id == Conversation.id,
            Trigger.seq > Conversation.consumed_trigger,
            Trigger.created_at <= now - timedelta(seconds=FOLLOWUP_SETTLE_SECONDS),
        )
        conversations = (
            await session.scalars(
                select(Conversation)
                .where(
                    Conversation.followup_enabled.is_(True),
                    (Conversation.next_due <= now)
                    | (Conversation.active_run_id.is_(None) & changed),
                )
                .with_for_update(skip_locked=True, key_share=True)
                .limit(50)
            )
        ).all()
        for conversation in conversations:
            conversation.next_due = now + timedelta(seconds=conversation.followup_interval)
            if conversation.active_run_id:
                continue
            mission = await session.get(MissionRow, conversation.mission_id)
            plan = mission.current_plan_id and await session.get(PlanRow, mission.current_plan_id)
            action = mission.current_action_id and await session.get(
                ActionRow, mission.current_action_id
            )
            received = await session.execute(
                select(InboundRow.action_id, InboundRow.sku_id, InboundRow.received_qty)
                .join(ActionRow, ActionRow.id == InboundRow.action_id)
                .where(ActionRow.mission_id == mission.id)
                .order_by(InboundRow.action_id, InboundRow.sku_id)
            )
            alerts = await session.execute(
                select(AlertRow.id, AlertRow.severity)
                .where(AlertRow.mission_id == mission.id, AlertRow.status != "RESOLVED")
                .order_by(AlertRow.id)
            )
            watermark = (
                await session.scalar(
                    select(func.max(Trigger.seq)).where(
                        Trigger.conversation_id == conversation.id,
                        Trigger.seq > conversation.consumed_trigger,
                    )
                )
                or 0
            )
            # Everything a follow-up would explain; row identity of the plan is not part of it.
            fingerprint = digest(
                [
                    mission.mission_version,
                    mission.status,
                    plan.input_hash if plan else None,
                    plan.status if plan else None,
                    mission.current_action_id,
                    action.status if action else None,
                    [list(row) for row in received],
                    [list(row) for row in alerts],
                ]
            )
            if fingerprint == conversation.last_fingerprint:
                # Triggers that left the business unchanged are handled without a run.
                conversation.consumed_trigger = max(conversation.consumed_trigger, watermark)
                continue
            if mission.status != "ACTIVE" and not watermark:
                continue
            # A queued run's event watermark is consumed only when the run ends:
            # published, or given up (followup_closed).
            run = AgentRun(
                id=str(uuid4()),
                conversation_id=conversation.id,
                input_through_seq=conversation.next_seq - 1,
                trigger="FOLLOWUP",
                trigger_watermark=watermark,
                trigger_fingerprint=fingerprint,
                status="QUEUED",
            )
            session.add(run)
            await session.flush()
            await promote(session, conversation)
