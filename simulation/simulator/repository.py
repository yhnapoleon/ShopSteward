import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from simulator.models import CommandRecord, EventRow, Purchase, Run
from simulator.schemas import DemandEvent, PurchaseEvent, PurchaseReceipt, ReceivedEvent, SaleEvent

# The configured bearer credential identifies the single backend service principal.
# Token rotation must not change command ownership or invalidate historical retries.
PRINCIPAL = "backend-service"


def digest(request):
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


async def lock_identity(session, identity):
    # Unique constraints remain the persistent invariant; advisory locks also serialize
    # absent rows across runs, so a competing request can replay instead of failing INSERT.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": json.dumps(identity)},
    )


async def command_replay(session, operation, key, content_hash):
    await lock_identity(session, ["command", PRINCIPAL, operation, key])
    command = await session.get(CommandRecord, (PRINCIPAL, operation, key))
    if command is not None:
        if command.content_hash != content_hash:
            raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED")
        return command.response
    return None


def record_command(session, operation, key, content_hash, run_id, response):
    session.add(
        CommandRecord(
            principal=PRINCIPAL,
            operation=operation,
            key=key,
            content_hash=content_hash,
            run_id=run_id,
            response=response,
        )
    )


async def locked_run(session, run_id):
    run = await session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    return run


def initial_snapshot():
    now = datetime.now(UTC)
    timestamp = now.isoformat()
    store_id, run_id = "store_" + uuid4().hex, "run_" + uuid4().hex
    state = {
        "store_id": store_id,
        "state_version": 1,
        "currency": "CNY",
        "cash_minor": 100000,
        "reserved_cash_minor": 0,
        "available_cash_minor": 100000,
        "receivables_minor": 0,
        "stocks": [
            {
                "sku_id": "sku_001",
                "on_hand": 20,
                "in_transit": 0,
                "remaining_demand": 60,
                "forecast_version": "fixed-1",
            }
        ],
        "data_as_of": timestamp,
        "simulation_time": timestamp,
    }
    forecast = {
        "forecast_id": "forecast_" + uuid4().hex,
        "store_id": store_id,
        "sku_id": "sku_001",
        "input_state_version": 1,
        "predicted_quantity": 60,
        "unit": "piece",
        "data_as_of": timestamp,
        "horizon_start": timestamp,
        "horizon_end": (now + timedelta(days=7)).isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "model_name": "fixed-scenario",
        "model_version": "fixed-1",
        "source": "fixed",
        "assumptions": ["SC01 fixed remaining demand; not a learned prediction"],
    }
    catalog = {
        "store_id": store_id,
        "currency": "CNY",
        "products": [{"sku_id": "sku_001", "name": "SC01 sample product", "unit": "piece"}],
        "offers": [
            {
                "supplier_id": "supplier_001",
                "sku_id": "sku_001",
                "unit_price_minor": 1000,
                "minimum_order_quantity": 20,
                "pack_size": 20,
                "offer_version": "offer-1",
                "currency": "CNY",
                "lead_time_seconds": 86400,
                "valid_from": timestamp,
                "valid_until": (now + timedelta(days=1)).isoformat(),
            }
        ],
    }
    return {
        "scenario_run_id": run_id,
        "store_id": store_id,
        "simulation_time": timestamp,
        "initial_state": state,
        "initial_forecast": forecast,
        "initial_catalog": catalog,
    }


async def create_run(session, key, request):
    content_hash = digest(request)
    replay = await command_replay(session, "simulation_create_run", key, content_hash)
    if replay is not None:
        return replay
    seed = initial_snapshot()
    await session.execute(
        insert(Run)
        .values(
            id=seed["scenario_run_id"],
            command_key=key,
            content_hash=content_hash,
            initial_snapshot=seed,
            world=seed["initial_state"],
            last_sequence=0,
            step_index=0,
        )
        .on_conflict_do_nothing(index_elements=[Run.command_key])
    )
    run = await session.scalar(select(Run).where(Run.command_key == key))
    if run.content_hash != content_hash:
        raise HTTPException(409, "IDEMPOTENCY_KEY_REUSED")
    record_command(
        session, "simulation_create_run", key, content_hash, run.id, run.initial_snapshot
    )
    return run.initial_snapshot


