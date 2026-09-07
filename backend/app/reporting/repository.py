from sqlalchemy import func, select, tuple_

from app.alerts.models import AlertRow
from app.core.pagination import decode_cursor, encode_cursor
from app.missions.models import MissionRow, ScheduleRow, TimelineRow
from app.operations.models import SourceCursor
from app.operations.repository import get_state
from app.planning.snapshot import source_fresh
from app.reporting.schemas import Dashboard, Freshness, TimelineEntry, TimelineEntryList
from app.scheduling.models import Job


async def dashboard(session, store_id, settings):
    """The route owns a read-only REPEATABLE READ transaction for this entire response."""
    state = await get_state(session, store_id)
    cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == store_id))
    now = await session.scalar(select(func.clock_timestamp()))
    status = "UNKNOWN"
    if cursor:
        if source_fresh(cursor, now, settings.source_stale_seconds):
            status = "FRESH"
        elif cursor.last_success_at is not None or cursor.last_error is not None:
            status = "STALE"
    missions = await session.scalar(
        select(func.count())
        .select_from(MissionRow)
        .where(MissionRow.store_id == store_id, MissionRow.status == "ACTIVE")
    )
    alerts = await session.scalar(
        select(func.count())
        .select_from(AlertRow)
        .where(AlertRow.store_id == store_id, AlertRow.status.in_(["OPEN", "ACKNOWLEDGED"]))
    )
    last = await session.scalar(
        select(func.max(Job.finished_at)).where(
            Job.store_id == store_id,
            Job.job_type == "check_mission",
            Job.status == "SUCCEEDED",
            Job.result["check_status"].astext.in_(["HEALTHY", "ANOMALY", "INCONCLUSIVE"]),
        )
    )
    queued = await session.scalar(
        select(func.min(func.greatest(Job.scheduled_for, Job.available_at)))
        .join(MissionRow, MissionRow.id == Job.mission_id)
        .where(
            Job.store_id == store_id,
            Job.job_type == "check_mission",
            Job.status.in_(["READY", "RETRY_WAIT"]),
            MissionRow.status == "ACTIVE",
        )
    )
    scheduled = await session.scalar(
        select(func.min(ScheduleRow.next_run_at))
        .join(MissionRow, MissionRow.id == ScheduleRow.mission_id)
        .where(
            MissionRow.store_id == store_id,
            MissionRow.status == "ACTIVE",
            ScheduleRow.enabled.is_(True),
            ScheduleRow.job_type == "check_mission",
        )
    )
    upcoming = [time for time in (queued, scheduled) if time is not None]
    return Dashboard(
        state=state,
        freshness=Freshness(
            status=status,
            data_as_of=state.data_as_of,
            last_sync_at=cursor.last_success_at if cursor else None,
        ),
        active_mission_count=missions,
        active_alert_count=alerts,
        last_check_at=last,
        next_check_at=min(upcoming) if upcoming else None,
    )


async def list_timeline(session, mission_id, cursor, limit):
    scope = ["timeline", mission_id]
    anchor = decode_cursor(cursor, scope)
    query = select(TimelineRow).where(TimelineRow.mission_id == mission_id)
    if anchor:
        query = query.where(tuple_(TimelineRow.created_at, TimelineRow.id) < anchor)
    rows = list(
        await session.scalars(
            query.order_by(TimelineRow.created_at.desc(), TimelineRow.id.desc()).limit(limit + 1)
        )
    )
    return TimelineEntryList(
        items=[TimelineEntry.model_validate(row) for row in rows[:limit]],
        next_cursor=encode_cursor(scope, rows[limit - 1]) if len(rows) > limit else None,
    )
