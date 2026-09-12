from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from test_missions import body as mission_body
from test_missions import environment, headers, settings

from app.core.errors import AppError
from app.execution.repository import validate_current
from app.forecast_v6 import repository as repo
from app.forecast_v6.models import ForecastV6Binding, ForecastV6Evidence
from app.forecast_v6.schemas import ForecastV6Refresh
from app.missions.models import MissionRow, PlanRow
from app.operations.models import Store
from app.planning.engine import build_plan
from app.planning.snapshot import prepare

pytestmark = pytest.mark.integration


def request_body():
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return ForecastV6Refresh(
        sku_id="sku_001",
        series_id="series",
        mode="observed",
        activate_for_planning=True,
        observation_end_date=(start - timedelta(days=1)).date(),
        history=[
            {"date": (start - timedelta(days=84 - i)).date(), "sold_quantity": 10, "complete": True}
            for i in range(84)
        ],
    )


def descriptor():
    return dict(
        model_version="v6-test",
        feature_profile="causal",
        minimum_history_days=84,
        recommended_history_days=374,
        weights={"F6": 0.5},
        evaluation={},
        supported_series=[{"series_id": "series"}],
        limitations=["Fixture model"],
    )


def prediction(captured):
    start = datetime.fromisoformat(captured["observation_end_date"]).replace(
        tzinfo=UTC
    ) + timedelta(days=1)
    now = datetime.now(UTC)
    return dict(
        forecast_id="forecast-" + captured["store_id"],
        model_version="v6-test",
        feature_profile="causal",
        series_id="series",
        store_id=captured["store_id"],
        sku_id="sku_001",
        input_state_version=captured["state_version"],
        observation_end_date=captured["observation_end_date"],
        horizon_start=start.isoformat(),
        horizon_end=(start + timedelta(days=7)).isoformat(),
        daily_predictions=[
            {"date": (start + timedelta(days=i)).date().isoformat(), "quantity": 10.0}
            for i in range(7)
        ],
        total_quantity_raw=70.0,
        predicted_quantity=70,
        unit="piece",
        source="model",
        model_name="ShopSteward v6",
        generated_at=now.isoformat(),
        valid_until=(now + timedelta(hours=1)).isoformat(),
        assumptions=[],
        evaluation={},
    )


async def publish(db, seed, cfg, *, demo=False):
    async with db.session() as session:
        captured = await repo.capture(session, cfg.auth_tokens[0], seed["store_id"], request_body())
    if demo:
        captured.update(mode="historical_demo", activate_for_planning=False)
    doc = prediction(captured)
    async with db.session() as session, session.begin():
        binding = await repo.persist(session, cfg.auth_tokens[0], captured, doc, descriptor())
    return captured, doc, binding


async def test_pg_immutable_scope_and_demo_activation_guards(db):
    async with environment(db) as (seed, _):
        cfg = settings(db, seed, forecast_v6_enabled=True)
        _, _, binding = await publish(db, seed, cfg, demo=True)
        for sql, parameters in [
            (
                "UPDATE forecast_v6_inputs SET mode='observed' WHERE id=:id",
                {"id": binding.input_id},
            ),
            ("DELETE FROM forecast_v6_evidence WHERE id=:id", {"id": binding.evidence_id}),
            (
                "UPDATE forecast_v6_bindings SET activate_for_planning=true WHERE store_id=:id",
                {"id": seed["store_id"]},
            ),
        ]:
            with pytest.raises(IntegrityError):
                async with db.session() as session, session.begin():
                    await session.execute(text(sql), parameters)
        async with db.session() as session:
            result = await repo.read_current(session, seed["store_id"], "sku_001", cfg)
        assert result["status"] == "READY" and not result["usable_for_planning"]
        assert result["mode"] == "historical_demo"


async def test_pg_planner_uses_only_midnight_activated_evidence_and_invalidates_old_plan(db):
    async with environment(db) as (seed, client):
        cfg = settings(db, seed, forecast_v6_enabled=True)
        response = await client.post("/api/v1/missions", json=mission_body(seed), headers=headers())
        assert response.status_code == 201, response.text
        mission_id = response.json()["id"]
        original = await prepare(db, mission_id, cfg)
        assert original.snapshot.forecast.source == "fixed"
        draft = build_plan(mission_id, 1, original.snapshot, ttl_seconds=cfg.plan_ttl_seconds)
        old_row = PlanRow(document=draft.model_dump(mode="json"), expires_at=draft.expires_at)
        _, document, _ = await publish(db, seed, cfg)
        invalid = await prepare(db, mission_id, cfg)
        assert invalid.reason == "FORECAST_UNAVAILABLE"
        async with db.session() as session, session.begin():
            store = await session.get(Store, seed["store_id"], with_for_update=True)
            store.simulation_time = datetime.fromisoformat(document["horizon_start"])
        prepared = await prepare(db, mission_id, cfg)
        assert prepared.reason is None
        assert prepared.snapshot.forecast.source == "model"
        assert prepared.snapshot.forecast.remaining_demand == 70
        assert prepared.snapshot.forecast.forecast_id == document["forecast_id"]
        assert (
            prepared.snapshot.forecast.forecast_version
            == original.snapshot.forecast.forecast_version
        )
        active_draft = build_plan(
            mission_id, 2, prepared.snapshot, ttl_seconds=cfg.plan_ttl_seconds
        )
        active_row = PlanRow(
            document=active_draft.model_dump(mode="json"), expires_at=active_draft.expires_at
        )
        async with db.session() as session:
            store = await session.get(Store, seed["store_id"])
            mission = await session.get(MissionRow, mission_id)
            validated = await validate_current(session, store, mission, active_row, cfg)
            assert validated.input_snapshot.forecast.forecast_id == document["forecast_id"]
            with pytest.raises(AppError) as exc:
                await validate_current(session, store, mission, old_row, cfg)
            assert exc.value.code == "STATE_VERSION_CONFLICT"
        async with db.session() as session, session.begin():
            store = await session.get(Store, seed["store_id"], with_for_update=True)
            store.simulation_time += timedelta(seconds=1)
        assert (await prepare(db, mission_id, cfg)).reason == "FORECAST_UNAVAILABLE"


async def test_pg_refresh_rechecks_state_and_preserves_old_evidence(db):
    async with environment(db) as (seed, _):
        cfg = settings(db, seed, forecast_v6_enabled=True)
        captured, document, binding = await publish(db, seed, cfg)
        async with db.session() as session:
            old = deepcopy((await session.get(ForecastV6Evidence, binding.evidence_id)).document)
        with pytest.raises(AppError) as exc:
            async with db.session() as session, session.begin():
                await repo.persist(session, cfg.auth_tokens[0], captured, document, descriptor())
        assert exc.value.code == "FORECAST_INPUT_CHANGED"
        async with db.session() as session:
            assert (await session.get(ForecastV6Evidence, binding.evidence_id)).document == old
            assert (
                await session.get(ForecastV6Binding, (seed["store_id"], "sku_001"))
            ).revision == 1
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ForecastV6Evidence)
                    .where(ForecastV6Evidence.id == binding.evidence_id)
                )
                == 1
            )
