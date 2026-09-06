from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from app.api.dependencies import User, authorize_store
from app.missions.router import Cursor, Id, Limit, visible_mission
from app.operations.router import errors
from app.reporting import repository as repo
from app.reporting.schemas import Dashboard, TimelineEntryList

router = APIRouter(tags=["Dashboard and history"], responses=errors)


@router.get("/api/v1/dashboard", response_model=Dashboard, operation_id="get_dashboard")
async def dashboard(
    request: Request, principal: User, store_id: Annotated[str, Query(min_length=1, max_length=128)]
):
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        return await repo.dashboard(session, store_id, request.app.state.settings)


@router.get(
    "/api/v1/missions/{mission_id}/timeline",
    response_model=TimelineEntryList,
    response_model_exclude_unset=True,
    operation_id="list_mission_timeline",
)
async def timeline(
    request: Request, principal: User, mission_id: Id, cursor: Cursor = None, limit: Limit = 20
):
    async with request.app.state.db.session() as session:
        await visible_mission(session, principal, mission_id)
        return await repo.list_timeline(session, mission_id, cursor, limit)
