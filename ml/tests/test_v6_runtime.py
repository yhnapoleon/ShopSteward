from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from shopsteward_ml.schemas import PredictRequest


def request_data(n=84):
    end = date(2026, 9, 10)
    return {
        "store_id": "store_1",
        "sku_id": "sku_1",
        "series_id": "FOODS_1_001_CA_1",
        "observation_end_date": end.isoformat(),
        "timezone": "UTC",
        "input_state_version": 1,
        "history": [
            {
                "date": (end - timedelta(days=n - i - 1)).isoformat(),
                "sold_quantity": i % 5,
                "complete": True,
            }
            for i in range(n)
        ],
    }


@pytest.mark.parametrize("n", [84, 374])
def test_history_boundaries(n):
    assert len(PredictRequest.model_validate(request_data(n)).history) == n


@pytest.mark.parametrize("n", [0, 83, 375])
def test_history_out_of_bounds(n):
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(request_data(n))


@pytest.mark.parametrize(
    "mutation",
    [
        "gap",
        "duplicate",
        "future",
        "incomplete",
        "negative",
        "boolean_quantity",
        "string_quantity",
        "fractional",
        "boolean_version",
        "timezone",
        "extra",
    ],
)
def test_strict_causal_input(mutation):
    body = request_data()
    if mutation == "gap":
        body["history"][1]["date"] = "2026-01-01"
    if mutation == "duplicate":
        body["history"][1]["date"] = body["history"][0]["date"]
    if mutation == "future":
        body["observation_end_date"] = "2026-09-09"
    if mutation == "incomplete":
        body["history"][0]["complete"] = False
    if mutation == "negative":
        body["history"][0]["sold_quantity"] = -1
    if mutation == "boolean_quantity":
        body["history"][0]["sold_quantity"] = True
    if mutation == "string_quantity":
        body["history"][0]["sold_quantity"] = "1"
    if mutation == "fractional":
        body["history"][0]["sold_quantity"] = 0.5
    if mutation == "boolean_version":
        body["input_state_version"] = True
    if mutation == "timezone":
        body["timezone"] = "not/a/timezone"
    if mutation == "extra":
        body["future_sales"] = [100]
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(body)


import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from shopsteward_ml.runtime import ForecastRuntime
from shopsteward_ml.service import create_app

BUNDLE = Path(__file__).resolve().parents[2] / "var/forecast-v6/bundle"


@pytest.fixture(scope="module")
def runtime():
    return ForecastRuntime(BUNDLE)


@pytest.fixture(scope="module")
def client(runtime):
    with TestClient(create_app(runtime=runtime, token="test-only-token")) as app:
        yield app


def test_authenticated_readiness_and_descriptor(client):
    assert client.get("/health/ready").status_code == 401
    assert client.get("/v1/model", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.get("/health/ready", headers={"Authorization": "Bearer test-only-token"}).json()[
            "ready"
        ]
        is True
    )
    descriptor = client.get("/v1/model", headers={"Authorization": "Bearer test-only-token"}).json()
    assert len(descriptor["supported_series"]) == 300
    assert descriptor["weights"] == {"F6": 0.5, "F3": 0.25, "W2": 0.125, "N3": 0.125}


