"""Оцінка й оптимізація (docs/MATH.md, §14). Друга черга."""

from __future__ import annotations

import numpy as np


def normalize(values, higher_is_better: bool = True) -> np.ndarray:
    """Мін-макс нормалізація до [0, 1]; якщо всі значення однакові — 1."""
    v = np.asarray(values, dtype=float)
    lo, hi = np.nanmin(v), np.nanmax(v)
    if hi == lo:
        return np.ones_like(v)
    s = (v - lo) / (hi - lo)
    return s if higher_is_better else 1.0 - s


def roc_weights(n: int) -> np.ndarray:
    """Ваги Rank Order Centroid для n факторів, упорядкованих за важливістю (перший — найважливіший)."""
    if n <= 0:
        return np.array([])
    inv = 1.0 / np.arange(1, n + 1)
    return np.array([inv[i:].sum() for i in range(n)]) / n


def weighted_score(scores, weights) -> np.ndarray:
    """scores: (варіанти, фактори) у [0, 1] → бал 0…100."""
    return 100.0 * np.asarray(scores, dtype=float) @ np.asarray(weights, dtype=float)


def maximin_score(scores) -> np.ndarray:
    """Режим «потрібно все»: бал = найгірший фактор, 0…100."""
    return 100.0 * np.asarray(scores, dtype=float).min(axis=1)


def pareto_front(scores) -> np.ndarray:
    """Індекси недомінованих варіантів (усі фактори — «більше краще»)."""
    s = np.asarray(scores, dtype=float)
    keep = []
    for i, row in enumerate(s):
        dominated = np.any(np.all(s >= row, axis=1) & np.any(s > row, axis=1))
        if not dominated:
            keep.append(i)
    return np.array(keep, dtype=int)
