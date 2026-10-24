"""The merged trial and Mission paths must consume the same activated demand."""

from datetime import datetime, timedelta

import pytest
from test_forecast_v6_persistence import publish
from test_missions import headers
from test_quantity_simulations import request
from test_work_items import env

from app.operations.models import Store
from app.operations.repository import mark_caught_up
from app.planning.snapshot import prepare

pytestmark = pytest.mark.integration


async def setup_forecast(db, seed, settings, *, demo=False):
    async with db.session() as session, session.begin():
        await mark_caught_up(session, seed["scenario_run_id"], 0)
    _, document, _ = await publish(db, seed, settings, demo=demo)
    async with db.session() as session, session.begin():
        store = await session.get(Store, seed["store_id"])
        store.simulation_time = datetime.fromisoformat(document["horizon_start"])
    return document


async def test_activated_model_drives_trial_and_mission_and_disabled_model_invalidates_result(db):
    async with env(db, forecast_v6_enabled=True) as (seed, client, app):
        doc = await setup_forecast(db, seed, app.state.settings)
        response = await client.post(
            f"/api/v1/stores/{seed['store_id']}/simulations",
            json=request(expected_state_version=2),
            headers=headers(),
        )
        assert response.status_code == 201, response.text
        item = response.json()["item"]
        result = item["result"]
        trial = result["calculation"]
        assert trial["input"]["remaining_demand"] == 70  # projection still says 60
        assert trial["input"]["forecast_provider"] == "v6"
        assert trial["input"]["forecast_id"] == doc["forecast_id"]
        assert trial["candidates"][2]["shortage_qty"] == 10
        app.state.settings.forecast_v6_enabled = False
        path = f"/api/v1/work-items/{item['id']}/mission"
        assert (
            await client.post(path, json={"expected_version": 1}, headers=headers())
        ).status_code == 409
        exported = await client.get(
            f"/api/v1/work-items/{item['id']}/results/{result['provenance']['result_id']}",
            headers=headers(),
        )
        assert "模型需求依据已变化或不再适用" in exported.json()["stale_reasons"]
        app.state.settings.forecast_v6_enabled = True
        accepted = await client.post(path, json={"expected_version": 1}, headers=headers())
        assert accepted.status_code == 200, accepted.text
        planned = await prepare(db, accepted.json()["item"]["mission_id"], app.state.settings)
        assert planned.snapshot.forecast.remaining_demand == 70
        assert planned.snapshot.forecast.forecast_id == trial["input"]["forecast_id"]


async def test_inapplicable_active_model_does_not_fall_back_to_old_projection(db):
    async with env(db, forecast_v6_enabled=True) as (seed, client, app):
        await setup_forecast(db, seed, app.state.settings)
        async with db.session() as session, session.begin():
            store = await session.get(Store, seed["store_id"])
            store.simulation_time += timedelta(seconds=1)
        path = f"/api/v1/stores/{seed['store_id']}/simulations"
        denied = await client.post(path, json=request(expected_state_version=2), headers=headers())
        assert denied.status_code == 409
        assert denied.json()["error"]["code"] == "FORECAST_UNAVAILABLE"
        hypothetical = await client.post(
            path,
            json=request(expected_state_version=2, remaining_demand=30, horizon_days=7),
            headers=headers(),
        )
        assert hypothetical.status_code == 201
        assert hypothetical.json()["item"]["mission_request"] is None


async def test_demo_forecast_never_replaces_current_trial_demand(db):
    async with env(db, forecast_v6_enabled=True) as (seed, client, app):
        await setup_forecast(db, seed, app.state.settings, demo=True)
        # The projection's own horizon starts at the original simulation time.
        async with db.session() as session, session.begin():
            store = await session.get(Store, seed["store_id"])
            store.simulation_time = datetime.fromisoformat(seed["simulation_time"])
        result = await client.post(
            f"/api/v1/stores/{seed['store_id']}/simulations",
            json=request(expected_state_version=2),
            headers=headers(),
        )
        assert result.status_code == 201, result.text
        actual = result.json()["item"]["result"]["calculation"]["input"]
        assert actual["forecast_provider"] == "projection" and actual["remaining_demand"] == 60