def test_real_http_prediction_matches_historical_reference(client, runtime):
    headers = {"Authorization": "Bearer test-only-token"}
    sid = runtime.descriptor()["supported_series"][0]["series_id"]
    demo = client.get("/v1/demo-history/" + sid, headers=headers).json()
    assert len(demo["history"]) == 374 and demo["observation_end_date"] == "2016-03-27"
    body = {
        "store_id": "business-store",
        "sku_id": "business-sku",
        "series_id": sid,
        "history": demo["history"],
        "observation_end_date": demo["observation_end_date"],
        "input_state_version": 1,
        "timezone": "UTC",
    }
    response = client.post("/v1/predict", json=body, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    expected = json.loads((BUNDLE / "parity-reference.json").read_text())["champion"]
    points = sorted([p for p in expected if p["series_id"] == sid], key=lambda p: p["horizon_step"])
    np.testing.assert_allclose(
        [p["quantity"] for p in result["daily_predictions"]],
        [p["predicted"] for p in points],
        rtol=1e-6,
        atol=1e-6,
    )
    assert result["predicted_quantity"] == __import__("math").ceil(result["total_quantity_raw"])
    assert (
        result["forecast_id"]
        == client.post("/v1/predict", json=body, headers=headers).json()["forecast_id"]
    )
    changed = dict(body, store_id="different-store")
    assert (
        result["forecast_id"]
        != client.post("/v1/predict", json=changed, headers=headers).json()["forecast_id"]
    )
    body["history"][-1]["date"] = "2016-03-28"
    assert client.post("/v1/predict", json=body, headers=headers).status_code == 422


def test_unknown_series_is_not_zero(client):
    response = client.post(
        "/v1/predict", json=request_data(), headers={"Authorization": "Bearer test-only-token"}
    )
    # This synthetic identity is not in the selected 300; it must never silently map to UNKNOWN.
    assert response.status_code == 422
    assert (
        client.get(
            "/v1/demo-history/missing", headers={"Authorization": "Bearer test-only-token"}
        ).status_code
        == 404
    )


def test_future_sales_cannot_reach_feature_kernels(runtime):
    import pandas as pd

    from shopsteward_ml._features_v5 import build_examples
    from shopsteward_ml._features_v6 import enrich

    sid = runtime.descriptor()["supported_series"][0]["series_id"]
    demo = runtime.demo_history(sid)
    request = PredictRequest.model_validate(
        {
            "store_id": "s",
            "sku_id": "k",
            "series_id": sid,
            "history": demo["history"],
            "observation_end_date": demo["observation_end_date"],
            "input_state_version": 1,
        }
    )
    frame = runtime.history_frame(request)
    original = enrich(
        frame,
        build_examples(
            frame,
            [sid],
            [len(frame)],
            runtime.mappings["F6"],
            include_labels=False,
            include_daily=False,
        ),
    )
    future = frame.iloc[[-1]].copy()
    future["day_index"] += 1
    future["date"] += pd.Timedelta(days=1)
    future["sold_quantity"] = 1_000_000_000
    contaminated = pd.concat([frame, future], ignore_index=True)
    rebuilt = enrich(
        contaminated,
        build_examples(
            contaminated,
            [sid],
            [len(frame)],
            runtime.mappings["F6"],
            include_labels=False,
            include_daily=False,
        ),
    )
    pd.testing.assert_frame_equal(original["X_weekly"], rebuilt["X_weekly"])
    np.testing.assert_array_equal(original["nn_history"], rebuilt["nn_history"])


def test_all_300_series_component_parity(runtime):
    references = json.loads((BUNDLE / "parity-reference.json").read_text())
    expected = {arm: {} for arm in references}
    for arm, points in references.items():
        for point in points:
            expected[arm].setdefault(point["series_id"], []).append(point["predicted"])
    for sid in runtime.series:
        demo = runtime.demo_history(sid)
        request = PredictRequest.model_validate(
            {
                "store_id": "s",
                "sku_id": "k",
                "series_id": sid,
                "history": demo["history"],
                "observation_end_date": demo["observation_end_date"],
                "input_state_version": 1,
            }
        )
        for arm, values in runtime.predict_components(request).items():
            np.testing.assert_allclose(
                values, expected[arm][sid], rtol=1e-6, atol=1e-6, err_msg=f"{sid}/{arm}"
            )


def test_minimum_history_and_timezone_horizon(runtime):
    sid = next(iter(runtime.series))
    demo = runtime.demo_history(sid)
    request = PredictRequest.model_validate(
        {
            "store_id": "s",
            "sku_id": "k",
            "series_id": sid,
            "history": demo["history"][-84:],
            "observation_end_date": demo["observation_end_date"],
            "timezone": "Asia/Shanghai",
            "input_state_version": 1,
        }
    )
    result = runtime.predict(request)
    assert result["horizon_start"] == "2016-03-28T00:00:00+08:00"
    assert result["horizon_end"] == "2016-04-04T00:00:00+08:00"
    assert all(point["quantity"] >= 0 for point in result["daily_predictions"])
