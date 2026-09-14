"""Boundary and persistence tests run without the isolated torch service or PostgreSQL."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings, TokenGrant
from app.core.errors import AppError
from app.forecast_v6 import repository as repo
from app.forecast_v6.models import ForecastV6Binding, ForecastV6Evidence
from app.forecast_v6.schemas import ForecastV6Refresh
from app.main import create_app
from app.operations.models import ProductRow, StockRow, Store
from app.planning.snapshot import v6_snapshot

NOW = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)
TOKEN = "forecast-operator-token-long-enough"


class MemoryDB:
    def __init__(self):
        self.rows = {}
        self.open_sessions = 0
        self.add(
            Store(id="store", scenario_run_id="scenario", state_version=4, simulation_time=NOW)
        )
        self.add(ProductRow(store_id="store", sku_id="sku", document={}))
        self.add(
            StockRow(
                store_id="store",
                sku_id="sku",
                forecast_version="fixed-1",
                remaining_demand=90,
                on_hand=10,
                in_transit=0,
            )
        )

    @asynccontextmanager
    async def session(self):
        self.open_sessions += 1
        try:
            yield self
        finally:
            self.open_sessions -= 1

    @asynccontextmanager
    async def begin(self):
        yield self

    async def get(self, model, key, **kwargs):
        return self.rows.get((model, key))

    def add(self, row):
        key = (
            (row.store_id, row.sku_id)
            if isinstance(row, (ProductRow, StockRow, ForecastV6Binding))
            else row.id
        )
        self.rows[type(row), key] = row

    async def flush(self):
        pass

    async def dispose(self):
        pass


def settings(role="operator", stores=None):
    return Settings(
        app_env="test",
        forecast_v6_enabled=True,
        forecast_v6_token="ml-token",
        auth_tokens=[
            TokenGrant(
                token=TOKEN,
                principal_id="tester",
                roles=[role],
                store_ids=stores if stores is not None else ["store"],
            )
        ],
    )


def history():
    return [
        {
            "date": (NOW - timedelta(days=84 - i)).date().isoformat(),
            "sold_quantity": 2,
            "complete": True,
        }
        for i in range(84)
    ]


def body(**changes):
    value = dict(
        sku_id="sku",
        series_id="series",
        mode="observed",
        history=history(),
        observation_end_date="2026-09-10",
        activate_for_planning=False,
    )
    value.update(changes)
    return ForecastV6Refresh.model_validate(value)


def model():
    return dict(
        model_version="v6",
        feature_profile="causal",
        minimum_history_days=84,
        recommended_history_days=374,
        weights={"F6": 0.5},
        evaluation={"wape": 0.34976},
        supported_series=[{"series_id": "series"}],
        limitations=["Historical evaluation"],
    )


def prediction(captured=None):
    return dict(
        forecast_id="forecast-v6",
        store_id="store",
        sku_id="sku",
        series_id="series",
        input_state_version=4 if captured is None else captured["state_version"],
        model_version="v6",
        feature_profile="causal",
        observation_end_date="2026-09-10",
        horizon_start=NOW.isoformat(),
        horizon_end=(NOW + timedelta(days=7)).isoformat(),
        daily_predictions=[
            {"date": (NOW + timedelta(days=i)).date().isoformat(), "quantity": 1.1}
            for i in range(7)
        ],
        total_quantity_raw=7.7,
        predicted_quantity=8,
        unit="piece",
        source="model",
        model_name="ShopSteward v6",
        generated_at=(NOW - timedelta(seconds=1)).isoformat(),
        valid_until=(NOW + timedelta(hours=24)).isoformat(),
        assumptions=[],
        evaluation={},
    )


async def saved(db, *, mode="observed", active=False):
    cfg = settings()
    captured = await repo.capture(
        db, cfg.auth_tokens[0], "store", body(activate_for_planning=active)
    )
    captured["mode"] = mode
    await repo.persist(db, cfg.auth_tokens[0], captured, prediction(), model(), NOW)
    return cfg, captured


@pytest.mark.parametrize(
    "mutation",
    [
        "gap",
        "duplicate",
        "incomplete",
        "too_short",
        "wrong_cutoff",
        "bool_quantity",
        "demo_activate",
    ],
)
def test_history_contract(mutation):
    data = dict(
        sku_id="sku",
        series_id="series",
        mode="observed",
        history=history(),
        observation_end_date="2026-09-10",
    )
    if mutation == "gap":
        data["history"].pop(40)
    elif mutation == "duplicate":
        data["history"][40] = data["history"][39]
    elif mutation == "incomplete":
        data["history"][40]["complete"] = False
    elif mutation == "too_short":
        data["history"] = data["history"][:80]
    elif mutation == "wrong_cutoff":
        data["observation_end_date"] = "2026-09-09"
    elif mutation == "bool_quantity":
        data["history"][40]["sold_quantity"] = True
    else:
        data.update(mode="historical_demo", activate_for_planning=True)
    with pytest.raises(ValidationError):
        ForecastV6Refresh.model_validate(data)


@pytest.mark.asyncio
async def test_current_empty_and_disabled_never_infer():
    db = MemoryDB()
    assert (await repo.read_current(db, "store", "sku", settings(), NOW))["status"] == "UNAVAILABLE"
    cfg = settings()
    cfg.forecast_v6_enabled = False
    assert (await repo.read_current(db, "store", "sku", cfg, NOW))[
        "reason"
    ] == "FORECAST_V6_DISABLED"
    assert len(db.rows) == 3


@pytest.mark.asyncio
async def test_immutable_evidence_reused_input_and_state_revision():
    db = MemoryDB()
    cfg, _ = await saved(db)
    current = await repo.read_current(db, "store", "sku", cfg, NOW)
    assert current["status"] == "READY" and current["forecast"]["input_state_version"] == 4
    assert (await db.get(Store, "store")).state_version == 5
    old = deepcopy(current)
    captured = await repo.capture(db, cfg.auth_tokens[0], "store", ForecastV6Refresh(sku_id="sku"))
    assert captured["history"] == history() and captured["state_version"] == 5
    await repo.persist(db, cfg.auth_tokens[0], captured, prediction(captured), model(), NOW)
    assert len([r for r in db.rows.values() if isinstance(r, ForecastV6Evidence)]) == 2
    assert old["forecast"] == prediction()
    assert (await db.get(StockRow, ("store", "sku"))).forecast_version == "fixed-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["state", "scenario", "binding"])
async def test_inference_race_rejected_before_write(kind):
    db = MemoryDB()
    cfg, _ = await saved(db)
    captured = await repo.capture(db, cfg.auth_tokens[0], "store", ForecastV6Refresh(sku_id="sku"))
    if kind == "state":
        (await db.get(Store, "store")).state_version += 1
    elif kind == "scenario":
        (await db.get(Store, "store")).scenario_run_id = "replacement"
    else:
        (await db.get(ForecastV6Binding, ("store", "sku"))).revision += 1
    count = len(db.rows)
    with pytest.raises(AppError, match="changed"):
        await repo.persist(db, cfg.auth_tokens[0], captured, prediction(captured), model(), NOW)
    assert len(db.rows) == count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,reason",
    [
        ("expired", "FORECAST_EXPIRED"),
        ("state", "STORE_STATE_CHANGED"),
        ("scope", "FORECAST_SCOPE_MISMATCH"),
    ],
)
async def test_stale_or_wrong_scope_not_usable(kind, reason):
    db = MemoryDB()
    cfg, _ = await saved(db, active=True)
    if kind == "state":
        (await db.get(Store, "store")).state_version += 1
    elif kind == "scope":
        evidence = next(row for row in db.rows.values() if isinstance(row, ForecastV6Evidence))
        evidence.document = prediction() | {"store_id": "another-store"}
    current = await repo.read_current(
        db, "store", "sku", cfg, NOW + timedelta(days=2) if kind == "expired" else NOW
    )
    assert current["status"] != "READY" and current["reason"] == reason
    assert not current["usable_for_planning"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,active,offset,usable",
    [
        ("historical_demo", False, 0, False),
        ("observed", False, 0, False),
        ("observed", True, 0, True),
        ("observed", True, 1, False),
        ("observed", True, 86400, False),
    ],
)
async def test_planning_requires_explicit_observed_first_midnight(mode, active, offset, usable):
    db = MemoryDB()
    cfg, _ = await saved(db, mode=mode, active=active)
    (await db.get(Store, "store")).simulation_time = NOW + timedelta(seconds=offset)
    current = await repo.read_current(db, "store", "sku", cfg, NOW)
    assert current["usable_for_planning"] is usable
    assert current["activate_for_planning"] is active
    if mode == "historical_demo":
        assert "HISTORICAL_DEMO_ONLY" in current["reason"]
    if usable:
        stock = await db.get(StockRow, ("store", "sku"))
        snap = v6_snapshot(current["forecast"], stock, SimpleNamespace(last_sequence=3))
        assert snap.remaining_demand == 8 and snap.forecast_version == stock.forecast_version
        assert snap.forecast_id == "forecast-v6" and "midnight" in " ".join(snap.assumptions)


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_id", "other"),
        ("input_state_version", 99),
        ("model_version", "other"),
        ("predicted_quantity", 14),
        ("horizon_start", "2026-09-11T01:00:00+00:00"),
        ("total_quantity_raw", 100),
        ("unit", "box"),
    ],
)
def test_external_evidence_binding_and_sum_validated(field, value):
    captured = dict(
        store_id="store",
        sku_id="sku",
        series_id="series",
        state_version=4,
        observation_end_date="2026-09-10",
    )
    with pytest.raises(ValueError):
        repo.validate_response(prediction() | {field: value}, model(), captured, NOW)


@pytest.mark.asyncio
async def test_observed_requires_import_and_cannot_rebind_using_old_history():
    db = MemoryDB()
    cfg = settings()
    with pytest.raises(AppError):
        await repo.capture(
            db,
            cfg.auth_tokens[0],
            "store",
            ForecastV6Refresh(sku_id="sku", series_id="series", mode="observed"),
        )
    await saved(db)
    with pytest.raises(AppError):
        await repo.capture(
            db, cfg.auth_tokens[0], "store", ForecastV6Refresh(sku_id="sku", series_id="different")
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "offset,reason", [(-1, "FORECAST_HORIZON_FUTURE"), (604800, "FORECAST_HORIZON_ELAPSED")]
)
async def test_observed_outside_business_horizon_is_stale_even_without_activation(offset, reason):
    db = MemoryDB()
    cfg, _ = await saved(db)
    (await db.get(Store, "store")).simulation_time = NOW + timedelta(seconds=offset)
    current = await repo.read_current(db, "store", "sku", cfg, NOW)
    assert current["status"] == "STALE" and current["reason"] == reason
    assert current["forecast"] is not None and not current["usable_for_planning"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,stores,status",
    [("viewer", ["store"], 403), ("operator", ["other"], 404), ("admin", [], 200)],
)
async def test_http_refresh_role_scope_and_network_outside_transaction(
    monkeypatch, role, stores, status
):
    import app.forecast_v6.router as routes

    db = MemoryDB()
    app = create_app(settings(role, stores))
    app.state.db = db
    calls = []

    @asynccontextmanager
    async def connect(_settings):
        assert db.open_sessions == 0
        yield object()

    async def remote(client, method, path, **kwargs):
        assert db.open_sessions == 0
        calls.append(path)
        if path == "/v1/model":
            return model()
        doc = prediction()
        now = datetime.now(UTC)
        doc.update(
            generated_at=(now - timedelta(seconds=1)).isoformat(),
            valid_until=(now + timedelta(hours=1)).isoformat(),
        )
        return doc

    monkeypatch.setattr(routes, "connect", connect)
    monkeypatch.setattr(routes, "json_request", remote)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/stores/store/forecast/refresh",
            headers={"Authorization": "Bearer " + TOKEN},
            json=body().model_dump(mode="json"),
        )
    assert response.status_code == status, response.text
    assert calls == (["/v1/model", "/v1/predict"] if status == 200 else [])
    if status == 200:
        assert response.json()["status"] == "READY"


@pytest.mark.asyncio
async def test_http_viewer_current_read_and_missing_sku():
    db = MemoryDB()
    app = create_app(settings("viewer"))
    app.state.db = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + TOKEN},
    ) as client:
        response = await client.get("/api/v1/stores/store/forecast?sku_id=sku")
        assert response.status_code == 200 and response.json()["status"] == "UNAVAILABLE"
        assert (await client.get("/api/v1/stores/store/forecast?sku_id=missing")).status_code == 404
        assert (await client.get("/api/v1/stores/other/forecast?sku_id=sku")).status_code == 404
