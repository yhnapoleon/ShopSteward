"""Opt-in loopback developer dashboard; all writes share simulator transactions."""

import ipaddress
from pathlib import Path as FilePath
from typing import Annotated

from asyncpg import PostgresError
from fastapi import APIRouter, Header, Path, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from simulator.console_backend import BackendBridge
from simulator.control_schemas import RunDetail, RunList, TriggerRequest, TriggerResult
from simulator.controls import get_run, list_runs, trigger_run
from simulator.repository import advance_run, create_run, list_events
from simulator.schemas import AdvanceResult, EventPage, ScenarioAdvance, ScenarioCreate, ScenarioRun

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
Id = Annotated[str, Path(min_length=1, max_length=128)]
STATIC = FilePath(__file__).parent / "static"


def local_request_allowed(request):
    try:
        if request.client is None or not ipaddress.ip_address(request.client.host).is_loopback:
            return False
    except ValueError:
        return False
    if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return False
    if request.url.path.startswith("/console/api/"):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return False
        if request.headers.get("sec-fetch-site") == "cross-site":
            return False
        if request.method not in {"GET", "HEAD"} and (
            request.headers.get("x-simulator-console") != "1"
            or request.headers.get("content-type", "").split(";")[0].strip() != "application/json"
        ):
            return False
    return True


def install_console(app):
    bridge = BackendBridge(app.state.settings)

    @app.middleware("http")
    async def console_boundary(request, call_next):
        if request.url.path == "/console" or request.url.path.startswith("/console/"):
            if not local_request_allowed(request):
                return JSONResponse(
                    {
                        "error": {
                            "code": "CONSOLE_LOCAL_ONLY",
                            "message": "Use the local same-origin dashboard",
                        }
                    },
                    status_code=403,
                )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
            return response
        return await call_next(request)

    router = APIRouter(prefix="/console/api", tags=["Local simulator console"])

    @router.get("/status")
    async def status():
        try:
            ready = await app.state.db.ready()
        except (OSError, TimeoutError, SQLAlchemyError, PostgresError):
            ready = False
        return {
            "simulator_ready": ready,
            "backend_configured": bridge.configured,
            "backend_url": app.state.settings.sim_backend_base_url,
            "backend_status": await bridge.health(),
            "synthetic": True,
        }

    @router.get("/runs", response_model=RunList)
    async def runs(
        before: Annotated[str | None, Query(max_length=2048)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ):
        async with app.state.db.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            return await list_runs(session, before, limit)

    @router.post(
        "/runs", status_code=201, response_model=ScenarioRun, response_model_exclude_unset=True
    )
    async def create(body: ScenarioCreate, key: Key):
        async with app.state.db.session() as session, session.begin():
            return await create_run(session, key, body.model_dump(exclude_none=True))

    @router.get("/runs/{run_id}", response_model=RunDetail)
    async def detail(run_id: Id):
        async with app.state.db.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            return await get_run(session, run_id)

    @router.get("/runs/{run_id}/events", response_model=EventPage)
    async def events(
        run_id: Id,
        after_sequence: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ):
        async with app.state.db.session() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            return await list_events(session, run_id, after_sequence, limit)

    @router.post("/runs/{run_id}/triggers", response_model=TriggerResult)
    async def trigger(run_id: Id, body: TriggerRequest, key: Key):
        async with app.state.db.session() as session, session.begin():
            return await trigger_run(session, run_id, key, body)

    @router.post("/runs/{run_id}/advance", response_model=AdvanceResult)
    async def advance(run_id: Id, body: ScenarioAdvance, key: Key):
        async with app.state.db.session() as session, session.begin():
            return await advance_run(session, run_id, key, body.model_dump())

    @router.post("/linked-runs", status_code=202)
    async def create_linked(body: ScenarioCreate, key: Key):
        return await bridge.create(body, key)

    @router.get("/jobs/{job_id}")
    async def job(job_id: Annotated[str, Path(min_length=1, max_length=128)]):
        return await bridge.job(job_id)

    @router.get("/runs/{run_id}/backend")
    async def backend(run_id: Id):
        async with app.state.db.session() as session:
            current = await get_run(session, run_id)
        return await bridge.observe(current["store_id"])

    app.include_router(router)

    @app.get("/console/", include_in_schema=False)
    async def page():
        return FileResponse(STATIC / "index.html")

    app.mount(
        "/console/static", StaticFiles(directory=STATIC, check_dir=False), name="console-static"
    )
