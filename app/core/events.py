"""Пошук сходу й заходу: моменти, коли функція видимості перетинає нуль (docs/MATH.md, §7)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# f(jd) → значення (масив), де > 0 означає «видно». jd — юліанські дати TT.
VisibilityFn = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class Crossing:
    jd: float
    rising: bool  # True — схід (з «не видно» у «видно»), False — захід


def find_crossings(
    fn: VisibilityFn,
    start_jd: float,
    end_jd: float,
    step_hours: float,
    tolerance_minutes: float = 1.0,
) -> list[Crossing]:
    """Усі перетини нуля на [start_jd, end_jd]: груба сітка + векторизована бісекція.

    Крок має бути меншим за найкоротший світлий/темний інтервал: для Сонця з маскою —
    10–20 хв, для Землі — 1 год.
    """
    grid = np.arange(start_jd, end_jd + 1e-12, step_hours / 24.0)
    if grid.size < 2:
        return []
    values = np.asarray(fn(grid), dtype=float)
    positive = values > 0
    idx = np.nonzero(positive[1:] != positive[:-1])[0]
    if idx.size == 0:
        return []
    lo, hi = grid[idx].copy(), grid[idx + 1].copy()
    lo_pos = positive[idx]
    tol = tolerance_minutes / 1440.0
    while np.max(hi - lo) > tol:
        mid = (lo + hi) / 2
        mid_pos = np.asarray(fn(mid), dtype=float) > 0
        same = mid_pos == lo_pos
        lo = np.where(same, mid, lo)
        hi = np.where(same, hi, mid)
    return [Crossing(float((a + b) / 2), not bool(p)) for a, b, p in zip(lo, hi, lo_pos, strict=True)]


def next_crossing(fn: VisibilityFn, start_jd: float, horizon_days: float, step_hours: float,
                  rising: bool, tolerance_minutes: float = 1.0) -> Crossing | None:
    """Найближчий схід (rising=True) або захід після start_jd у межах horizon_days."""
    for c in find_crossings(fn, start_jd, start_jd + horizon_days, step_hours, tolerance_minutes):
        if c.rising == rising:
            return c
    return None
