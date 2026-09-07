import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Query, Request
from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)
from sqlalchemy import text

from app.api.dependencies import User, authorize_store
from app.api.routing import B0Router, errors
from app.api.schemas import Identifier
from app.core.errors import AppError
from app.reporting import read_repository as repo
from app.reporting.read_schemas import (
    ActionList,
    InboundList,
    LedgerEntryList,
    SaleList,
    SaleSummary,
)

router = B0Router(tags=["Frontend data"], responses=errors)


def iso_date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value
    ):
        raise ValueError("Expected an ISO date-time with timezone")
    try:
        return datetime.fromisoformat(value.upper()).astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Date-time is outside the supported range") from exc


QueryDate = Annotated[AwareDatetime, BeforeValidator(iso_date)]


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)


class StoreQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_id: Identifier


class SaleQuery(StoreQuery, PageQuery):
    sku_id: Identifier | None = None
    start: QueryDate | None = Field(default=None, alias="from")
    end: QueryDate | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def date_range(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("from and to must be provided together")
        if self.start is not None:
            self.start, self.end = self.start.astimezone(UTC), self.end.astimezone(UTC)
            if not self.start < self.end or self.end - self.start > timedelta(days=90):
                raise ValueError("Expected a positive interval of at most 90 days")
        return self


class SummaryQuery(StoreQuery):
    sku_id: Identifier | None = None
    start: QueryDate = Field(alias="from")
    end: QueryDate = Field(alias="to")

    @model_validator(mode="after")
    def date_range(self):
        self.start, self.end = self.start.astimezone(UTC), self.end.astimezone(UTC)
        if not self.start < self.end or self.end - self.start > timedelta(days=90):
            raise ValueError("Expected a positive interval of at most 90 days")
        return self


class ActionQuery(StoreQuery, PageQuery):
    mission_id: Identifier | None = None
    sku_id: Identifier | None = None
    status: (
        Literal["QUEUED", "EXECUTING", "SUCCEEDED", "FAILED", "UNKNOWN", "STALE", "CANCELLED"]
        | None
    ) = None


class InboundQuery(StoreQuery, PageQuery):
    mission_id: Identifier | None = None
    sku_id: Identifier | None = None
    arrival_status: Literal["NOT_RECEIVED", "PARTIALLY_RECEIVED", "RECEIVED"] | None = None


class LedgerQuery(StoreQuery, PageQuery):
    effect_type: (
        Literal["INIT", "PURCHASE_ACCEPTED", "GOODS_RECEIVED", "SALE_RECORDED", "DEMAND_REVISED"]
        | None
    ) = None


def unique_query(request):
    keys = list(request.query_params.keys())
    if any(len(request.query_params.getlist(key)) != 1 for key in keys):
        raise AppError(422, "VALIDATION_ERROR", "Query parameters must not be repeated")


@asynccontextmanager
async def read_transaction(request):
    unique_query(request)
    async with request.app.state.db.session() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        try:
            yield session
        except ValidationError as exc:
            raise AppError(503, "INVALID_STORED_DATA", "Stored data cannot be read") from exc


async def context(session, request, principal, query):
    authorize_store(principal, query.store_id)
    return await repo.read_context(
        session,
        query.store_id,
        request.app.state.settings,
        sku_id=getattr(query, "sku_id", None),
        mission_id=getattr(query, "mission_id", None),
    )


@router.get(
    "/api/v1/sales",
    response_model=SaleList,
    operation_id="list_sales",
    openapi_extra={"x-work-package": "frontend-data-v1"},
)
async def sales(request: Request, principal: User, query: Annotated[SaleQuery, Query()]):
    async with read_transaction(request) as session:
        ctx = await context(session, request, principal, query)
        return await repo.list_sales(
            session,
            principal,
            ctx,
            sku_id=query.sku_id,
            start=query.start,
            end=query.end,
            limit=query.limit,
            cursor=query.cursor,
        )


@router.get(
    "/api/v1/sales/summary",
    response_model=SaleSummary,
    operation_id="get_sales_summary",
    openapi_extra={"x-work-package": "frontend-data-v1"},
)
async def sales_summary(request: Request, principal: User, query: Annotated[SummaryQuery, Query()]):
    async with read_transaction(request) as session:
        ctx = await context(session, request, principal, query)
        return await repo.summarize_sales(
            session, ctx, sku_id=query.sku_id, start=query.start, end=query.end
        )


@router.get(
    "/api/v1/actions",
    response_model=ActionList,
    operation_id="list_actions",
    openapi_extra={"x-work-package": "frontend-data-v1"},
)
async def actions(request: Request, principal: User, query: Annotated[ActionQuery, Query()]):
    async with read_transaction(request) as session:
        ctx = await context(session, request, principal, query)
        return await repo.list_actions(
            session,
            principal,
            ctx,
            mission_id=query.mission_id,
            sku_id=query.sku_id,
            status=query.status,
            limit=query.limit,
            cursor=query.cursor,
        )


@router.get(
    "/api/v1/inbounds",
    response_model=InboundList,
    operation_id="list_inbounds",
    openapi_extra={"x-work-package": "frontend-data-v1"},
)
async def inbounds(request: Request, principal: User, query: Annotated[InboundQuery, Query()]):
    async with read_transaction(request) as session:
        ctx = await context(session, request, principal, query)
        return await repo.list_inbounds(
            session,
            principal,
            ctx,
            mission_id=query.mission_id,
            sku_id=query.sku_id,
            arrival_status=query.arrival_status,
            limit=query.limit,
            cursor=query.cursor,
        )


@router.get(
    "/api/v1/ledger-entries",
    response_model=LedgerEntryList,
    operation_id="list_ledger_entries",
    openapi_extra={"x-work-package": "frontend-data-v1"},
)
async def ledger_entries(request: Request, principal: User, query: Annotated[LedgerQuery, Query()]):
    async with read_transaction(request) as session:
        ctx = await context(session, request, principal, query)
        return await repo.list_ledger_entries(
            session,
            principal,
            ctx,
            effect_type=query.effect_type,
            limit=query.limit,
            cursor=query.cursor,
        )
