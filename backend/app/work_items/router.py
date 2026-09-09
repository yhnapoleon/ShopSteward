from fastapi import Request
from sqlalchemy import func, or_, select

from app.api.dependencies import (
    Cursor,
    Id,
    Key,
    Limit,
    Service,
    User,
    authorize_store,
    require_role,
)
from app.api.routing import B0Router, errors
from app.core.errors import AppError
from app.reporting.read_router import read_transaction
from app.work_items import repository as repo
from app.work_items.models import WorkItem
from app.work_items.schemas import (
    WorkClaim,
    WorkContext,
    WorkControl,
    WorkCreate,
    WorkDetail,
    WorkInput,
    WorkLease,
    WorkList,
    WorkUpdate,
    WorkVersion,
)

router = B0Router(tags=["Work intake"], responses=errors)


@router.post(
    "/api/v1/work-items",
    response_model=WorkDetail,
    status_code=201,
    operation_id="create_work_item",
)
async def create(request: Request, principal: User, body: WorkCreate, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.create(session, principal, body, key, request.app.state.settings)


@router.get("/api/v1/work-items", response_model=WorkList, operation_id="list_work_items")
async def listing(
    request: Request, principal: User, store_id: str, cursor: Cursor = None, limit: Limit = 30
):
    async with read_transaction(request) as session:
        return await repo.listing(
            session, principal, store_id, cursor, limit, request.app.state.settings
        )


@router.get("/api/v1/work-items/{item_id}", response_model=WorkDetail, operation_id="get_work_item")
async def detail(request: Request, principal: User, item_id: Id):
    async with read_transaction(request) as session:
        return await repo.detail(
            session, await repo.visible(session, principal, item_id), request.app.state.settings
        )


@router.post(
    "/api/v1/work-items/{item_id}/messages",
    response_model=WorkDetail,
    operation_id="send_work_message",
)
async def send(request: Request, principal: User, item_id: Id, body: WorkInput, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.send(session, principal, item_id, body, key, request.app.state.settings)


@router.post(
    "/api/v1/missions/{mission_id}/work-item",
    response_model=WorkDetail,
    operation_id="open_mission_work_item",
)
async def from_mission(request: Request, principal: User, mission_id: Id, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.from_mission(session, principal, mission_id, request.app.state.settings)


@router.post(
    "/api/v1/work-items/{item_id}/mission",
    response_model=WorkDetail,
    operation_id="accept_work_mission",
)
async def accept(request: Request, principal: User, item_id: Id, body: WorkVersion, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.accept_mission(
            session, principal, item_id, body, key, request.app.state.settings
        )


@router.post(
    "/api/v1/work-items/{item_id}/control",
    response_model=WorkDetail,
    operation_id="control_work_item",
)
async def control(request: Request, principal: User, item_id: Id, body: WorkControl, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.control(
            session, principal, item_id, body, key, request.app.state.settings
        )


@router.get("/internal/v1/work-items", response_model=WorkList, operation_id="pending_work_items")
async def pending(request: Request, service: Service, store_id: str, limit: Limit = 30):
    require_role(service, "operator")
    authorize_store(service, store_id)
    owners = set()
    for grant in request.app.state.settings.auth_tokens:
        if grant.kind == "user":
            try:
                authorize_store(grant, store_id)
                owners.add(grant.principal_id)
            except AppError:
                continue
    async with read_transaction(request) as session:
        rows = list(
            await session.scalars(
                select(WorkItem)
                .where(
                    WorkItem.store_id == store_id,
                    WorkItem.canonical_id.is_(None),
                    WorkItem.principal_id.in_(owners),
                    WorkItem.status.in_(["RECEIVED", "PROCESSING"]),
                    or_(
                        WorkItem.processing_expires_at.is_(None),
                        WorkItem.processing_expires_at <= func.clock_timestamp(),
                    ),
                )
                .order_by(WorkItem.updated_at, WorkItem.id)
                .limit(limit)
            )
        )
        return {
            "items": [await repo.view(session, row, request.app.state.settings) for row in rows],
            "next_cursor": None,
            "processor_available": request.app.state.settings.work_processor_enabled,
        }


@router.post(
    "/internal/v1/work-items/{item_id}/claim",
    response_model=WorkLease,
    operation_id="claim_work_item",
)
async def claim(request: Request, service: Service, item_id: Id, body: WorkClaim, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.claim(session, service, item_id, body, key, request.app.state.settings)


@router.post(
    "/internal/v1/work-items/{item_id}/updates",
    response_model=WorkDetail,
    operation_id="publish_work_update",
)
async def publish(request: Request, service: Service, item_id: Id, body: WorkUpdate, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        return await repo.publish(session, service, item_id, body, key, request.app.state.settings)


@router.get(
    "/internal/v1/work-items/{item_id}/context",
    response_model=WorkContext,
    operation_id="read_work_context",
)
async def context(request: Request, service: Service, item_id: Id, mission_cursor: Cursor = None):
    from app.missions import repository as missions
    from app.operations.repository import get_catalog
    from app.reporting.repository import dashboard

    require_role(service, "operator")
    async with read_transaction(request) as session:
        row = await repo.visible(session, service, item_id, service=True)
        repo.current_owner(request.app.state.settings, row)
        return WorkContext(
            work=await repo.detail(session, row, request.app.state.settings),
            catalog=await get_catalog(session, row.store_id),
            dashboard=await dashboard(session, row.store_id, request.app.state.settings),
            missions=await missions.list_missions(session, row.store_id, None, mission_cursor, 30),
        )
