"""Vendored unchanged inference kernels from ShopSteward-forecast; no training imports."""

from __future__ import annotations

ID_CATEGORY_FIELDS = ("store_id", "item_id", "dept_id", "cat_id", "state_id")


EVENT_CATEGORY_FIELDS = (
    "event_name_1",
    "event_type_1",
    "event_name_2",
    "event_type_2",
)


CATEGORY_FIELDS = ID_CATEGORY_FIELDS + EVENT_CATEGORY_FIELDS


OFFSET_DAYS = (0, 1, 6, 13, 27)


ROLLING_WINDOWS = (7, 14, 28)


HISTORY_FEATURE_COLUMNS = (
    tuple(f"offset_{offset}" for offset in OFFSET_DAYS)
    + tuple(
        f"rolling_{stat}_{window}"
        for window in ROLLING_WINDOWS
        for stat in ("mean", "std", "sum", "zero_ratio")
    )
    + ("mean_7_to_28_ratio", "mean_7_to_28_ratio_missing")
)


CALENDAR_FEATURE_COLUMNS = (
    "target_day_of_week",
    "target_month",
    "target_is_weekend",
    "target_snap_flag",
) + tuple(f"target_{field}_code" for field in EVENT_CATEGORY_FIELDS)


CATEGORY_FEATURE_COLUMNS = tuple(f"{field}_code" for field in ID_CATEGORY_FIELDS)


FEATURE_COLUMNS = (
    HISTORY_FEATURE_COLUMNS
    + CALENDAR_FEATURE_COLUMNS
    + CATEGORY_FEATURE_COLUMNS
    + ("horizon_step",)
)

ALIGNED_FEATURE_COLUMNS = (
    "aligned_lag_7",
    "aligned_lag_14",
    "aligned_lag_28",
    "weekday_mean_4_shrunk",
    "weekday_mean_8_shrunk",
)


STATE_FEATURE_COLUMNS = (
    "history_n84",
    "zero_ratio84",
    "mean84",
    "positive_count84",
    "positive_cv2_84",
    "days_since_positive84",
    "no_positive84",
    "mean_gap84",
    "gap_cv2_84",
    "occurrence_ewma84",
    "positive_ewma84",
)


PRICE_FEATURE_COLUMNS = (
    "price_relative28",
    "price_log_change7",
    "price_observed_count28",
    "price_age28",
    "price_current_missing",
)


_BLOCK_COLUMNS = {
    "A": ALIGNED_FEATURE_COLUMNS,
    "S": STATE_FEATURE_COLUMNS,
    "P": PRICE_FEATURE_COLUMNS,
}


_CONFIG_BLOCKS = {
    "F0": (),
    "FA": ("A",),
    "FS": ("S",),
    "FAS": ("A", "S"),
    "FASP": ("A", "S", "P"),
}


EXTRA_FEATURE_COLUMNS = {
    config: tuple(name for block in blocks for name in _BLOCK_COLUMNS[block])
    for config, blocks in _CONFIG_BLOCKS.items()
}
