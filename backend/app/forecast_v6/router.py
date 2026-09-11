from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Request

from app.api.dependencies import Id, User, require_role
from app.api.routing import errors
from app.core.errors import AppError
from app.forecast_v6 import repository as repo
from app.forecast_v6.client import connect, json_request
from app.forecast_v6.schemas import (
    ForecastV6Current,
    ForecastV6Model,
    ForecastV6Refresh,
    HistoryDay,
    validate_history,
)

router = APIRouter(tags=["Forecast v6"], responses=errors)


@router.get(
    "/api/v1/stores/{store_id}/forecast/model",
    response_model=ForecastV6Model,
    operation_id="get_forecast_v6_model",
)
async def model(request: Request, principal: User, store_id: Id):
    async with request.app.state.db.session() as session:
        await repo.scope(session, principal, store_id)
    async with connect(request.app.state.settings) as client:
        result = await json_request(client, "GET", "/v1/model")
    try:
        return ForecastV6Model.model_validate(result)
    except ValueError as exc:
        raise AppError(503, "FORECAST_INVALID_EVIDENCE", "Invalid v6 model descriptor") from exc


@router.get(
    "/api/v1/stores/{store_id}/forecast",
    response_model=ForecastV6Current,
    operation_id="get_forecast_v6",
)
async def current(
    request: Request,
    principal: User,
    store_id: Id,
    sku_id: Annotated[str, Query(min_length=1, max_length=128)],
):
    async with request.app.state.db.session() as session:
        await repo.scope(session, principal, store_id, sku_id)
        return await repo.read_current(session, store_id, sku_id, request.app.state.settings)


@router.post(
    "/api/v1/stores/{store_id}/forecast/refresh",
    response_model=ForecastV6Current,
    operation_id="refresh_forecast_v6",
)
async def refresh(request: Request, principal: User, store_id: Id, body: ForecastV6Refresh):
    require_role(principal, "operator")
    settings = request.app.state.settings
    async with request.app.state.db.session() as session:
        captured = await repo.capture(session, principal, store_id, body)
    # No database transaction or business lock survives across model-service HTTP.
    async with connect(settings) as client:
        descriptor = await json_request(client, "GET", "/v1/model")
        if captured["mode"] == "historical_demo":
            demo = await json_request(
                client, "GET", "/v1/demo-history/" + quote(captured["series_id"], safe="")
            )
            try:
                if (
                    demo["series_id"] != captured["series_id"]
                    or demo["source_kind"] != "historical_demo"
                ):
                    raise ValueError("Historical series mismatch")
                validate_history(
                    [HistoryDay.model_validate(row) for row in demo["history"]],
                    date.fromisoformat(demo["observation_end_date"]),
                )
                captured.update(
                    history=demo["history"], observation_end_date=demo["observation_end_date"]
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise AppError(
                    503, "FORECAST_INVALID_EVIDENCE", "Invalid packaged demo history"
                ) from exc
        payload = {
            key: captured[key]
            for key in ("store_id", "sku_id", "series_id", "history", "observation_end_date")
        }
        payload.update(timezone="UTC", input_state_version=captured["state_version"])
        prediction = await json_request(client, "POST", "/v1/predict", json=payload)
    async with request.app.state.db.session() as session, session.begin():
        await repo.persist(session, principal, captured, prediction, descriptor)
        return await repo.read_current(session, store_id, body.sku_id, settings)
