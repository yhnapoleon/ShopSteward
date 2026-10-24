from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select
from test_periodic import clean_queue  # noqa: F401

from app.missions.models import MissionRow, ScheduleRow
from app.operations.models import SourceCursor, SourceSchedule, Store
from app.scheduling.dispatcher import dispatch_due
from app.scheduling.models import Job

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["source", "mission"])
async def test_locked_oldest_page_cannot_starve_later_unlocked_store(db, kind):
    """100 locked oldest stores must not hide the 101st runnable occurrence."""
    prefix = uuid4().hex
    ids = [f"fair-{prefix}-{index:03}" for index in range(101)]
    async with db.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp()))
        anchors = [now - timedelta(seconds=300 - index) for index in range(101)]
        await session.execute(
            insert(Store),
            [
                dict(
                    id=identifier,
                    scenario_run_id=identifier,
                    initial_hash="0" * 64,
                    currency="CNY",
                    cash_minor=100000,
                    reserved_cash_minor=0,
                    receivables_minor=0,
                    state_version=1,
                )
                for identifier in ids
            ],
        )
        if kind == "source":
            await session.execute(
                insert(SourceCursor),
                [
                    dict(
                        scenario_run_id=identifier,
                        store_id=identifier,
                        source="simulation",
                        last_sequence=0,
                    )
                    for identifier in ids
                ],
            )
            await session.execute(
                insert(SourceSchedule),
                [
                    dict(
                        scenario_run_id=identifier,
                        job_type="sync_events",
                        interval_seconds=5,
                        next_run_at=anchor,
                        rerun_requested=False,
                    )
                    for identifier, anchor in zip(ids, anchors, strict=True)
                ],
            )
        else:
            await session.execute(
                insert(MissionRow),
                [
                    dict(
                        id=identifier,
                        store_id=identifier,
                        sku_id="sku",
                        objective="fair dispatch",
                        status="ACTIVE",
                        mission_version=1,
                        policy={},
                        policy_version="1",
                        completion_criteria="manual",
                        created_at=now,
                        updated_at=now,
                    )
                    for identifier in ids
                ],
            )
            await session.execute(
                insert(ScheduleRow),
                [
                    dict(
                        id=identifier,
                        mission_id=identifier,
                        job_type="check_mission",
                        trigger="INTERVAL",
                        interval_seconds=5,
                        enabled=True,
                        version=1,
                        next_run_at=anchor,
                    )
                    for identifier, anchor in zip(ids, anchors, strict=True)
                ],
            )
    async with db.session() as busy, busy.begin():
        await busy.execute(select(Store.id).where(Store.id.in_(ids[:100])).with_for_update())
        await dispatch_due(db)
        async with db.session() as session:
            ready = list(await session.scalars(select(Job).where(Job.store_id.in_(ids))))
            assert len(ready) == 1 and ready[0].store_id == ids[-1]
            if kind == "source":
                locked = await session.get(SourceSchedule, (ids[0], "sync_events"))
            else:
                locked = await session.get(ScheduleRow, ids[0])
            assert locked.next_run_at == anchors[0]
