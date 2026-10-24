"""Scenario inspection and atomic manual source events using the existing world."""

import base64
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, tuple_

from simulator.models import EventRow, Purchase, Run
from simulator.repository import (
    append_event,
    command_replay,
    digest,
    locked_run,
    record_command,
)
from simulator.schemas import State


def summary(run):
    return {
        "scenario_run_id": run.id,
        "store_id": run.world["store_id"],
        "scenario": run.configuration.get("scenario", "SC01"),
        "label": run.configuration.get("label") or run.configuration.get("scenario", "SC01"),
        "created_at": run.initial_snapshot["simulation_time"],
        "simulation_time": run.world["simulation_time"],
        "last_sequence": run.last_sequence,
    }


async def list_runs(session, before=None, limit=30):
    timestamp = Run.initial_snapshot["simulation_time"].astext
    query = select(Run).order_by(timestamp.desc(), Run.id.desc())
    if before:
        try:
            cursor = json.loads(base64.urlsafe_b64decode(before.encode()))
            if (
                not isinstance(cursor, list)
                or len(cursor) != 2
                or any(not isinstance(v, str) or not v or len(v) > 128 for v in cursor)
            ):
                raise ValueError()
            datetime.fromisoformat(cursor[0])
        except (ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(422, "INVALID_CURSOR") from exc
        query = query.where(tuple_(timestamp, Run.id) < tuple_(*cursor))
    rows = list(await session.scalars(query.limit(limit + 1)))
    page = rows[:limit]
    cursor = None
    if len(rows) > limit:
        tail = page[-1]
        cursor = base64.urlsafe_b64encode(
            json.dumps([tail.initial_snapshot["simulation_time"], tail.id]).encode()
        ).decode()
    return {"items": [summary(r) for r in page], "next_cursor": cursor}


async def get_run(session, run_id):
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    orders = await session.scalars(
        select(Purchase).where(Purchase.run_id == run_id).order_by(Purchase.action_id)
    )
    return summary(run) | {
        "state": run.world,
        "initial_snapshot": run.initial_snapshot,
        "configuration": run.configuration,
        "step_index": run.step_index,
        "orders": [
            {
                "action_id": p.action_id,
                "status": p.receipt["status"],
                "quantity": p.accepted_quantity,
                "received_quantity": p.received_quantity,
                "remaining_quantity": p.accepted_quantity - p.received_quantity,
                "eta": p.eta.isoformat() if p.eta else None,
                "total_minor": p.receipt["total_minor"],
            }
            for p in orders
        ],
    }


async def trigger_run(session, run_id, key, request):
    if await session.scalar(select(Run.id).where(Run.id == run_id)) is None:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    payload = request.model_dump(mode="json")
    content_hash = digest({"run_id": run_id, "body": payload})
    operation = "simulation_trigger"
    replay = await command_replay(session, operation, key, content_hash)
    if replay is not None:
        return replay
    run = await locked_run(session, run_id)
    if run.configuration.get("scenario") != "SANDBOX":
        raise HTTPException(409, "SCENARIO_MODE_MISMATCH")
    if run.last_sequence != request.expected_sequence:
        raise HTTPException(409, "SOURCE_CHANGED")
    before, state = deepcopy(run.world), deepcopy(run.world)
    now = datetime.now(UTC)
    sim_time = datetime.fromisoformat(state["simulation_time"])
    horizon = datetime.fromisoformat(run.initial_snapshot["initial_forecast"]["horizon_end"])
    stock = state["stocks"][0]
    if request.kind == "receipt":
        order = await session.get(Purchase, request.action_id)
        if order is None or order.run_id != run.id:
            raise HTTPException(404, "ORDER_NOT_FOUND")
        remaining = order.accepted_quantity - order.received_quantity
        quantity = remaining if request.quantity is None else request.quantity
        if quantity <= 0 or quantity > remaining or stock["in_transit"] < quantity:
            raise HTTPException(409, "RECEIPT_QUANTITY_INVALID")
        sim_time = max(sim_time, order.eta)
        if sim_time > horizon:
            raise HTTPException(409, "SCENARIO_HORIZON_EXCEEDED")
        stock["on_hand"] += quantity
        stock["in_transit"] -= quantity
        order.received_quantity += quantity
        event_type = "GOODS_RECEIVED"
        event_payload = {
            "action_id": order.action_id,
            "sku_id": stock["sku_id"],
            "quantity": quantity,
        }
    else:
        sim_time += timedelta(seconds=request.advance_seconds)
        if sim_time >= horizon:
            raise HTTPException(409, "SCENARIO_HORIZON_EXCEEDED")
        if request.kind == "sale":
            if stock["on_hand"] < request.quantity:
                raise HTTPException(409, "INSUFFICIENT_STOCK")
            stock["on_hand"] -= request.quantity
            stock["remaining_demand"] = max(0, stock["remaining_demand"] - request.quantity)
            state["receivables_minor"] += request.quantity * request.unit_price_minor
            event_type = "SALE_RECORDED"
            event_payload = {
                "sku_id": stock["sku_id"],
                "quantity": request.quantity,
                "unit_price_minor": request.unit_price_minor,
            }
        else:
            stock["remaining_demand"] = request.remaining_demand
            stock["forecast_version"] = "manual-" + uuid4().hex
            event_type = "DEMAND_REVISED"
            event_payload = {
                "sku_id": stock["sku_id"],
                "remaining_demand": request.remaining_demand,
                "forecast_version": stock["forecast_version"],
                "data_as_of": now,
                "valid_until": now + timedelta(hours=1),
                "horizon_start": sim_time,
                "horizon_end": horizon,
            }
    state["simulation_time"], state["data_as_of"] = sim_time.isoformat(), now.isoformat()
    try:
        State.model_validate(state)
    except ValidationError as exc:
        raise HTTPException(409, "WORLD_LIMIT_EXCEEDED") from exc
    run.world = state
    append_event(session, run, event_type, event_payload, now)
    await session.flush()
    event = await session.get(EventRow, (run.id, run.last_sequence))
    response = {
        "scenario_run_id": run.id,
        "first_sequence": run.last_sequence,
        "last_sequence": run.last_sequence,
        "simulation_time": state["simulation_time"],
        "before": before,
        "after": state,
        "events": [event.document],
    }
    record_command(session, operation, key, content_hash, run.id, response)
    return response
