from typing import Annotated

from fastapi import Query, Request
from sqlalchemy import func, select

from app.api.dependencies import (
    Cursor,
    Id,
    Key,
    Limit,
    User,
    authorize_store,
    require_role,
    visible_mission,
)
from app.api.routing import B0Router, errors
from app.core.errors import AppError
from app.missions import repository as repo
from app.missions.models import PlanRow
from app.missions.schemas import (
    CheckRequest,
    JobAccepted,
    Mission,
    MissionControl,
    MissionCreate,
    MissionList,
    MissionStatus,
    Schedule,
    ScheduleUpdate,
)
from app.planning.schemas import Plan, PlanList

router = B0Router(tags=["Missions"], responses=errors)


@router.post(
    "/api/v1/missions", status_code=201, response_model=Mission, operation_id="create_mission"
)
async def create(request: Request, principal: User, body: MissionCreate, key: Key):
    require_role(principal, "operator")
    authorize_store(principal, body.store_id)
    async with request.app.state.db.session() as session, session.begin():
        return await repo.create_mission(session, body, principal.principal_id, key)


@router.get("/api/v1/missions", response_model=MissionList, operation_id="list_missions")
async def listing(
    request: Request,
    principal: User,
    store_id: Annotated[str, Query(min_length=1, max_length=128)],
    status: MissionStatus | None = None,
    cursor: Cursor = None,
    limit: Limit = 20,
):
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session:
        return await repo.list_missions(session, store_id, status, cursor, limit)


@router.get("/api/v1/missions/{mission_id}", response_model=Mission, operation_id="get_mission")
async def detail(request: Request, principal: User, mission_id: Id):
    async with request.app.state.db.session() as session:
        await visible_mission(session, principal, mission_id)
        return await repo.read_mission(session, mission_id)


@router.post(
    "/api/v1/missions/{mission_id}/control", response_model=Mission, operation_id="control_mission"
)
async def control(
    request: Request, principal: User, mission_id: Id, body: MissionControl, key: Key
):
    require_role(principal, "approver" if body.operation in {"complete", "cancel"} else "operator")
    async with request.app.state.db.session() as session, session.begin():
        await visible_mission(session, principal, mission_id)
        return await repo.control_mission(session, mission_id, body, principal.principal_id, key)


@router.patch(
    "/api/v1/missions/{mission_id}/schedule",
    response_model=Schedule,
    operation_id="update_mission_schedule",
    tags=["Scheduling"],
)
async def update_schedule(
    request: Request, principal: User, mission_id: Id, body: ScheduleUpdate, key: Key
):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        await visible_mission(session, principal, mission_id)
        return await repo.update_schedule(session, mission_id, body, principal.principal_id, key)


@router.post(
    "/api/v1/missions/{mission_id}/checks",
    status_code=202,
    response_model=JobAccepted,
    operation_id="request_mission_check",
)
async def check(request: Request, principal: User, mission_id: Id, body: CheckRequest, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        await visible_mission(session, principal, mission_id)
        return await repo.request_check(session, mission_id, body, principal.principal_id, key)


@router.get(
    "/api/v1/missions/{mission_id}/plans",
    response_model=PlanList,
    operation_id="list_mission_plans",
)
async def plans(
    request: Request, principal: User, mission_id: Id, cursor: Cursor = None, limit: Limit = 20
):
    async with request.app.state.db.session() as session:
        await visible_mission(session, principal, mission_id)
        return await repo.list_plans(session, mission_id, cursor, limit)


@router.get(
    "/api/v1/plans/{plan_id}", response_model=Plan, operation_id="get_plan", tags=["Planning"]
)
async def plan(request: Request, principal: User, plan_id: Id):
    async with request.app.state.db.session() as session:
        row = await session.get(PlanRow, plan_id)
        if row is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Plan is not visible or does not exist")
        await visible_mission(session, principal, row.mission_id)
        now = await session.scalar(select(func.clock_timestamp()))
        return repo.plan_dto(row, now)
