"""Vendored unchanged inference kernels from ShopSteward-forecast; no training imports."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._constants import (
    ALIGNED_FEATURE_COLUMNS,
    EXTRA_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    HISTORY_FEATURE_COLUMNS,
    ID_CATEGORY_FIELDS,
    OFFSET_DAYS,
    ROLLING_WINDOWS,
    STATE_FEATURE_COLUMNS,
)
from ._state import _state, _windows

METADATA = ("series_id", "item_id", "dept_id", "cat_id", "store_id", "state_id")


NN_CATEGORIES = ("dept_id", "cat_id", "store_id", "state_id")


DAILY_COLUMNS = (*FEATURE_COLUMNS, *EXTRA_FEATURE_COLUMNS["FAS"])


DISABLED_CALENDAR_COLUMNS = (
    "target_snap_flag",
    "target_event_name_1_code",
    "target_event_type_1_code",
    "target_event_name_2_code",
    "target_event_type_2_code",
)


def _history_features(window: np.ndarray) -> np.ndarray:
    blocks = [window[:, -1 - np.array(OFFSET_DAYS)]]
    for span in ROLLING_WINDOWS:
        tail = window[:, -span:]
        blocks.append(
            np.column_stack([tail.mean(1), tail.std(1), tail.sum(1), (tail == 0).mean(1)])
        )
    mean28 = window[:, -28:].mean(1)
    ratio = np.divide(
        window[:, -7:].mean(1), mean28, out=np.full(len(window), np.nan), where=mean28 != 0
    )
    blocks.append(np.column_stack([ratio, mean28 == 0]))
    return np.column_stack(blocks)


def build_examples(
    frame: pd.DataFrame,
    series_ids: list[str],
    origins: list[int],
    mapping: dict,
    include_labels: bool = True,
    *,
    include_daily: bool = True,
) -> dict:
    """Construct series-major examples, each followed by ordered h1..7 daily rows.

    Each source is processed in a vectorized batch of origins. Only the 84-day
    window and static identity at or before the earliest origin feed features.
    Missing history/labels raise instead of silently dropping evaluation rows.
    With ``include_daily=False``, skip all daily feature allocation and expansion;
    return ``X_daily=None`` and exactly the same weekly, neural and label outputs.
    """
    if not series_ids or not origins:
        raise ValueError("NONEMPTY_EXAMPLES_REQUIRED")
    if len(series_ids) != len(set(series_ids)) or len(origins) != len(set(origins)):
        raise ValueError("DUPLICATE_EXAMPLE_KEY")
    if any(isinstance(o, bool) or not isinstance(o, (int, np.integer)) for o in origins):
        raise ValueError("INTEGER_ORIGINS_REQUIRED")
    origin = np.asarray(origins, dtype=np.int32)
    count = len(origin)
    n = len(series_ids) * count
    history = np.empty((n, 84), dtype=np.float32)
    calendar_nn = np.empty((n, 28), dtype=np.float32)
    categories_nn = np.empty((n, 4), dtype=np.int64)
    scale = np.empty(n, dtype=np.float32)
    weights = np.empty((n, 7), dtype=np.float64)
    y = np.empty((n, 7), dtype=np.float32) if include_labels else None
    daily = np.zeros((n * 7, len(DAILY_COLUMNS)), dtype=np.float32) if include_daily else None
    weekly_columns = (
        *HISTORY_FEATURE_COLUMNS,
        *STATE_FEATURE_COLUMNS,
        *(f"{f}_code" for f in ID_CATEGORY_FIELDS),
        "target_week_start_month",
        "target_week_end_month",
        "target_weekend_days",
        "target_week_month_mean",
        *(f"weekday_weight_{h}" for h in range(1, 8)),
    )
    weekly = np.empty((n, len(weekly_columns)), dtype=np.float32)
    groups = frame.groupby("series_id", sort=False, observed=True).indices
    horizons = np.arange(1, 8)
    for i, sid in enumerate(series_ids):
        if sid not in groups:
            raise ValueError(f"SERIES_MISSING: {sid}")
        source = frame.iloc[groups[sid]].sort_values("day_index")
        visible = source.loc[source.day_index.between(int(origin.min()) - 83, int(origin.max()))]
        days = visible.day_index.to_numpy(dtype=np.int64)
        if not len(days) or len(days) != len(np.unique(days)):
            raise ValueError("HISTORY_MISSING_OR_DUPLICATE")
        sales = visible.sold_quantity.to_numpy(dtype=np.float64)
        if "complete" in visible:
            if not visible.complete.isin([True, False, 0, 1]).all():
                raise ValueError("BOOLEAN_COMPLETE_FLAG_REQUIRED")
            sales = np.where(visible.complete.to_numpy(dtype=bool), sales, np.nan)
        window = _windows(days, sales, origin, 84)
        if not np.isfinite(window).all() or (window < 0).any():
            raise ValueError("COMPLETE_NONNEGATIVE_84_DAY_HISTORY_REQUIRED")
        metadata = visible.loc[visible.day_index.le(origin.min())].iloc[-1]
        codes = [
            mapping["fields"][field].get(str(metadata[field]), 0) for field in ID_CATEGORY_FIELDS
        ]
        nn_codes = [
            mapping["fields"][field].get(str(metadata[field]), 0) for field in NN_CATEGORIES
        ]
        base = _history_features(window)
        state = _state(window, np.full(count, 84))
        aligned = window[:, 83 + horizons[:, None] - 7 * np.arange(1, 9)]
        mean28 = window[:, -28:].mean(1)
        # Target dates derive from a visible origin date, so inference needs no future rows.
        origin_dates = pd.to_datetime(visible.set_index("day_index").loc[origin, "date"])
        dates = pd.DatetimeIndex(
            (origin_dates.to_numpy()[:, None] + horizons[None, :] * np.timedelta64(1, "D")).reshape(
                -1
            )
        )
        dow = dates.dayofweek.to_numpy().reshape(count, 7)
        month = dates.month.to_numpy().reshape(count, 7)
        if include_daily:
            shrinkage = 2 * mean28[:, None]
            alignment = np.stack(
                [
                    aligned[:, :, 0],
                    aligned[:, :, 1],
                    aligned[:, :, 3],
                    (aligned[:, :, :4].sum(2) + shrinkage) / 6,
                    (aligned.sum(2) + shrinkage) / 10,
                ],
                axis=2,
            )
            block = daily[i * count * 7 : (i + 1) * count * 7]
            values = {
                name: np.repeat(base[:, j], 7) for j, name in enumerate(HISTORY_FEATURE_COLUMNS)
            }
            values.update(
                {name: np.repeat(state[:, j], 7) for j, name in enumerate(STATE_FEATURE_COLUMNS)}
            )
            values.update(
                {
                    name: alignment[:, :, j].reshape(-1)
                    for j, name in enumerate(ALIGNED_FEATURE_COLUMNS)
                }
            )
            values.update(
                {
                    f"{field}_code": code
                    for field, code in zip(ID_CATEGORY_FIELDS, codes, strict=True)
                }
            )
            values.update(
                target_day_of_week=dow.reshape(-1),
                target_month=month.reshape(-1),
                target_is_weekend=(dow >= 5).reshape(-1),
                horizon_step=np.tile(horizons, count),
            )
            for j, name in enumerate(DAILY_COLUMNS):
                if name in values:
                    block[:, j] = values[name]
        sl = slice(i * count, (i + 1) * count)
        scale[sl] = np.maximum(mean28, 1)
        history[sl] = window / scale[sl, None]
        calendar_nn[sl] = np.stack(
            [
                np.sin(2 * np.pi * dow / 7),
                np.cos(2 * np.pi * dow / 7),
                np.sin(2 * np.pi * month / 12),
                np.cos(2 * np.pi * month / 12),
            ],
            axis=2,
        ).reshape(count, 28)
        categories_nn[sl] = nn_codes
        weights[sl] = (aligned[:, :, :4].sum(2) + 1) / (window[:, -28:].sum(1, keepdims=True) + 7)
        weekly[sl] = np.column_stack(
            [
                base,
                state,
                np.tile(codes, (count, 1)),
                month[:, 0],
                month[:, -1],
                (dow >= 5).sum(1),
                month.mean(1),
                weights[sl],
            ]
        )
        if include_labels:
            target_days = (origin[:, None] + horizons).reshape(-1)
            target = source.set_index("day_index").reindex(target_days)
            labels = target.sold_quantity.to_numpy(dtype=np.float32)
            complete = (
                target.complete.fillna(False).to_numpy(dtype=bool) if "complete" in target else True
            )
            if not np.isfinite(labels).all() or (labels < 0).any() or not np.all(complete):
                raise ValueError("COMPLETE_NONNEGATIVE_LABELS_REQUIRED")
            y[sl] = labels.reshape(count, 7)
    X_daily = pd.DataFrame(daily, columns=DAILY_COLUMNS) if include_daily else None
    X_weekly = pd.DataFrame(weekly, columns=weekly_columns)
    categorical_columns = [f"{field}_code" for field in ID_CATEGORY_FIELDS]
    for field, column in zip(ID_CATEGORY_FIELDS, categorical_columns, strict=True):
        levels = range(len(mapping["fields"][field]) + 1)
        if include_daily:
            X_daily[column] = pd.Categorical(X_daily[column].astype(np.int32), categories=levels)
        X_weekly[column] = pd.Categorical(X_weekly[column].astype(np.int32), categories=levels)
    for features in (X_daily, X_weekly):
        if features is None:
            continue
        features.attrs["categorical_columns"] = categorical_columns
        features.attrs["disabled_calendar_columns"] = list(DISABLED_CALENDAR_COLUMNS)
    return {
        "X_daily": X_daily,
        "X_weekly": X_weekly,
        "nn_history": history,
        "nn_calendar": calendar_nn,
        "nn_categories": categories_nn,
        "scale": scale,
        "weights": weights,
        "y": y,
        "keys": pd.DataFrame(
            {"series_id": np.repeat(series_ids, count), "origin": np.tile(origin, len(series_ids))}
        ),
        "mapping": mapping,
        "cat_sizes": [len(mapping["fields"][field]) + 1 for field in NN_CATEGORIES],
    }