async def list_events(session, run_id, after, limit):
    # REPEATABLE READ is selected by the caller before the first statement.
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    if after > run.last_sequence:
        raise HTTPException(409, "EVENT_CURSOR_AHEAD")
    events = list(
        await session.scalars(
            select(EventRow.document)
            .where(
                EventRow.run_id == run_id,
                EventRow.sequence > after,
                EventRow.sequence <= run.last_sequence,
            )
            .order_by(EventRow.sequence)
            .limit(limit)
        )
    )
    last = events[-1]["sequence"] if events else after
    return {
        "events": events,
        "last_sequence": last,
        "source_head_sequence": run.last_sequence,
        "has_more": last < run.last_sequence,
    }


def append_event(session, run, event_type, payload, now):
    run.last_sequence += 1
    dto = {
        "PURCHASE_ACCEPTED": PurchaseEvent,
        "GOODS_RECEIVED": ReceivedEvent,
        "SALE_RECORDED": SaleEvent,
        "DEMAND_REVISED": DemandEvent,
    }[event_type]
    document = dto(
        event_id="event_" + uuid4().hex,
        sequence=run.last_sequence,
        schema_version="1.0",
        event_type=event_type,
        store_id=run.world["store_id"],
        occurred_at=now,
        simulation_time=run.world["simulation_time"],
        payload=payload,
    ).model_dump(mode="json")
    session.add(
        EventRow(
            run_id=run.id,
            sequence=run.last_sequence,
            event_id=document["event_id"],
            document=document,
        )
    )


def purchase_terms(run, request, now):
    offer = next(
        (
            offer
            for offer in run.initial_snapshot["initial_catalog"]["offers"]
            if offer["sku_id"] == request["sku_id"]
            and offer["supplier_id"] == request["supplier_id"]
        ),
        None,
    )
    if offer is None:
        return "OFFER_NOT_FOUND", 0, None
    if (
        not datetime.fromisoformat(offer["valid_from"])
        <= now
        < datetime.fromisoformat(offer["valid_until"])
    ):
        return "OFFER_EXPIRED", 0, None
    quantity = request["quantity"]
    total = quantity * offer["unit_price_minor"]
    if quantity < offer["minimum_order_quantity"]:
        return "MINIMUM_ORDER_QUANTITY", 0, None
    if quantity % offer["pack_size"]:
        return "PACK_SIZE_MISMATCH", 0, None
    if total != request["expected_total_minor"]:
        return "PRICE_MISMATCH", 0, None
    if total > run.world["cash_minor"]:
        return "INSUFFICIENT_CASH", 0, None
    eta = datetime.fromisoformat(run.world["simulation_time"]) + timedelta(
        seconds=offer["lead_time_seconds"]
    )
    if eta > datetime.fromisoformat(run.initial_snapshot["initial_forecast"]["horizon_end"]):
        return "ETA_OUTSIDE_SCENARIO", 0, None
    return None, total, eta


async def submit_purchase(session, key, request):
    # The route authenticates before entering this transaction. With one service
    # principal, every run is in its scope; store/run identity must still match.
    run_identity = await session.scalar(
        select(Run.initial_snapshot).where(Run.id == request["scenario_run_id"])
    )
    if run_identity is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    if run_identity["store_id"] != request["store_id"]:
        raise HTTPException(403, "RESOURCE_FORBIDDEN")
    content_hash = digest(request)
    replay = await command_replay(session, "simulation_purchase", key, content_hash)
    if replay is not None:
        return replay
    run = await locked_run(session, request["scenario_run_id"])
    await lock_identity(session, ["action", request["action_id"]])
    existing = await session.get(Purchase, request["action_id"])
    if existing is not None:
        if existing.content_hash != content_hash:
            raise HTTPException(409, "ACTION_CONTENT_CONFLICT")
        receipt = existing.receipt
    else:
        now = datetime.now(UTC)
        reason, total, eta = purchase_terms(run, request, now)
        receipt = PurchaseReceipt(
            action_id=request["action_id"],
            status="REJECTED" if reason else "ACCEPTED",
            external_order_id=None if reason else "order_" + uuid4().hex,
            quantity=0 if reason else request["quantity"],
            total_minor=total,
            currency="CNY",
            recorded_at=now,
            reason=reason,
        ).model_dump(mode="json")
        session.add(
            Purchase(
                action_id=request["action_id"],
                run_id=run.id,
                content_hash=content_hash,
                request=request,
                receipt=receipt,
                accepted_quantity=receipt["quantity"],
                received_quantity=0,
                eta=eta,
            )
        )
        if reason is None:
            state = deepcopy(run.world)
            state["cash_minor"] -= total
            state["available_cash_minor"] = state["cash_minor"]
            stock = next(s for s in state["stocks"] if s["sku_id"] == request["sku_id"])
            stock["in_transit"] += request["quantity"]
            state["data_as_of"] = now.isoformat()
            run.world = state
            append_event(
                session,
                run,
                "PURCHASE_ACCEPTED",
                {
                    "action_id": request["action_id"],
                    "external_order_id": receipt["external_order_id"],
                    "sku_id": request["sku_id"],
                    "quantity": request["quantity"],
                    "total_minor": total,
                },
                now,
            )
    record_command(session, "simulation_purchase", key, content_hash, run.id, receipt)
    return receipt


