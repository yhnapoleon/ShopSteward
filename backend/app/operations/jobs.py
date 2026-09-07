from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.hashing import digest
from app.operations.client import SimulationClient
from app.operations.models import SourceCursor, SourceSchedule
from app.operations.repository import ingest, initialize, mark_caught_up, store_for_run
from app.operations.scheduling import queue_source
from app.operations.schemas import EventBatch
from app.scheduling.handlers import Handler


async def apply_page(session, run_id, after, page, key, receipts=None):
    sequences = [event.sequence for event in page.events]
    if (
        sequences != list(range(after + 1, after + 1 + len(sequences)))
        or page.last_sequence != (sequences[-1] if sequences else after)
        or page.source_head_sequence < page.last_sequence
        or page.has_more != (page.last_sequence < page.source_head_sequence)
        or (page.has_more and not sequences)
    ):
        raise AppError(503, "INVALID_SOURCE_PAGE", "Source page is not a contiguous head snapshot")
    store = await store_for_run(session, run_id)
    cursor = await session.get(SourceCursor, run_id)
    if cursor.last_sequence < after:
        raise AppError(409, "SOURCE_CURSOR_CONFLICT", "Local cursor precedes requested source page")
    if page.events:
        await ingest(
            session,
            EventBatch(source="simulation", scenario_run_id=run_id, events=page.events),
            command_scope="worker-sync",
            key=key,
            receipts=receipts,
        )
    if not page.has_more:
        await mark_caught_up(session, run_id, page.last_sequence)
    else:
        cursor.last_error = "SOURCE_CATCHING_UP"
        schedule = await session.get(SourceSchedule, (run_id, "sync_events"), with_for_update=True)
        schedule.rerun_requested = True
    return {
        "summary": "Source page synchronized",
        "references": [{"type": "store", "id": store.id}],
        "output_state_version": store.state_version,
    }


def make_handlers(settings, *, client=None):
    client = client or SimulationClient(settings)

    async def prepare_init(db, job):
        return await client.create(job.id, job.payload)

    async def apply_init(session, job, seed):
        store = await initialize(session, seed)
        await queue_source(session, store, key=digest(["initial-sync", job.id]))
        return {
            "summary": "Scenario initialized",
            "output_state_version": store.state_version,
            "references": [
                {"type": "scenario", "id": seed.scenario_run_id},
                {"type": "store", "id": store.id},
            ],
        }

    async def prepare_sync(db, job):
        run_id = job.payload["scenario_run_id"]
        async with db.session() as session:
            cursor = await session.scalar(
                select(SourceCursor).where(SourceCursor.scenario_run_id == run_id)
            )
            if cursor is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "Source run does not exist")
            after = cursor.last_sequence
        from app.execution.events import prepare_receipts

        page = await client.events(run_id, after)
        receipts = {}
        if page.events:
            batch = EventBatch(source="simulation", scenario_run_id=run_id, events=page.events)
            receipts = await prepare_receipts(db, batch, client)
        return after, page, receipts

    async def apply_sync(session, job, prepared):
        from app.missions.repository import wake_store_missions
        from app.planning.snapshot import source_fresh

        after, page, receipts = prepared
        store = await store_for_run(session, job.payload["scenario_run_id"])
        cursor = await session.get(SourceCursor, store.scenario_run_id)
        now = await session.scalar(select(func.clock_timestamp()))
        was_fresh = source_fresh(cursor, now, settings.source_stale_seconds)
        outcome = await apply_page(
            session, job.payload["scenario_run_id"], after, page, job.id, receipts
        )
        if not was_fresh and not page.has_more:
            await wake_store_missions(session, store, key="source-recovered:" + job.id)
        return outcome

    async def after_sync(session, job, outcome):
        store = await store_for_run(session, job.payload["scenario_run_id"])
        schedule = await session.get(
            SourceSchedule, (store.scenario_run_id, "sync_events"), with_for_update=True
        )
        if schedule.rerun_requested:
            await queue_source(session, store, key="sync-followup:" + job.id)

    async def sync_error(session, job, error):
        from app.execution.events import EventActionConflict, persist_conflict

        if isinstance(error, EventActionConflict):
            await persist_conflict(session, error)
        store = await store_for_run(session, job.payload["scenario_run_id"])
        cursor = await session.get(SourceCursor, store.scenario_run_id, with_for_update=True)
        cursor.last_error = error.code if isinstance(error, AppError) else "SOURCE_SYNC_FAILED"

    async def prepare_freshness(db, job):
        # Evaluate under the publication locks, so a concurrent successful sync wins.
        return None

    async def apply_freshness(session, job, prepared):
        from app.alerts.repository import reconcile
        from app.alerts.rules import inconclusive
        from app.missions.models import MissionRow
        from app.planning.snapshot import source_fresh

        store = await store_for_run(session, job.payload["scenario_run_id"])
        cursor = await session.get(SourceCursor, store.scenario_run_id)
        now = await session.scalar(select(func.clock_timestamp()))
        fresh = source_fresh(cursor, now, settings.source_stale_seconds)
        if not fresh:
            missions = await session.scalars(
                select(MissionRow)
                .where(
                    MissionRow.store_id == store.id,
                    MissionRow.status.in_(["ACTIVE", "PAUSED"]),
                )
                .order_by(MissionRow.id)
                .with_for_update()
            )
            for mission in missions:
                await reconcile(
                    session,
                    mission,
                    [inconclusive("DATA_STALE")],
                    {"DATA_STALE"},
                    store.state_version,
                )
        # Fresh source alone cannot prove an expired offer/forecast healthy; Mission check does.
        return {
            "summary": "Source freshness checked",
            "check_status": "HEALTHY" if fresh else "INCONCLUSIVE",
            "references": [{"type": "store", "id": store.id}],
        }

    async def prepare_advance(db, job):
        # Simulator command id is the persistent job id, including retries after
        # a lost response or expired lease. No backend transaction spans this call.
        run_id = job.payload["scenario_run_id"]
        result = await client.advance(run_id, job.id, {"steps": job.payload["steps"]})
        if result.scenario_run_id != run_id:
            raise AppError(
                503, "INVALID_SOURCE_RESPONSE", "Advance result belongs to another source run"
            )
        return result

    async def apply_advance(session, job, result):
        run_id = job.payload["scenario_run_id"]
        store = await store_for_run(session, run_id)
        await queue_source(session, store, key=digest(["advance-sync", job.id]))
        # World state and source cursor advance only through verified event ingestion.
        return {
            "summary": "Scenario advanced; source synchronization queued",
            "references": [
                {"type": "scenario", "id": run_id},
                {"type": "store", "id": store.id},
            ],
        }

    return {
        "initialize_scenario": Handler(prepare_init, retry_safe=True, apply=apply_init),
        "sync_events": Handler(
            prepare_sync,
            retry_safe=True,
            apply=apply_sync,
            on_error=sync_error,
            after_complete=after_sync,
        ),
        "check_freshness": Handler(prepare_freshness, retry_safe=True, apply=apply_freshness),
        "advance_scenario": Handler(prepare_advance, retry_safe=True, apply=apply_advance),
    }
