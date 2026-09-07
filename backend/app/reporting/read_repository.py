"""Read views over accepted facts. Caller owns a read-only repeatable-read transaction."""

import logging
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import func, select, tuple_

from app.core.errors import AppError
from app.execution.models import ActionRow
from app.execution.schemas import Action
from app.missions.models import InboundRow, MissionRow
from app.operations.models import EventRow, LedgerEntry, ProductRow, SourceCursor, Store
from app.planning.snapshot import source_fresh
from app.reporting.read_pagination import decode_read_cursor, encode_read_cursor, read_scope
from app.reporting.read_projections import day_buckets, inbound_view, ledger_view, sale_view
from app.reporting.read_schemas import (
    ActionList,
    InboundList,
    LedgerEntryList,
    ReadContext,
    SaleList,
    SaleSummary,
    StoreList,
    StoreSummary,
)
from app.reporting.schemas import Freshness
from app.scheduling.models import Job


def invalid_record(row):
    logging.getLogger("shopsteward").warning(
        "invalid_stored_read",
        extra={
            "record_type": type(row).__name__,
            "record_id": getattr(
                row, "id", getattr(row, "event_id", getattr(row, "action_id", None))
            ),
        },
    )
    return AppError(503, "INVALID_STORED_DATA", "Stored data cannot be safely read")


def project(view, row, *args):
    try:
        return view(row, *args)
    except (ValidationError, KeyError, TypeError) as exc:
        raise invalid_record(row) from exc
    except AppError as exc:
        if exc.code == "INVALID_STORED_DATA":
            raise invalid_record(row) from exc
        raise


async def read_context(session, store_id, settings, *, sku_id=None, mission_id=None):
    store = await session.get(Store, store_id)
    if store is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Store is not visible or does not exist")
    now = await session.scalar(select(func.clock_timestamp()))
    if sku_id is not None and await session.get(ProductRow, (store_id, sku_id)) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Product is not visible or does not exist")
    if mission_id is not None:
        mission = await session.get(MissionRow, mission_id)
        if mission is None or mission.store_id != store_id:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Mission is not visible or does not exist")
    cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == store_id))
    status = "UNKNOWN"
    if cursor:
        if source_fresh(cursor, now, settings.source_stale_seconds):
            status = "FRESH"
        elif cursor.last_success_at is not None or cursor.last_error is not None:
            status = "STALE"
    return ReadContext(
        store_id=store.id,
        currency=store.currency,
        state_version=store.state_version,
        as_of=now,
        simulation_time=store.simulation_time,
        source_sequence=cursor.last_sequence if cursor else None,
        freshness=Freshness(
            status=status,
            data_as_of=store.data_as_of,
            last_sync_at=cursor.last_success_at if cursor else None,
        ),
    )


