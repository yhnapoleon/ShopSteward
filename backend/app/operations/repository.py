import hashlib
import json
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.operations.models import (
    Command,
    EventRow,
    ForecastRow,
    LedgerEntry,
    OfferRow,
    ProductRow,
    SourceCursor,
    StockRow,
    Store,
)
from app.operations.schemas import Catalog, EventBatchResult, State, Stock


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def conflict(code, message):
    return AppError(409, code, message)


async def store_for_run(session, run_id, *, lock=True):
    query = select(Store).where(Store.scenario_run_id == run_id)
    if lock:
        query = query.with_for_update()
    store = await session.scalar(query.execution_options(populate_existing=True))
    if store is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Scenario does not exist")
    return store


async def initialize(session, seed):
    state = seed.initial_state
    content_hash = digest(seed.model_dump(mode="json", exclude_unset=True))
    inserted = await session.scalar(
        insert(Store)
        .values(
            id=seed.store_id,
            scenario_run_id=seed.scenario_run_id,
            initial_hash=content_hash,
            currency=state.currency,
            cash_minor=state.cash_minor,
            reserved_cash_minor=state.reserved_cash_minor,
            receivables_minor=state.receivables_minor,
            state_version=1,
            data_as_of=state.data_as_of,
            simulation_time=state.simulation_time,
        )
        .on_conflict_do_nothing()
        .returning(Store.id)
    )
    if inserted is None:
        existing = await store_for_run(session, seed.scenario_run_id)
        if existing.id != seed.store_id or existing.initial_hash != content_hash:
            raise conflict("INITIAL_STATE_CONFLICT", "Initial snapshot differs from original")
        return existing
    for product in seed.initial_catalog.products:
        session.add(
            ProductRow(
                store_id=seed.store_id,
                sku_id=product.sku_id,
                document=product.model_dump(mode="json"),
            )
        )
    for offer in seed.initial_catalog.offers:
        session.add(
            OfferRow(
                store_id=seed.store_id,
                sku_id=offer.sku_id,
                supplier_id=offer.supplier_id,
                document=offer.model_dump(mode="json"),
            )
        )
    local_version = "local-" + digest([seed.scenario_run_id, "initial-forecast"])[:32]
    for stock in state.stocks:
        fields = stock.model_dump()
        if stock.sku_id == seed.initial_forecast.sku_id:
            fields["forecast_version"] = local_version
        session.add(StockRow(store_id=seed.store_id, **fields))
    forecast = seed.initial_forecast
    session.add(
        ForecastRow(
            store_id=seed.store_id,
            sku_id=forecast.sku_id,
            version=local_version,
            source_sequence=0,
            document=forecast.model_dump(mode="json", exclude_unset=True),
        )
    )
    session.add(
        SourceCursor(
            scenario_run_id=seed.scenario_run_id,
            store_id=seed.store_id,
            source="simulation",
            last_sequence=0,
        )
    )
    session.add(
        LedgerEntry(
            id=digest([seed.store_id, "INIT"]),
            store_id=seed.store_id,
            effect_type="INIT",
            state_version=1,
            document=state.model_dump(mode="json"),
        )
    )
    await session.flush()
    return await session.get(Store, seed.store_id)


async def get_state(session, store_id):
    # One statement gives a consistent state/stock snapshot under READ COMMITTED.
    rows = (
        await session.execute(
            select(Store, StockRow)
            .outerjoin(StockRow, StockRow.store_id == Store.id)
            .where(Store.id == store_id)
            .order_by(StockRow.sku_id)
            .execution_options(populate_existing=True)
        )
    ).all()
    if not rows:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Store does not exist")
    store = rows[0][0]
    return State(
        store_id=store.id,
        state_version=store.state_version,
        currency=store.currency,
        cash_minor=store.cash_minor,
        reserved_cash_minor=store.reserved_cash_minor,
        available_cash_minor=store.cash_minor - store.reserved_cash_minor,
        receivables_minor=store.receivables_minor,
        data_as_of=store.data_as_of,
        simulation_time=store.simulation_time,
        stocks=[Stock.model_validate(row) for _, row in rows if row is not None],
    )


async def get_catalog(session, store_id):
    store = await session.get(Store, store_id)
    if store is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Store does not exist")
    products = await session.scalars(
        select(ProductRow.document)
        .where(ProductRow.store_id == store_id)
        .order_by(ProductRow.sku_id)
    )
    offers = await session.scalars(
        select(OfferRow.document)
        .where(OfferRow.store_id == store_id)
        .order_by(OfferRow.sku_id, OfferRow.supplier_id)
    )
    return Catalog(
        store_id=store_id, currency=store.currency, products=list(products), offers=list(offers)
    )


