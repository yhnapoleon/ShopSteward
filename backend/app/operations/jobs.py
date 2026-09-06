from sqlalchemy import select

from app.core.errors import AppError
from app.operations.client import SimulationClient
from app.operations.models import SourceCursor
from app.operations.repository import digest, ingest, initialize, mark_caught_up, store_for_run
from app.operations.schemas import EventBatch
from app.scheduling.handlers import Handler
from app.scheduling.repository import enqueue


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
        await enqueue(
            session,
            job_type="sync_events",
            store_id=store.id,
            dedup_key=digest(["sync-page", key, page.last_sequence]),
            payload={"scenario_run_id": run_id},
        )
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
        await enqueue(
            session,
            job_type="sync_events",
            store_id=store.id,
            dedup_key=digest(["initial-sync", job.id]),
            payload={"scenario_run_id": seed.scenario_run_id},
        )
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
        after, page, receipts = prepared
        return await apply_page(
            session, job.payload["scenario_run_id"], after, page, job.id, receipts
        )

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
        await enqueue(
            session,
            job_type="sync_events",
            store_id=store.id,
            dedup_key=digest(["advance-sync", job.id]),
            payload={"scenario_run_id": run_id},
        )
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
        "sync_events": Handler(prepare_sync, retry_safe=True, apply=apply_sync),
        "advance_scenario": Handler(prepare_advance, retry_safe=True, apply=apply_advance),
    }
