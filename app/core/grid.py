"""Сітка кандидатів на сфері для підбору точок (docs/MATH.md, §19.9).

Рядки — за широтою з кроком `step_deg`; у кожному рядку довготи рівномірні, їх кількість пропорційна cos(широти),
тож густина точок на поверхні приблизно однакова, а на самому полюсі — одна точка (довгота 0).
Чисті функції без залежностей від Flask.
"""

from __future__ import annotations

import math

MAX_CANDIDATES_LIMIT = 400


def _rows(lat_min: float, lat_max: float, step_deg: float) -> list[float]:
    """Широти рядків від lat_min до lat_max включно (останній рядок додається, якщо крок не ділить діапазон)."""
    rows, k = [], 0
    while True:
        lat = lat_min + k * step_deg
        if lat >= lat_max - 1e-9:
            break
        rows.append(lat)
        k += 1
    rows.append(lat_max)
    return rows


def _lons(lat: float, lon_min: float, lon_max: float, step_deg: float) -> list[float]:
    if abs(lat) >= 90 - 1e-9:
        return [0.0]  # полюс: довгота не визначена
    span = lon_max - lon_min
    n = max(1, round(span * math.cos(math.radians(lat)) / step_deg))
    return [lon_min + (i + 0.5) * span / n for i in range(n)]


def candidate_grid(lat_min: float, lat_max: float, lon_min: float, lon_max: float, step_deg: float,
                   max_candidates: int = MAX_CANDIDATES_LIMIT) -> list[tuple[float, float]]:
    """Точки (широта, довгота) у регіоні. Більше за max_candidates — ValueError з порадою."""
    if not (-90 <= lat_min <= lat_max <= 90):
        raise ValueError("Має бути −90 ≤ lat_min ≤ lat_max ≤ 90")
    if not (-180 <= lon_min < lon_max <= 180):
        raise ValueError("Має бути −180 ≤ lon_min < lon_max ≤ 180")
    if step_deg <= 0:
        raise ValueError("Крок сітки має бути додатним")
    points = [(lat, lon) for lat in _rows(lat_min, lat_max, step_deg)
              for lon in _lons(lat, lon_min, lon_max, step_deg)]
    # унікальність (рядки на межах не дублюються, але перестрахуємося від збігу після округлення)
    points = list(dict.fromkeys((round(la, 6), round(lo, 6)) for la, lo in points))
    if len(points) > max_candidates:
        raise ValueError(f"Сітка має {len(points)} кандидатів, а дозволено {max_candidates}: "
                         "збільште grid_step_deg або зменште region")
    return points
