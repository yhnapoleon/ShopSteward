"""Vendored unchanged inference kernels from ShopSteward-forecast; no training imports."""

from __future__ import annotations

import numpy as np


def _windows(days, values, origins, span):
    requested = origins[:, None] + np.arange(1 - span, 1)
    indices = np.searchsorted(days, requested)
    safe = np.minimum(indices, len(days) - 1)
    present = (indices < len(days)) & (days[safe] == requested)
    return np.where(present, values[safe], np.nan)


def _state(window, length):
    active = np.arange(84)[None, :] >= (84 - length[:, None])
    positive = active & (window > 0)
    count = positive.sum(axis=1)
    positions = np.where(positive, np.arange(84), -1)
    last = positions.max(axis=1)
    pmean = np.divide(
        np.where(positive, window, 0).sum(axis=1),
        count,
        out=np.full(len(window), np.nan),
        where=count > 0,
    )
    pvar = np.divide(
        np.where(positive, (window - pmean[:, None]) ** 2, 0).sum(axis=1),
        count,
        out=np.full(len(window), np.nan),
        where=count > 0,
    )
    previous = np.maximum.accumulate(positions, axis=1)
    previous = np.column_stack([np.full(len(window), -1), previous[:, :-1]])
    has_gap = positive & (previous >= 0)
    gaps = np.arange(84)[None, :] - previous
    gap_count = has_gap.sum(axis=1)
    gmean = np.divide(
        np.where(has_gap, gaps, 0).sum(axis=1),
        gap_count,
        out=np.full(len(window), np.nan),
        where=gap_count > 0,
    )
    gvar = np.divide(
        np.where(has_gap, (gaps - gmean[:, None]) ** 2, 0).sum(axis=1),
        gap_count,
        out=np.full(len(window), np.nan),
        where=gap_count > 0,
    )
    occurrence = np.full(len(window), np.nan)
    magnitude = np.full(len(window), np.nan)
    # Vectorize across origins; preserve the scalar recurrence's exact ordering.
    for i in range(84):
        event = positive[:, i].astype(float)
        updated = np.where(
            np.isnan(occurrence), event, (2 / 29) * event + (1 - 2 / 29) * occurrence
        )
        occurrence = np.where(active[:, i], updated, occurrence)
        updated = np.where(np.isnan(magnitude), window[:, i], 0.2 * window[:, i] + 0.8 * magnitude)
        magnitude = np.where(positive[:, i], updated, magnitude)
    return np.column_stack(
        [
            length,
            (active & (window == 0)).sum(axis=1) / length,
            np.where(active, window, 0).sum(axis=1) / length,
            count,
            np.where(count >= 2, pvar / pmean**2, np.nan),
            np.where(count > 0, 83 - last, length),
            count == 0,
            gmean,
            np.where(count >= 3, gvar / gmean**2, np.nan),
            occurrence,
            magnitude,
        ]
    )