async def ingest(session, batch, *, command_scope, key, receipts=None):
    store = await store_for_run(session, batch.scenario_run_id)
    command_id = digest(["event_batch", command_scope, key])
    request_hash = digest(batch.model_dump(mode="json"))
    reserved = await session.scalar(
        insert(Command)
        .values(id=command_id, content_hash=request_hash, response={})
        .on_conflict_do_nothing()
        .returning(Command.id)
    )
    original = await session.get(Command, command_id)
    if reserved is None:
        if original.content_hash != request_hash:
            raise conflict("IDEMPOTENCY_KEY_REUSED", "Command key was used for different content")
        return EventBatchResult.model_validate(original.response)
    cursor = await session.scalar(
        select(SourceCursor)
        .where(SourceCursor.scenario_run_id == batch.scenario_run_id)
        .with_for_update()
    )
    result = EventBatchResult(
        accepted_event_ids=[], duplicate_event_ids=[], last_sequence=cursor.last_sequence
    )
    for event in batch.events:
        if event.store_id != store.id:
            raise conflict("EVENT_STORE_MISMATCH", "Event does not belong to the bound store")
        document = event.model_dump(mode="json")
        event_hash = digest(document)
        existing = (
            await session.scalars(
                select(EventRow).where(
                    EventRow.scenario_run_id == batch.scenario_run_id,
                    or_(EventRow.event_id == event.event_id, EventRow.sequence == event.sequence),
                )
            )
        ).all()
        if existing:
            if len(existing) != 1 or existing[0].content_hash != event_hash:
                raise conflict("EVENT_CONFLICT", "Event identity or sequence has different content")
            result.duplicate_event_ids.append(event.event_id)
            continue
        if event.sequence != cursor.last_sequence + 1:
            raise conflict(
                "EVENT_SEQUENCE_GAP", "Events must extend the contiguous source sequence"
            )
        stock = await session.get(StockRow, (store.id, event.payload.sku_id))
        if stock is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Event SKU does not exist in this store")
        ordinary_effect = await apply_event(session, store, stock, event, receipts or {})
        if ordinary_effect:
            store.state_version += 1
        # Event order is authoritative; the source may legitimately have delayed wall timestamps.
        store.data_as_of = max(filter(None, [store.data_as_of, event.occurred_at]))
        store.simulation_time = max(filter(None, [store.simulation_time, event.simulation_time]))
        session.add(
            EventRow(
                scenario_run_id=batch.scenario_run_id,
                event_id=event.event_id,
                sequence=event.sequence,
                content_hash=event_hash,
                document=document,
            )
        )
        if ordinary_effect:
            session.add(
                LedgerEntry(
                    id=digest([batch.scenario_run_id, event.event_id, event.event_type]),
                    store_id=store.id,
                    effect_type=event.event_type,
                    source_event_id=event.event_id,
                    state_version=store.state_version,
                    document=document,
                )
            )
        cursor.last_sequence = event.sequence
        result.accepted_event_ids.append(event.event_id)
        await session.flush()
    result.last_sequence = cursor.last_sequence
    # A pushed batch provides no source head proof. Do not mark it caught up.
    original.response = result.model_dump()
    await session.flush()
    return result


async def apply_event(session, store, stock, event, receipts=None):
    payload = event.payload
    if event.event_type == "SALE_RECORDED":
        if stock.on_hand < payload.quantity:
            raise conflict("INSUFFICIENT_STOCK", "Sale quantity exceeds recorded on-hand stock")
        receivables = store.receivables_minor + payload.quantity * payload.unit_price_minor
        if receivables > 9223372036854775807:
            raise conflict("AMOUNT_OUT_OF_RANGE", "Resulting receivables exceed supported range")
        stock.on_hand -= payload.quantity
        store.receivables_minor = receivables
        if stock.remaining_demand is not None:
            stock.remaining_demand = max(0, stock.remaining_demand - payload.quantity)
            previous = (
                await session.get(ForecastRow, (store.id, stock.sku_id, stock.forecast_version))
                if stock.forecast_version
                else None
            )
            if previous is not None:
                document = dict(previous.document)
                quantity_field = (
                    "predicted_quantity" if "predicted_quantity" in document else "remaining_demand"
                )
                document[quantity_field] = stock.remaining_demand
                document["data_as_of"] = max(
                    datetime.fromisoformat(document["data_as_of"]), event.occurred_at
                ).isoformat()
                if "input_state_version" in document:
                    document["input_state_version"] = store.state_version + 1
                local_version = "local-" + digest([store.scenario_run_id, event.event_id])[:32]
                stock.forecast_version = local_version
                session.add(
                    ForecastRow(
                        store_id=store.id,
                        sku_id=stock.sku_id,
                        version=local_version,
                        source_sequence=event.sequence,
                        document=document,
                    )
                )
            else:
                # Missing forecast metadata must not prevent recording a real sale.
                stock.forecast_version = None
    elif event.event_type == "DEMAND_REVISED":
        local_version = "local-" + digest([store.scenario_run_id, event.event_id])[:32]
        stock.remaining_demand = payload.remaining_demand
        stock.forecast_version = local_version
        session.add(
            ForecastRow(
                store_id=store.id,
                sku_id=stock.sku_id,
                version=local_version,
                source_sequence=event.sequence,
                document=payload.model_dump(mode="json"),
            )
        )
    else:
        from app.execution.events import apply_purchase_event

        return await apply_purchase_event(session, store, stock, event, receipts or {})
    return True


async def mark_caught_up(session, run_id, sequence):
    cursor = await session.scalar(
        select(SourceCursor).where(SourceCursor.scenario_run_id == run_id).with_for_update()
    )
    if cursor.last_sequence == sequence:
        cursor.last_success_at = await session.scalar(select(func.clock_timestamp()))
        cursor.last_error = None
