"""Vendored unchanged inference kernels from ShopSteward-forecast; no training imports."""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

POOLED = {"F6", "F7", "F8"}


def _groups(bundle, arm="F6"):
    field = "dept_id_code" if arm == "F8" else "cat_id_code"
    values = bundle["X_weekly"][field].to_numpy()
    return np.asarray(
        [
            str(int(v))
            if isinstance(v, (float, np.floating)) and np.isfinite(v) and v.is_integer()
            else str(v)
            for v in values
        ]
    )


def _scale(bundle):
    scale = np.asarray(bundle["week_scale"], dtype=float)
    if (
        scale.shape != (len(bundle["X_weekly"]),)
        or not np.isfinite(scale).all()
        or (scale < 1).any()
    ):
        raise ValueError("INVALID_WEEK_SCALE")
    return scale


def _restore(arm, raw, bundle, rows):
    if arm == "F4":
        raw = raw + np.asarray(bundle["week_baseline"], dtype=float)[rows]
    elif arm == "F5":
        raw = raw * _scale(bundle)[rows]
    if not np.isfinite(raw).all():
        raise ValueError("NONFINITE_WEEKLY_PREDICTION")
    return np.maximum(raw, 0)


def predict(model, bundle):
    """Restore weekly units, then apply the causal seven weekday weights."""
    features = bundle["X_weekly"]
    weights = np.asarray(bundle["weights"], dtype=float)
    if (
        weights.shape != (len(features), 7)
        or not np.isfinite(weights).all()
        or (weights < 0).any()
        or not np.allclose(weights.sum(axis=1), 1)
    ):
        raise ValueError("INVALID_WEEKDAY_WEIGHTS")
    if not len(features):
        return np.empty((0, 7), dtype=float)
    boosters = model["boosters"]
    threads = model.get("threads", 4)
    raw = np.asarray(boosters["all"].predict(features, num_threads=threads))
    if model["arm"] in POOLED:
        groups = _groups(bundle, model["arm"])
        for group, booster in boosters.items():
            if group == "all":
                continue
            rows = np.flatnonzero(groups == group)
            if rows.size:
                raw[rows] = booster.predict(features.iloc[rows], num_threads=threads)
    weekly = _restore(model["arm"], raw, bundle, np.arange(len(features)))
    return weekly[:, None] * weights


def load(path):
    path = Path(path)
    info = json.loads((path / "info.json").read_text(encoding="utf-8"))
    return {
        "arm": info["arm"],
        "threads": info.get("threads", 4),
        "info": info,
        "boosters": {
            group: lgb.Booster(model_file=str(path / filename))
            for group, filename in info["model_files"].items()
        },
    }
