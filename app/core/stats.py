"""Статистика за період (docs/MATH.md, §8, §10): години Сонця/зв'язку, найдовша ніч."""

from __future__ import annotations

import numpy as np


def total_hours(weights, step_hours: float) -> float:
    """Σ wᵢ·Δt. weights — частка (0…1) або булеві значення видимості на рівномірній сітці."""
    return float(np.sum(np.asarray(weights, dtype=float)) * step_hours)


def fraction_of_time(weights) -> float:
    w = np.asarray(weights, dtype=float)
    return float(w.mean()) if w.size else 0.0


def longest_run_hours(mask, step_hours: float) -> float:
    """Найдовший безперервний інтервал, де mask = True (наприклад, найдовша ніч: mask = ~видно)."""
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        return 0.0
    padded = np.concatenate([[False], m, [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return float((edges[1::2] - edges[::2]).max() * step_hours)


def intervals(mask, times) -> list[tuple[float, float]]:
    """Інтервали [початок, кінець] (у одиницях times), де mask = True."""
    m = np.asarray(mask, dtype=bool)
    t = np.asarray(times, dtype=float)
    padded = np.concatenate([[False], m, [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(float(t[a]), float(t[b - 1])) for a, b in zip(edges[::2], edges[1::2], strict=True)]
