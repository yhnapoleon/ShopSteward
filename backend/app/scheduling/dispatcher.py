"""Durable fixed-anchor dispatch; each occurrence commits in a short transaction."""

from datetime import timedelta

from sqlalchemy import func, select

from app.missions.models import MissionRow, ScheduleRow
from app.missions.repository import queue_check
from app.operations.models import SourceCursor, SourceSchedule, Store
from app.operations.scheduling import queue_source


def due_occurrence(anchor, interval_seconds, now):
    interval = timedelta(seconds=interval_seconds)
    scheduled_for = anchor + ((now - anchor) // interval) * interval
    return scheduled_for, scheduled_for + interval


async def dispatch_due(db):
    # Skip busy stores before LIMIT, otherwise a locked first page starves later work.
    # These discovery locks are released before individual dispatch transactions.
    async with db.session() as session:
        missions = (
            await session.execute(
                select(ScheduleRow.id, MissionRow.id, MissionRow.store_id)
                .join(MissionRow, MissionRow.id == ScheduleRow.mission_id)
                .join(Store, Store.id == MissionRow.store_id)
                .where(
                    ScheduleRow.enabled.is_(True),
                    ScheduleRow.next_run_at <= func.clock_timestamp(),
                    MissionRow.status == "ACTIVE",
                )
                .order_by(ScheduleRow.next_run_at, ScheduleRow.id)
                .limit(100)
                .with_for_update(of=Store, skip_locked=True)
            )
        ).all()
        sources = (
            await session.execute(
                select(
                    SourceSchedule.scenario_run_id, SourceSchedule.job_type, SourceCursor.store_id
                )
                .join(SourceCursor, SourceCursor.scenario_run_id == SourceSchedule.scenario_run_id)
                .join(Store, Store.id == SourceCursor.store_id)
                .where(SourceSchedule.next_run_at <= func.clock_timestamp())
                .order_by(
                    SourceSchedule.next_run_at,
                    SourceSchedule.scenario_run_id,
                    SourceSchedule.job_type,
                )
                .limit(100)
                .with_for_update(of=Store, skip_locked=True)
            )
        ).all()
    count = 0
    for kind, rows in (("source", sources), ("mission", missions)):
        for identity, scope, store_id in rows:
            async with db.session() as session, session.begin():
                store = await session.scalar(
                    select(Store).where(Store.id == store_id).with_for_update(skip_locked=True)
                )
                if store is None:
                    continue
                if kind == "mission":
                    mission = await session.get(MissionRow, scope, with_for_update=True)
                    schedule = await session.get(ScheduleRow, identity, with_for_update=True)
                    if mission.status != "ACTIVE" or not schedule.enabled:
                        continue
                else:
                    schedule = await session.get(
                        SourceSchedule, (identity, scope), with_for_update=True
                    )
                now = await session.scalar(select(func.clock_timestamp()))
                if schedule.next_run_at is None or schedule.next_run_at > now:
                    continue
                occurrence, following = due_occurrence(
                    schedule.next_run_at, schedule.interval_seconds, now
                )
                key = f"interval:{identity}:{scope}:{occurrence.isoformat()}"
                if kind == "mission":
                    await queue_check(
                        session,
                        store,
                        mission,
                        key=key,
                        trigger_source="INTERVAL",
                        scheduled_for=occurrence,
                    )
                else:
                    await queue_source(
                        session,
                        store,
                        key=key,
                        job_type=scope,
                        trigger_source="INTERVAL",
                        scheduled_for=occurrence,
                    )
                schedule.next_run_at = following
                count += 1
    return count
