import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from asyncpg import PostgresError
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from simulator.config import Settings
from simulator.control_schemas import RunDetail, RunList, TriggerRequest, TriggerResult
from simulator.controls import get_run, list_runs, trigger_run
from simulator.db import Database
from simulator.repository import advance_run, create_run, get_purchase, list_events, submit_purchase
from simulator.schemas import (
    AdvanceResult,
    EventPage,
    PurchaseReceipt,
    PurchaseRequest,
    ScenarioAdvance,
    ScenarioCreate,
    ScenarioRun,
)

bearer = HTTPBearer(scheme_name="ServiceBearer", auto_error=False)


def authenticate(
    request: Request, credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    token = request.app.state.settings.sim_service_token
    if (
        token is None
        or credential is None
        or not secrets.compare_digest(
            credential.credentials.encode(), token.get_secret_value().encode()
        )
    ):
        raise HTTPException(401, "UNAUTHENTICATED")


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        yield
        await app.state.db.dispose()

    app = FastAPI(title="ShopSteward Simulator", version="0.3.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(
        settings.sim_database_url.get_secret_value() if settings.sim_database_url else None
    )

    @app.middleware("http")
    async def context(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    async def error(request, exc):
        status = (
            exc.status_code
            if isinstance(exc, StarletteHTTPException)
            else (422 if isinstance(exc, RequestValidationError) else 503)
        )
        code = (
            exc.detail
            if isinstance(exc, HTTPException)
            else ("VALIDATION_ERROR" if status == 422 else "DEPENDENCY_UNAVAILABLE")
        )
        return JSONResponse(
            {
                "error": {
                    "code": code,
                    "message": "Simulator request failed",
                    "request_id": request.state.request_id,
                    "retryable": status == 503,
                    "details": {},
                }
            },
            status_code=status,
        )

    for kind in [
        StarletteHTTPException,
        RequestValidationError,
        SQLAlchemyError,
        PostgresError,
        OSError,
        TimeoutError,
    ]:
        app.add_exception_handler(kind, error)

    @app.get("/health/ready")
    async def ready():
        try:
            available = await app.state.db.ready()
        except (OSError, TimeoutError, SQLAlchemyError, PostgresError):
            available = False
        return JSONResponse(
            {"status": "ok" if available else "unavailable", "component": "simulation"},
            status_code=200 if available else 503,
        )

    @app.post(
        "/sim/v1/runs",
        status_code=201,
        operation_id="simulation_create_run",
        response_model=ScenarioRun,
        response_model_exclude_unset=True,
        dependencies=[Depends(authenticate)],
    )
    async def create(
        body: ScenarioCreate,
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    ):
        async with app.state.db.session() as session, session.begin():
            return await create_run(session, key, body.model_dump(exclude_none=True))

    @app.get(
        "/sim/v1/runs",
        operation_id="simulation_list_runs",
        response_model=RunList,
        dependencies=[Depends(authenticate)],
    )
    async def runs(
        before: Annotated[str | None, Query(max_length=2048)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ):
        async with app.state.db.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            return await list_runs(session, before, limit)

    @app.get(
        "/sim/v1/runs/{run_id}",
        operation_id="simulation_get_run",
        response_model=RunDetail,
        dependencies=[Depends(authenticate)],
    )
    async def run_detail(run_id: Annotated[str, Path(min_length=1, max_length=128)]):
        async with app.state.db.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            return await get_run(session, run_id)

    @app.post(
        "/sim/v1/runs/{run_id}/triggers",
        operation_id="simulation_trigger",
        response_model=TriggerResult,
        dependencies=[Depends(authenticate)],
    )
    async def trigger(
        run_id: Annotated[str, Path(min_length=1, max_length=128)],
        body: TriggerRequest,
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    ):
        async with app.state.db.session() as session, session.begin():
            return await trigger_run(session, run_id, key, body)

    @app.get(
        "/sim/v1/runs/{run_id}/events",
        operation_id="simulation_list_events",
        response_model=EventPage,
        dependencies=[Depends(authenticate)],
    )
    async def events(
        run_id: Annotated[str, Path(min_length=1, max_length=128)],
        after_sequence: Annotated[int, Query(ge=0, le=9223372036854775807)],
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ):
        async with app.state.db.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            return await list_events(session, run_id, after_sequence, limit)

    @app.post(
        "/sim/v1/purchases",
        operation_id="simulation_purchase",
        response_model=PurchaseReceipt,
        dependencies=[Depends(authenticate)],
    )
    async def purchase(
        body: PurchaseRequest,
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    ):
        async with app.state.db.session() as session, session.begin():
            return await submit_purchase(session, key, body.model_dump())

    @app.get(
        "/sim/v1/purchases/{action_id}",
        operation_id="simulation_get_purchase",
        response_model=PurchaseReceipt,
        dependencies=[Depends(authenticate)],
    )
    async def receipt(action_id: Annotated[str, Path(min_length=1, max_length=128)]):
        async with app.state.db.session() as session:
            return await get_purchase(session, action_id)

    @app.post(
        "/sim/v1/runs/{run_id}/advance",
        operation_id="simulation_advance",
        response_model=AdvanceResult,
        dependencies=[Depends(authenticate)],
    )
    async def advance(
        run_id: Annotated[str, Path(min_length=1, max_length=128)],
        body: ScenarioAdvance,
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    ):
        async with app.state.db.session() as session, session.begin():
            return await advance_run(session, run_id, key, body.model_dump())

    if settings.sim_console_enabled:
        from simulator.console import install_console

        install_console(app)
    return app


app = create_app()
