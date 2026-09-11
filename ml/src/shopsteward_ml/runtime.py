"""Load portable frozen components and infer exclusively from request history."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import lightgbm as lgb
import numpy as np
import pandas as pd

from ._features_v5 import build_examples
from ._features_v6 import enrich
from ._neural import load_neural, predict_neural
from ._trees_v6 import load as load_tree
from ._trees_v6 import predict as predict_tree
from .schemas import PredictRequest

WEIGHTS = {"F6": 0.5, "F3": 0.25, "W2": 0.125, "N3": 0.125}


class ForecastRuntime:
    def __init__(self, bundle: Path):
        self.bundle = Path(bundle).resolve()
        self.manifest = json.loads((self.bundle / "manifest.json").read_text(encoding="utf-8"))
        if (
            self.manifest.get("schema_version") != "shopsteward-v6-bundle-v1"
            or self.manifest.get("weights") != WEIGHTS
        ):
            raise ValueError("UNSUPPORTED_MODEL_BUNDLE")
        for name, expected in self.manifest["sha256"].items():
            path = (self.bundle / name).resolve()
            if (
                not path.is_relative_to(self.bundle)
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("BUNDLE_INTEGRITY_FAILURE")
        rows = json.loads((self.bundle / "series.json").read_text(encoding="utf-8"))
        self.series = {row["series_id"]: row for row in rows}
        if len(self.series) != 300 or len(rows) != 300:
            raise ValueError("EXPECTED_300_UNIQUE_SERIES")
        self.models, self.mappings = {}, {}
        for arm in WEIGHTS:
            path = self.bundle / "components" / arm
            self.mappings[arm] = json.loads((path / "mapping.json").read_text(encoding="utf-8"))
            if arm in ("F6", "F3"):
                self.models[arm] = load_tree(path)
            elif arm == "W2":
                self.models[arm] = lgb.Booster(model_file=str(path / "model.txt"))
            else:
                self.models[arm] = load_neural(path / "model.pt")
        self.bundle_digest = hashlib.sha256(
            json.dumps(self.manifest, sort_keys=True).encode()
        ).hexdigest()
        self.lock = threading.Lock()

    def descriptor(self):
        fields = (
            "model_version",
            "feature_profile",
            "minimum_history_days",
            "recommended_history_days",
            "weights",
            "evaluation",
            "limitations",
        )
        return copy.deepcopy(
            {
                **{field: self.manifest[field] for field in fields},
                "supported_series": list(self.series.values()),
            }
        )

    def demo_history(self, series_id):
        if series_id not in self.series:
            raise ValueError("UNSUPPORTED_SERIES")
        # Explicitly isolated from predict: demo data is only loaded by this endpoint.
        return json.loads(
            (self.bundle / "demo-history" / f"{series_id}.json").read_text(encoding="utf-8")
        )

    def history_frame(self, request: PredictRequest):
        if request.series_id not in self.series:
            raise ValueError("UNSUPPORTED_SERIES")
        frame = pd.DataFrame([row.model_dump() for row in request.history])
        frame["date"] = pd.to_datetime(frame.date)
        frame["day_index"] = np.arange(1, len(frame) + 1)
        for field, value in self.series[request.series_id].items():
            frame[field] = value
        return frame

    def predict_components(self, request: PredictRequest):
        frame = self.history_frame(request)
        result = {}
        with self.lock:
            for arm in WEIGHTS:
                features = build_examples(
                    frame,
                    [request.series_id],
                    [len(frame)],
                    self.mappings[arm],
                    include_labels=False,
                    include_daily=False,
                )
                if arm in ("F6", "F3"):
                    result[arm] = predict_tree(self.models[arm], enrich(frame, features))[0]
                elif arm == "W2":
                    raw = self.models[arm].predict(features["X_weekly"], num_threads=4)
                    result[arm] = (np.maximum(raw, 0)[:, None] * features["weights"])[0]
                else:
                    result[arm] = predict_neural(self.models[arm], features)[0]
        if any(
            np.asarray(values).shape != (7,) or not np.isfinite(values).all() or (values < 0).any()
            for values in result.values()
        ):
            raise ValueError("INVALID_MODEL_OUTPUT")
        return result

    def predict(self, request: PredictRequest):
        components = self.predict_components(request)
        values = sum(
            weight * np.asarray(components[arm], dtype=np.float64)
            for arm, weight in WEIGHTS.items()
        )
        total = float(values.sum())
        now = datetime.now(UTC)
        start_date = request.observation_end_date + timedelta(days=1)
        local_zone = ZoneInfo(request.timezone)
        start = datetime.combine(start_date, time.min, local_zone)
        end = datetime.combine(start_date + timedelta(days=7), time.min, local_zone)
        canonical = json.dumps(
            {"bundle": self.bundle_digest, "request": request.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "forecast_id": "v6-" + hashlib.sha256(canonical.encode()).hexdigest(),
            "model_version": self.manifest["model_version"],
            "feature_profile": self.manifest["feature_profile"],
            "series_id": request.series_id,
            "store_id": request.store_id,
            "sku_id": request.sku_id,
            "input_state_version": request.input_state_version,
            "observation_end_date": request.observation_end_date.isoformat(),
            "horizon_start": start.isoformat(),
            "horizon_end": end.isoformat(),
            "daily_predictions": [
                {"date": (start_date + timedelta(days=i)).isoformat(), "quantity": float(value)}
                for i, value in enumerate(values)
            ],
            "total_quantity_raw": total,
            "predicted_quantity": math.ceil(total),
            "unit": "piece",
            "generated_at": now.isoformat(),
            "valid_until": (now + timedelta(hours=24)).isoformat(),
            "source": "model",
            "model_name": "ShopSteward v6",
            "assumptions": [
                "Seven daily point forecasts; horizon_end is exclusive.",
                "Only explicitly supplied complete history was used; no future sales or implicit zero filling.",
                f"{len(request.history)} history days; unavailable annual/long-window features remain missing.",
                "Selected M5 identity is an explicit proxy for the business SKU; forecast is not purchase quantity.",
                "Validity is a 24-hour evidence lifetime; consumers must separately match business forecast dates.",
            ],
            "evaluation": copy.deepcopy(self.manifest["evaluation"]),
        }
