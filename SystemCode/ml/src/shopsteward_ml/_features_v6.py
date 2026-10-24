"""Vendored unchanged inference kernels from ShopSteward-forecast; no training imports."""

from __future__ import annotations

import numpy as np
import pandas as pd

EXTRA_COLUMNS = (
    *(f"week_lag_{lag}" for lag in range(1, 13)),
    *(
        f"week_{stat}_{span}"
        for span in (4, 8, 12)
        for stat in ("mean", "median", "std", "zero_rate", "max")
    ),
    *(f"day_{stat}_{span}" for span in (112, 182, 364) for stat in ("mean", "zero_rate")),
    *(f"trend_{span}d_{stat}" for span in (7, 28) for stat in ("delta", "ratio")),
    "annual_target_week_sum",
    "annual_context_mean_28d",
    "target_year_sin",
    "target_year_cos",
    "target_year_progress",
)


def enrich(frame: pd.DataFrame, bundle: dict) -> dict:
    """Return a shallow bundle copy with 42 appended weekly columns and scales.

    Week lag 1 sums origin-6..origin; lag 12 sums origin-83..origin-77.
    Weekly std is population std. Trends compare recent and preceding daily
    means, using their difference and recent / max(previous, 1).

    The annual week is exactly target h1..7 shifted back 364 days: origin-363
    through origin-357 inclusive. Its centered 28-day context is origin-373
    through origin-346, ten days before that week and eleven days after it.
    Calendar phase uses the first target day's zero-based day of year divided
    by that year's length. All dates derive from each visible origin date.

    Missing/incomplete/invalid old observations make their entire containing
    feature window NaN; rows are retained. Extra history is gathered per series,
    never as a panel-sized N x 374 matrix. Original columns, row index, category
    levels, attrs, labels and all other bundle objects are preserved.

    The count data's exact mean28 * 7 baseline is reconstructed by rounding
    normalized float32 history back to integer sales *before* summation. This
    avoids float32 normalization error in F4/F5's baseline and sample weights.
    """
    keys = bundle["keys"]
    weekly = bundle["X_weekly"]
    count = len(keys)
    if len(weekly) != count:
        raise ValueError("WEEKLY_KEY_LENGTH_MISMATCH")
    if any(column in weekly for column in EXTRA_COLUMNS):
        raise ValueError("V6_FEATURES_ALREADY_PRESENT")
    values = np.full((count, len(EXTRA_COLUMNS)), np.nan, dtype=np.float32)
    source_groups = frame.groupby("series_id", sort=False, observed=True).indices
    key_groups = keys.groupby("series_id", sort=False, observed=True).indices
    for sid, rows in key_groups.items():
        if sid not in source_groups:
            raise ValueError(f"SERIES_MISSING: {sid}")
        origins = keys.iloc[rows].origin.to_numpy(dtype=np.int64)
        source = frame.iloc[source_groups[sid]]
        source = source.loc[
            source.day_index.between(int(origins.min()) - 373, int(origins.max()))
        ].sort_values("day_index")
        days = source.day_index.to_numpy(dtype=np.int64)
        if not len(days) or np.any(np.diff(days) == 0):
            raise ValueError("HISTORY_MISSING_OR_DUPLICATE")
        sales = source.sold_quantity.to_numpy(dtype=np.float64)
        valid = np.isfinite(sales) & (sales >= 0)
        if "complete" in source:
            valid &= source.complete.eq(True).to_numpy(dtype=bool)
        sales = np.where(valid, sales, np.nan)
        targets = origins[:, None] + np.arange(-373, 1)
        positions = np.searchsorted(days, targets)
        positions = np.minimum(positions, len(days) - 1)
        history = np.where(days[positions] == targets, sales[positions], np.nan)

        weeks = history[:, -84:].reshape(len(rows), 12, 7).sum(axis=2)[:, ::-1]
        blocks = [weeks]
        for span in (4, 8, 12):
            tail = weeks[:, :span]
            zero_rate = np.where(np.isfinite(tail).all(axis=1), (tail == 0).mean(axis=1), np.nan)
            blocks.append(
                np.column_stack(
                    [
                        tail.mean(axis=1),
                        np.median(tail, axis=1),
                        tail.std(axis=1),
                        zero_rate,
                        tail.max(axis=1),
                    ]
                )
            )
        for span in (112, 182, 364):
            tail = history[:, -span:]
            zero_rate = np.where(np.isfinite(tail).all(axis=1), (tail == 0).mean(axis=1), np.nan)
            blocks.append(np.column_stack([tail.mean(axis=1), zero_rate]))
        for span in (7, 28):
            recent = history[:, -span:].mean(axis=1)
            previous = history[:, -2 * span : -span].mean(axis=1)
            blocks.append(np.column_stack([recent - previous, recent / np.maximum(previous, 1)]))
        blocks.append(
            np.column_stack([history[:, 10:17].sum(axis=1), history[:, :28].mean(axis=1)])
        )

        origin_positions = np.searchsorted(days, origins)
        if np.any(origin_positions >= len(days)) or not np.array_equal(
            days[origin_positions], origins
        ):
            raise ValueError("ORIGIN_DATE_MISSING")
        origin_dates = pd.to_datetime(source.date.iloc[origin_positions]).to_numpy()
        dates = pd.DatetimeIndex(origin_dates + np.timedelta64(1, "D"))
        progress = (dates.dayofyear.to_numpy() - 1) / np.where(dates.is_leap_year, 366, 365)
        blocks.append(
            np.column_stack([np.sin(2 * np.pi * progress), np.cos(2 * np.pi * progress), progress])
        )
        values[rows] = np.column_stack(blocks)

    # Work only on the 28 values needed, keeping memory bounded at large N.
    counts = np.rint(
        np.asarray(bundle["nn_history"][:, -28:], dtype=np.float64)
        * np.asarray(bundle["scale"], dtype=np.float64)[:, None]
    )
    baseline = counts.sum(axis=1) / 4
    appended = pd.DataFrame(values, columns=EXTRA_COLUMNS, index=weekly.index)
    enriched = pd.concat([weekly, appended], axis=1)
    enriched.attrs = weekly.attrs.copy()
    return {
        **bundle,
        "X_weekly": enriched,
        "week_baseline": baseline,
        "week_scale": np.maximum(baseline, 1),
    }
