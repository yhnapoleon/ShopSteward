from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.core.hashing import digest
from app.missions.models import InboundRow, MissionRow
from app.operations.models import ForecastRow, OfferRow, SourceCursor
from app.operations.repository import get_state
from app.operations.schemas import Offer
from app.planning.engine import RULE_VERSION
from app.planning.schemas import DecisionSnapshot, ForecastSnapshot, InboundSnapshot, Policy


@dataclass
class Prepared:
    mission_id: str
    state_version: int
    mission_version: int
    plan_counter: int
    manual: bool
    snapshot: DecisionSnapshot | None = None
    renewal: dict | None = None
    reason: str | None = None


def source_fresh(cursor, now, stale_seconds):
    return (
        cursor is not None
        and cursor.last_success_at is not None
        and cursor.last_error is None
        and 0 <= (now - cursor.last_success_at).total_seconds() < stale_seconds
    )


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Aware timestamp required")
    return parsed


class FixedForecastProvider:
    """Uses the current projection, never an initial-demand constant."""

    def read(self, row, stock, state, cursor, now, ttl_seconds):
        doc = row.document
        start, end = timestamp(doc["horizon_start"]), timestamp(doc["horizon_end"])
        if state.simulation_time is None or not start <= state.simulation_time < end:
            raise ValueError("Forecast horizon does not cover simulation time")
        cutoff = timestamp(doc["data_as_of"])
        if cutoff > now or (state.data_as_of and state.data_as_of > now):
            raise ValueError("Forecast cutoff is in the future")
        source = doc.get("source", "fixed")
        version = row.version
        valid_until = timestamp(doc["valid_until"])
        forecast_id = doc.get(
            "forecast_id", "forecast-" + digest([state.store_id, stock.sku_id, row.version])[:32]
        )
        model_version = doc.get("model_version", doc.get("forecast_version", "fixed-scenario"))
        assumptions = list(
            doc.get(
                "assumptions",
                ["SC01 fixed remaining demand; purchases arrive before remaining sales."],
            )
        )
        renewal = None
        if valid_until <= now:
            if source != "fixed":
                raise ValueError("Only a fixed forecast can be revalidated locally")
            version = "local-" + uuid4().hex
            forecast_id = "forecast-" + uuid4().hex
            cutoff = cursor.last_success_at
            valid_until = now + timedelta(seconds=ttl_seconds)
            renewal = {
                "forecast_id": forecast_id,
                "store_id": state.store_id,
                "sku_id": stock.sku_id,
                "input_state_version": state.state_version + 1,
                "predicted_quantity": stock.remaining_demand,
                "unit": "piece",
                "data_as_of": cutoff.isoformat(),
                "horizon_start": start.isoformat(),
                "horizon_end": end.isoformat(),
                "valid_until": valid_until.isoformat(),
                "source": "fixed",
                "model_name": doc.get("model_name", "fixed-scenario"),
                "model_version": model_version,
                "assumptions": assumptions,
            }
        forecast = ForecastSnapshot(
            forecast_id=forecast_id,
            forecast_version=version,
            store_id=state.store_id,
            sku_id=stock.sku_id,
            remaining_demand=stock.remaining_demand,
            unit="piece",
            data_as_of=cutoff,
            source_sequence=cursor.last_sequence,
            horizon_start=start,
            horizon_end=end,
            valid_until=valid_until,
            source=source,
            model_name=doc.get("model_name", "fixed-scenario"),
            model_version=model_version,
            assumptions=assumptions,
        )
        return forecast, renewal


async def prepare(db, mission_id, settings):
    async with db.session() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        mission = await session.get(MissionRow, mission_id)
        if mission is None:
            return Prepared(mission_id, 0, 0, 0, False, reason="MISSION_NOT_FOUND")
        state = await get_state(session, mission.store_id)
        prepared = Prepared(
            mission_id,
            state.state_version,
            mission.mission_version,
            mission.plan_counter,
            mission.manual_check_requested,
        )
        if mission.status != "ACTIVE" or mission.current_action_id is not None:
            prepared.reason = "MISSION_INACTIVE_OR_ACTION_PENDING"
            return prepared
        cursor = await session.scalar(
            select(SourceCursor).where(SourceCursor.store_id == mission.store_id)
        )
        now = await session.scalar(select(func.clock_timestamp()))
        if not source_fresh(cursor, now, settings.source_stale_seconds):
            prepared.reason = "DATA_STALE"
            return prepared
        stock = next((s for s in state.stocks if s.sku_id == mission.sku_id), None)
        if stock is None or stock.remaining_demand is None or stock.forecast_version is None:
            prepared.reason = "FORECAST_UNAVAILABLE"
            return prepared
        forecast_row = await session.get(
            ForecastRow, (state.store_id, stock.sku_id, stock.forecast_version)
        )
        offer_row = await session.get(
            OfferRow, (state.store_id, stock.sku_id, mission.policy["supplier_id"])
        )
        if forecast_row is None or offer_row is None:
            prepared.reason = "INPUT_UNAVAILABLE"
            return prepared
        try:
            offer = Offer.model_validate(offer_row.document)
            if not offer.valid_from <= now < offer.valid_until or offer.currency != state.currency:
                prepared.reason = "OFFER_EXPIRED"
                return prepared
            forecast, renewal = FixedForecastProvider().read(
                forecast_row, stock, state, cursor, now, settings.fixed_forecast_ttl_seconds
            )
            rows = list(
                await session.scalars(
                    select(InboundRow)
                    .where(
                        InboundRow.store_id == state.store_id,
                        InboundRow.sku_id == stock.sku_id,
                        InboundRow.ordered_qty > InboundRow.received_qty,
                    )
                    .order_by(InboundRow.action_id, InboundRow.sku_id)
                )
            )
            if sum(row.ordered_qty - row.received_qty for row in rows) != stock.in_transit:
                prepared.reason = "INBOUND_STATE_MISMATCH"
                return prepared
            inbound = [
                InboundSnapshot(
                    action_id=row.action_id,
                    sku_id=row.sku_id,
                    remaining_quantity=row.ordered_qty - row.received_qty,
                    expected_arrival_at=row.expected_arrival_at,
                    eligible=row.expected_arrival_at is not None
                    and state.simulation_time <= row.expected_arrival_at < forecast.horizon_end,
                )
                for row in rows
            ]
            if renewal:
                state.state_version += 1
                stock.forecast_version = forecast.forecast_version
            prepared.renewal = renewal
            prepared.snapshot = DecisionSnapshot(
                snapshot_version="decision-v1",
                state=state,
                mission_version=mission.mission_version,
                policy=Policy.model_validate(mission.policy),
                policy_version=mission.policy_version,
                forecast=forecast,
                offer=offer,
                inbound_items=inbound,
                eligible_inbound_qty=sum(row.remaining_quantity for row in inbound if row.eligible),
                rule_version=RULE_VERSION,
                evaluated_at=now,
                last_successful_sync_at=cursor.last_success_at,
                source_fresh_until=cursor.last_success_at
                + timedelta(seconds=settings.source_stale_seconds),
            )
        except (ValueError, KeyError, TypeError, ValidationError):
            prepared.reason = "INVALID_FORECAST_OR_OFFER"
        return prepared