async def list_stores(session, principal, *, limit, cursor):
    scope = read_scope(principal, "stores")
    anchor = decode_read_cursor(cursor, scope, (str,))
    query = select(Store)
    if "admin" not in principal.roles:
        query = query.where(Store.id.in_(principal.store_ids if principal.roles else []))
    if anchor:
        query = query.where(Store.id > anchor[0])
    rows = list(await session.scalars(query.order_by(Store.id).limit(limit + 1)))
    # Successful initialization and its result commit with the imported business state.
    # Order by request time so a slower, older creation cannot supersede a newer one.
    latest = await session.scalar(
        select(Job)
        .where(Job.job_type == "initialize_scenario", Job.status == "SUCCEEDED")
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    active = None
    if latest and latest.result:
        store_id = next(
            (ref["id"] for ref in latest.result.get("references", []) if ref["type"] == "store"),
            None,
        )
        if store_id and (
            "admin" in principal.roles or (principal.roles and store_id in principal.store_ids)
        ):
            active = await session.get(Store, store_id)

    def summary(row):
        return StoreSummary(
            store_id=row.id,
            currency=row.currency,
            source_type="simulation",
            simulation_time=row.simulation_time,
        )

    return StoreList(
        items=[summary(row) for row in rows[:limit]],
        next_cursor=encode_read_cursor(scope, (rows[limit - 1].id,)) if len(rows) > limit else None,
        active_store=summary(active) if active else None,
    )


async def sales_records(session, store_id, *, sku_id, start, end):
    # Validate before date filtering: casting bad JSON dates in SQL would hide corruption
    # behind a dependency error. Stream local facts without materializing all rows.
    query = (
        select(EventRow)
        .join(SourceCursor, SourceCursor.scenario_run_id == EventRow.scenario_run_id)
        .where(
            SourceCursor.store_id == store_id,
            EventRow.document["event_type"].astext == "SALE_RECORDED",
        )
        .order_by(EventRow.sequence.desc(), EventRow.event_id.desc())
    )
    async for row in await session.stream_scalars(query.execution_options(yield_per=200)):
        record = project(sale_view, row)
        if row.document["store_id"] != store_id:
            raise invalid_record(row)
        if sku_id is not None and record.sku_id != sku_id:
            continue
        if start is not None and not start <= record.simulation_time < end:
            continue
        yield record


async def list_sales(session, principal, context, *, sku_id, start, end, limit, cursor):
    scope = read_scope(
        principal, "sales", store_id=context.store_id, sku_id=sku_id, start=start, end=end
    )
    anchor = decode_read_cursor(cursor, scope, (int, str))
    items = []
    async for record in sales_records(
        session, context.store_id, sku_id=sku_id, start=start, end=end
    ):
        if anchor is not None and (record.sequence, record.event_id) >= anchor:
            continue
        items.append(record)
        if len(items) > limit:
            break
    return SaleList(
        context=context,
        items=items[:limit],
        next_cursor=encode_read_cursor(
            scope, (items[limit - 1].sequence, items[limit - 1].event_id)
        )
        if len(items) > limit
        else None,
    )


async def summarize_sales(session, context, *, sku_id, start, end):
    records = [
        record
        async for record in sales_records(
            session, context.store_id, sku_id=sku_id, start=start, end=end
        )
    ]
    buckets = day_buckets(start, end, records)
    totals = {
        key: sum(getattr(bucket, key) for bucket in buckets)
        for key in ("record_count", "recorded_quantity", "recorded_sales_amount_minor")
    }
    if any(value > 2**63 - 1 for value in totals.values()):
        raise AppError(422, "AGGREGATE_OUT_OF_RANGE", "Aggregate exceeds int64 range")
    return SaleSummary(
        **{
            "context": context,
            "from": start,
            "to": end,
            "time_basis": "simulation_time",
            "timezone": "UTC",
            "granularity": "day",
            "coverage": "RECORDED_EVENTS_ONLY",
            "buckets": buckets,
            **totals,
        }
    )


async def list_actions(session, principal, context, *, mission_id, sku_id, status, limit, cursor):
    scope = read_scope(
        principal,
        "actions",
        store_id=context.store_id,
        mission_id=mission_id,
        sku_id=sku_id,
        status=status,
    )
    anchor = decode_read_cursor(cursor, scope, (datetime, str))
    query = select(ActionRow).where(ActionRow.store_id == context.store_id)
    if mission_id is not None:
        query = query.where(ActionRow.mission_id == mission_id)
    if sku_id is not None:
        query = query.where(ActionRow.purchase_snapshot["sku_id"].astext == sku_id)
    if status is not None:
        query = query.where(ActionRow.status == status)
    if anchor:
        query = query.where(tuple_(ActionRow.created_at, ActionRow.id) < anchor)
    rows = list(
        await session.scalars(
            query.order_by(ActionRow.created_at.desc(), ActionRow.id.desc()).limit(limit + 1)
        )
    )
    items = [project(Action.model_validate, row) for row in rows[:limit]]
    return ActionList(
        context=context,
        items=items,
        next_cursor=encode_read_cursor(scope, (rows[limit - 1].created_at, rows[limit - 1].id))
        if len(rows) > limit
        else None,
    )


async def list_inbounds(
    session, principal, context, *, mission_id, sku_id, arrival_status, limit, cursor
):
    scope = read_scope(
        principal,
        "inbounds",
        store_id=context.store_id,
        mission_id=mission_id,
        sku_id=sku_id,
        arrival_status=arrival_status,
    )
    anchor = decode_read_cursor(cursor, scope, (str, str))
    query = (
        select(InboundRow, ActionRow)
        .outerjoin(ActionRow, ActionRow.id == InboundRow.action_id)
        .where(InboundRow.store_id == context.store_id)
    )
    if mission_id is not None:
        query = query.where(ActionRow.mission_id == mission_id)
    if sku_id is not None:
        query = query.where(InboundRow.sku_id == sku_id)
    if arrival_status == "NOT_RECEIVED":
        query = query.where(InboundRow.received_qty == 0)
    elif arrival_status == "PARTIALLY_RECEIVED":
        query = query.where(
            InboundRow.received_qty > 0, InboundRow.received_qty < InboundRow.ordered_qty
        )
    elif arrival_status == "RECEIVED":
        query = query.where(InboundRow.received_qty == InboundRow.ordered_qty)
    if anchor:
        query = query.where(tuple_(InboundRow.action_id, InboundRow.sku_id) > anchor)
    rows = list(
        await session.execute(
            query.order_by(InboundRow.action_id, InboundRow.sku_id).limit(limit + 1)
        )
    )
    return InboundList(
        context=context,
        items=[
            project(inbound_view, row, action, context.simulation_time)
            for row, action in rows[:limit]
        ],
        next_cursor=encode_read_cursor(
            scope, (rows[limit - 1][0].action_id, rows[limit - 1][0].sku_id)
        )
        if len(rows) > limit
        else None,
    )


async def list_ledger_entries(session, principal, context, *, effect_type, limit, cursor):
    scope = read_scope(principal, "ledger", store_id=context.store_id, effect_type=effect_type)
    anchor = decode_read_cursor(cursor, scope, (int, str))
    query = select(LedgerEntry).where(LedgerEntry.store_id == context.store_id)
    if effect_type is not None:
        query = query.where(LedgerEntry.effect_type == effect_type)
    if anchor:
        query = query.where(tuple_(LedgerEntry.state_version, LedgerEntry.id) < anchor)
    rows = list(
        await session.scalars(
            query.order_by(LedgerEntry.state_version.desc(), LedgerEntry.id.desc()).limit(limit + 1)
        )
    )
    action_ids = set()
    for row in rows[:limit]:
        if row.effect_type not in {"PURCHASE_ACCEPTED", "GOODS_RECEIVED"}:
            continue
        document = row.document
        if row.effect_type == "GOODS_RECEIVED" and isinstance(document, dict):
            document = document.get("payload")
        action_id = document.get("action_id") if isinstance(document, dict) else None
        if not isinstance(action_id, str) or not 1 <= len(action_id) <= 128:
            raise invalid_record(row)
        action_ids.add(action_id)
    actions = await session.scalars(
        select(ActionRow).where(
            ActionRow.store_id == context.store_id, ActionRow.id.in_(action_ids)
        )
    )
    action_by_id = {action.id: action for action in actions}
    return LedgerEntryList(
        context=context,
        items=[project(ledger_view, row, action_by_id) for row in rows[:limit]],
        next_cursor=encode_read_cursor(scope, (rows[limit - 1].state_version, rows[limit - 1].id))
        if len(rows) > limit
        else None,
    )
