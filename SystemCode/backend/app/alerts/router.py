from typing import Annotated

from fastapi import Query, Request

from app.alerts import repository as repo
from app.alerts.models import AlertRow
from app.alerts.schemas import Alert, AlertList, AlertStatus
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
from app.operations.models import Store

router = B0Router(tags=["Alerts"], responses=errors)


@router.get(
    "/api/v1/alerts",
    response_model=AlertList,
    response_model_exclude_unset=True,
    operation_id="list_alerts",
)
async def listing(
    request: Request,
    principal: User,
    store_id: Annotated[str, Query(min_length=1, max_length=128)],
    mission_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    status: AlertStatus | None = None,
    cursor: Cursor = None,
    limit: Limit = 20,
):
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session:
        if await session.get(Store, store_id) is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Store does not exist")
        if mission_id:
            mission = await visible_mission(session, principal, mission_id)
            if mission.store_id != store_id:
                raise AppError(404, "RESOURCE_NOT_FOUND", "Mission does not belong to this store")
        return await repo.list_alerts(session, store_id, mission_id, status, cursor, limit)


@router.post(
    "/api/v1/alerts/{alert_id}/acknowledgement",
    response_model=Alert,
    response_model_exclude_unset=True,
    operation_id="acknowledge_alert",
)
async def acknowledge(request: Request, principal: User, alert_id: Id, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        row = await session.get(AlertRow, alert_id)
        if row is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Alert does not exist")
        authorize_store(principal, row.store_id)
        return await repo.acknowledge(session, alert_id, principal.principal_id, key)
