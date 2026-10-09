"""Resolve applicability from authoritative rows, never model-supplied conditions."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.execution.models import ActionRow
from app.learning.retrieval import retrieve
from app.learning.schemas import LearningScope
from app.missions.models import MissionRow
from app.operations.models import SourceCursor
from app.operations_cases.models import CaseRow
from app.planning.snapshot import source_fresh


async def for_conversation(session, conversation, run_id, settings, principal):
    if not settings.learning_enabled:
        return []

    async def empty_selection():
        from app.learning.repository import policy
        from app.learning.run_binding import pin, selection

        scope = LearningScope(principal_id=principal.principal_id, store_id=conversation.store_id)
        pol = await policy(session, scope, lock=True)
        if not await selection(session, scope, run_id):
            await pin(session, scope, run_id, pol, [])
        return []

    mission = await session.get(MissionRow, conversation.mission_id)
    if not mission or mission.status != "ACTIVE":
        return await empty_selection()
    cases = list(
        await session.scalars(
            select(CaseRow)
            .where(
                CaseRow.mission_id == mission.id,
                CaseRow.owner_id == principal.principal_id,
                CaseRow.status.notin_(["CLOSED", "CANCELLED"]),
            )
            .order_by(CaseRow.updated_at.desc())
            .limit(2)
        )
    )
    # Ambiguous case selection cannot be resolved from a guessed user intent.
    if len(cases) > 1:
        return await empty_selection()
    cursor = await session.scalar(
        select(SourceCursor).where(SourceCursor.store_id == conversation.store_id)
    )
    fresh = bool(source_fresh(cursor, datetime.now(UTC), settings.source_stale_seconds))
    actions = list(
        await session.scalars(
            select(ActionRow).where(
                ActionRow.mission_id == mission.id,
                ActionRow.status.in_(["UNKNOWN", "QUEUED", "EXECUTING"]),
            )
        )
    )
    facts = {
        "current_mission": True,
        "current_case": bool(cases),
        "authoritative_snapshot_current": fresh,
        "stale_snapshot": not fresh,
        "unknown_execution": bool(actions),
        "missing_eta": any("eta" in str(v).lower() for v in cases[0].missing_inputs)
        if cases
        else None,
    }
    return await retrieve(
        session,
        scope=LearningScope(principal_id=principal.principal_id, store_id=conversation.store_id),
        family="supply_delay_recovery" if cases else "replenishment",
        facts=facts,
        settings=settings,
        principal=principal,
        run_id=run_id,
    )
