from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.agent_bridge.models import AgentRun, Conversation, Trigger
from app.agent_bridge.repository import promote
from app.core.hashing import digest
from app.missions.models import MissionRow
from app.operations.models import Store


async def record_event(session, mission_id, source_key, references):
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


async def dispatch_followups(db, settings):
    if not settings.agent_enabled:
        return
    async with db.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp()))
        conversations = (
            await session.scalars(
                select(Conversation)
                .where(Conversation.followup_enabled.is_(True), Conversation.next_due <= now)
                .with_for_update(skip_locked=True, key_share=True)
                .limit(50)
            )
        ).all()
        for conversation in conversations:
            conversation.next_due = now + timedelta(seconds=conversation.followup_interval)
            mission = await session.get(MissionRow, conversation.mission_id)
            store = await session.get(Store, conversation.store_id)
            watermark = (
                await session.scalar(
                    select(func.max(Trigger.seq)).where(
                        Trigger.conversation_id == conversation.id,
                        Trigger.seq > conversation.consumed_trigger,
                    )
                )
                or 0
            )
            fingerprint = digest(
                [
                    store.state_version,
                    mission.mission_version,
                    mission.current_plan_id,
                    mission.current_action_id,
                    mission.status,
                ]
            )
            if conversation.active_run_id:
                continue
            if fingerprint == conversation.last_fingerprint and not watermark:
                continue
            if mission.status != "ACTIVE" and not watermark:
                continue
            # Do not consume event watermark until response is durably published.
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