async def get_purchase(session, action_id):
    purchase = await session.get(Purchase, action_id)
    if purchase is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    return purchase.receipt


async def advance_run(session, run_id, key, request):
    # Resolve the resource before replay; the request digest includes the path run.
    if await session.scalar(select(Run.id).where(Run.id == run_id)) is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    content_hash = digest({"run_id": run_id, "body": request})
    replay = await command_replay(session, "simulation_advance", key, content_hash)
    if replay is not None:
        return replay
    run = await locked_run(session, run_id)
    if run.step_index + request["steps"] > 4:
        raise HTTPException(409, "SCENARIO_FINISHED")
    horizon_end = datetime.fromisoformat(run.initial_snapshot["initial_forecast"]["horizon_end"])
    for _ in range(request["steps"]):
        now = datetime.now(UTC)
        state = deepcopy(run.world)
        sim_time = datetime.fromisoformat(state["simulation_time"])
        stock = state["stocks"][0]
        if run.step_index in (0, 3):
            pending = list(
                await session.scalars(
                    select(Purchase)
                    .where(
                        Purchase.run_id == run.id,
                        Purchase.received_quantity < Purchase.accepted_quantity,
                    )
                    .order_by(Purchase.action_id)
                )
            )
            if not pending:
                raise HTTPException(409, "SCENARIO_STEP_BLOCKED")
            sim_time = max([sim_time] + [p.eta for p in pending])
            if sim_time > horizon_end:
                raise HTTPException(409, "SCENARIO_STEP_BLOCKED")
            state["simulation_time"] = sim_time.isoformat()
            state["data_as_of"] = now.isoformat()
            run.world = state
            for order in pending:
                quantity = order.accepted_quantity - order.received_quantity
                receiving_stock = next(
                    s for s in state["stocks"] if s["sku_id"] == order.request["sku_id"]
                )
                if receiving_stock["in_transit"] < quantity:
                    raise HTTPException(409, "SCENARIO_STEP_BLOCKED")
                receiving_stock["in_transit"] -= quantity
                receiving_stock["on_hand"] += quantity
                order.received_quantity += quantity
                append_event(
                    session,
                    run,
                    "GOODS_RECEIVED",
                    {
                        "action_id": order.action_id,
                        "sku_id": order.request["sku_id"],
                        "quantity": quantity,
                    },
                    now,
                )
        else:
            sim_time += timedelta(hours=1)
            if sim_time >= horizon_end:
                raise HTTPException(409, "SCENARIO_STEP_BLOCKED")
            state["simulation_time"] = sim_time.isoformat()
            state["data_as_of"] = now.isoformat()
            run.world = state
            if run.step_index == 1:
                if stock["on_hand"] < 10:
                    raise HTTPException(409, "SCENARIO_STEP_BLOCKED")
                stock["on_hand"] -= 10
                stock["remaining_demand"] = max(0, stock["remaining_demand"] - 10)
                state["receivables_minor"] += 20000
                append_event(
                    session,
                    run,
                    "SALE_RECORDED",
                    {
                        "sku_id": stock["sku_id"],
                        "quantity": 10,
                        "unit_price_minor": 2000,
                    },
                    now,
                )
            else:
                stock["remaining_demand"] = 70
                stock["forecast_version"] = "fixed-" + uuid4().hex
                append_event(
                    session,
                    run,
                    "DEMAND_REVISED",
                    {
                        "sku_id": stock["sku_id"],
                        "remaining_demand": 70,
                        "forecast_version": stock["forecast_version"],
                        "data_as_of": now,
                        "valid_until": now + timedelta(hours=1),
                        "horizon_start": sim_time,
                        "horizon_end": horizon_end,
                    },
                    now,
                )
        run.step_index += 1
    response = {
        "scenario_run_id": run.id,
        "simulation_time": run.world["simulation_time"],
        "last_sequence": run.last_sequence,
    }
    record_command(session, "simulation_advance", key, content_hash, run.id, response)
    return response
