from typing import Annotated

from fastapi import Query, Request
from sqlalchemy import select

from app.api.dependencies import Id, Key, Limit, User, require_role, visible_mission
from app.api.routing import B0Router, errors
from app.operations_cases import repository as repo
from app.operations_cases.models import CaseEventRow
from app.operations_cases.schemas import (
    CaseAnalyze,
    CaseControl,
    CaseCreate,
    CaseDetail,
    CaseEvents,
    CaseList,
    CaseMaterialize,
    CaseRevise,
)

router = B0Router(tags=["Recovery Cases"], responses=errors)


@router.post(
    "/api/v1/operations-cases",
    status_code=201,
    response_model=CaseDetail,
    operation_id="create_operations_case",
)
async def create(request: Request, principal: User, body: CaseCreate, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        await visible_mission(session, principal, body.mission_id)
        return await repo.create(session, body, principal, key)


@router.get(
    "/api/v1/operations-cases", response_model=CaseList, operation_id="list_operations_cases"
)
async def listing(
    request: Request,
    principal: User,
    store_id: Annotated[str, Query(min_length=1, max_length=128)],
    limit: Limit = 20,
):
    async with request.app.state.db.session() as session:
        return await repo.listing(session, principal, store_id, limit)


@router.get(
    "/api/v1/operations-cases/{case_id}",
    response_model=CaseDetail,
    operation_id="get_operations_case",
)
async def detail(request: Request, principal: User, case_id: Id):
    async with request.app.state.db.session() as session:
        return await repo.detail(session, await repo.visible(session, principal, case_id))


@router.post(
    "/api/v1/operations-cases/{case_id}/analyze",
    response_model=CaseDetail,
    operation_id="analyze_operations_case",
)
async def analyze(request: Request, principal: User, case_id: Id, body: CaseAnalyze, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        row = await repo.visible(session, principal, case_id, lock=True)
        result = await repo.analyze(session, row, body, principal, key, request.app.state.settings)
    if request.app.state.settings.agent_case_experts_enabled and result.proposal:
        from app.agent_bridge.context_cases import attach_case_experts

        return await attach_case_experts(
            request.app.state.db,
            request.app.state.settings,
            principal,
            case_id,
            result.current_revision,
            result.proposal.id,
        )
    return result


@router.post(
    "/api/v1/operations-cases/{case_id}/revise",
    response_model=CaseDetail,
    operation_id="revise_operations_case",
)
async def revise(request: Request, principal: User, case_id: Id, body: CaseRevise, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        row = await repo.visible(session, principal, case_id, lock=True)
        return await repo.revise(session, row, body, principal, key)


@router.post(
    "/api/v1/operations-cases/{case_id}/materialize",
    response_model=CaseDetail,
    operation_id="materialize_operations_case",
)
async def materialize(
    request: Request, principal: User, case_id: Id, body: CaseMaterialize, key: Key
):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        row = await repo.visible(session, principal, case_id, lock=True)
        return await repo.materialize(
            session, row, body, principal, key, request.app.state.settings
        )


@router.post(
    "/api/v1/operations-cases/{case_id}/control",
    response_model=CaseDetail,
    operation_id="control_operations_case",
)
async def control(request: Request, principal: User, case_id: Id, body: CaseControl, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        row = await repo.visible(session, principal, case_id, lock=True)
        return await repo.control(session, row, body, principal, key)


@router.get(
    "/api/v1/operations-cases/{case_id}/events",
    response_model=CaseEvents,
    operation_id="list_operations_case_events",
)
async def events(
    request: Request,
    principal: User,
    case_id: Id,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Limit = 100,
):
    async with request.app.state.db.session() as session:
        await repo.visible(session, principal, case_id)
        rows = list(
            await session.scalars(
                select(CaseEventRow)
                .where(CaseEventRow.case_id == case_id, CaseEventRow.seq > after_seq)
                .order_by(CaseEventRow.seq)
                .limit(limit)
            )
        )
        return CaseEvents(items=rows)
