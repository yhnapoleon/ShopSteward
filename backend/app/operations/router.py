from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request

from app.api.dependencies import Admin, Service, User, authorize_store
from app.api.schemas import Error
from app.core.errors import AppError
from app.execution.schemas import ScenarioAdvance
from app.missions.schemas import JobAccepted
from app.operations import repository
from app.operations.schemas import (
    Catalog,
    EventBatch,
    EventBatchResult,
    ScenarioAccepted,
    ScenarioCreate,
)
from app.scheduling.repository import enqueue

router, dev_router = APIRouter(), APIRouter()
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
errors = {code: {"model": Error} for code in [401, 403, 404, 409, 422, 500, 503]}


@router.get(
    "/api/v1/catalog",
    response_model=Catalog,
    operation_id="get_catalog",
    tags=["Operations"],
    responses=errors,
)
async def catalog(
    request: Request, principal: User, store_id: Annotated[str, Query(min_length=1, max_length=128)]
):
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session:
        return await repository.get_catalog(session, store_id)


@router.post(
    "/internal/v1/events/batches",
    response_model=EventBatchResult,
    operation_id="ingest_event_batch",
    tags=["Operations"],
    responses=errors,
)
async def events(request: Request, principal: Service, body: EventBatch, key: Key):
    if body.scenario_run_id not in principal.scenario_run_ids:
        raise AppError(403, "FORBIDDEN", "Service is not authorized for this source run")
    from app.execution.events import EventActionConflict, persist_conflict, prepare_receipts
    from app.operations.client import SimulationClient

    db = request.app.state.db
    receipts = await prepare_receipts(db, body, SimulationClient(request.app.state.settings))
    try:
        async with db.session() as session, session.begin():
            return await repository.ingest(
                session, body, command_scope=principal.principal_id, key=key, receipts=receipts
            )
    except EventActionConflict as exc:
        # Preserve source evidence after rolling back the whole financial batch.
        async with db.session() as session, session.begin():
            await persist_conflict(session, exc)
        raise


@dev_router.post(
    "/dev/v1/scenarios",
    status_code=202,
    response_model=ScenarioAccepted,
    operation_id="create_dev_scenario",
    tags=["Development"],
    responses=errors,
)
async def create_scenario(request: Request, principal: Admin, body: ScenarioCreate, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        job = await enqueue(
            session,
            job_type="initialize_scenario",
            dedup_key=repository.digest(["initialize", principal.principal_id, key]),
            payload=body.model_dump(),
        )
        # Replay the original acceptance receipt; GET JobRun is the live status authority.
        return ScenarioAccepted(
            job_run_id=job.id, status="READY", scenario_run_id=None, store_id=None
        )


@dev_router.post(
    "/dev/v1/scenarios/{run_id}/advance",
    status_code=202,
    response_model=JobAccepted,
    operation_id="advance_dev_scenario",
    tags=["Development"],
    responses=errors,
)
async def advance_scenario(
    request: Request,
    principal: Admin,
    run_id: Annotated[str, Path(min_length=1, max_length=128)],
    body: ScenarioAdvance,
    key: Key,
):
    async with request.app.state.db.session() as session, session.begin():
        store = await repository.store_for_run(session, run_id)
        job = await enqueue(
            session,
            job_type="advance_scenario",
            store_id=store.id,
            dedup_key=repository.digest(["advance_dev_scenario", principal.principal_id, key]),
            payload={"scenario_run_id": run_id, **body.model_dump()},
        )
        # The acceptance response is immutable even after the job completes.
        return JobAccepted(job_run_id=job.id, status="READY", merged=False)


for route in [*router.routes, *dev_router.routes]:
    route.openapi_extra = {"x-phase": "B0", "x-implementation-status": "implemented"}
