"""Вікно запуску: оцінка у % для кожної дати старту (контракт LaunchWindow; задача B8; VISION «Вікно запуску»).

Для кожної дати періоду (старт TLI о 00:00 UTC) рахуємо:
    fuel    — сумарний Δv: найкращий прямий перехід за 3–5 діб (transfer.py, M10) + добавка майданчика (втрата прибавки
              від обертання Землі й доворот площини, launch.py, M19); оцінка — мін-макс серед дат періоду;
    light   — частка часу, коли в точці посадки видно Сонце (будь-яку частину диска над маскою рельєфу) протягом
              `LANDED_DAYS` діб після прибуття: енергія й тепло на початку роботи (MATH §13 «Стартове вікно»);
    comms   — те саме для Землі (прямий зв'язок);
    windows — вікна запуску на добу з майданчика, W/2.
Оцінка дати — ваги ROC за порядком пріоритетів (MATH §14, §19). Економна траєкторія — оцінка: прибуття через середню
тривалість (launch.TRAJECTORIES), Δv — найкращий прямий мінус економія (transfer.LOW_ENERGY_DV_SAVING_M_S).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone

import numpy as np

from app.core import scoring, transfer
from app.core.ephemeris import get_ephemeris
from app.core.launch import TRAJECTORIES, best_inclination_deg, site_departure
from app.services import catalogs, horizon, visibility

FACTORS = ("light", "fuel", "comms", "windows")
MAX_DAYS = 60
LANDED_DAYS = 7.0  # скільки діб після прибуття оцінюємо світло й зв'язок
SAMPLE_STEP_H = 2.0
DIRECT_TOF_DAYS = np.arange(3.0, 5.0 + 1e-9, 0.5)


class LaunchWindowError(ValueError):
    """Помилка запиту (400)."""


class LaunchSiteNotFound(LaunchWindowError):
    """Невідомий майданчик (404)."""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_priorities(value: str | None) -> list[str]:
    if not value:
        return list(FACTORS)
    items = [v.strip() for v in value.split(",") if v.strip()]
    bad = [v for v in items if v not in FACTORS]
    if not items or bad or len(set(items)) != len(items):
        raise LaunchWindowError(f"priorities — унікальні фактори через кому з: {', '.join(FACTORS)}")
    return items


def _dates(start: datetime, end: datetime) -> list[date]:
    d0, d1 = start.astimezone(timezone.utc).date(), end.astimezone(timezone.utc).date()
    if d1 < d0:
        raise LaunchWindowError("Кінець періоду має бути не раніше за початок")
    n = (d1 - d0).days + 1
    if n > MAX_DAYS:
        raise LaunchWindowError(f"Період довший за {MAX_DAYS} діб")
    return [d0 + timedelta(days=i) for i in range(n)]


def _landed_fractions(eph, mask, lat: float, lon: float, arrival: datetime) -> tuple[float, float, bool]:
    """Частки часу видимості Сонця й Землі за LANDED_DAYS після прибуття і чи освітлено в момент прибуття."""
    hours = np.arange(0.0, LANDED_DAYS * 24 + 1e-9, SAMPLE_STEP_H)
    t = eph.time_grid(arrival, hours)
    _, _, sun_f, earth_f = visibility.sun_earth_visibility(eph, t, mask, lat, lon)
    sun_f, earth_f = np.atleast_1d(sun_f), np.atleast_1d(earth_f)
    return float(np.mean(sun_f > 0)), float(np.mean(earth_f > 0)), bool(sun_f[0] > 0)


def day_metrics(eph, mask, site_lat: float, lat: float, lon: float, day: date, trajectory: str) -> dict:
    """Показники однієї дати старту (без оцінок)."""
    departure = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    curve = transfer.dv_curve(eph, departure, DIRECT_TOF_DAYS)
    best = min(curve, key=lambda p: p.dv_total_m_s)
    dep = site_departure(site_lat, best_inclination_deg(site_lat, best.min_parking_inclination_deg))
    if trajectory == "direct":
        arrival, dv_total = best.arrival_utc, best.dv_total_m_s
        duration = best.tof_days
    else:
        lo, hi = TRAJECTORIES["low_energy"]["duration_days"]
        duration = (lo + hi) / 2
        arrival = departure + timedelta(days=duration)
        dv_total = best.dv_total_m_s - sum(transfer.LOW_ENERGY_DV_SAVING_M_S) / 2
    sun_frac, earth_frac, sunlit = _landed_fractions(eph, mask, lat, lon, arrival)
    return {
        "date": day.isoformat(),
        "arrival": _iso(arrival),
        "flight_days": float(duration),
        "dv_total_m_s": float(dv_total + dep.dv_penalty_m_s),
        "windows_per_day": dep.windows_per_day,
        "inclination_deg": float(dep.target_inclination_deg),
        "sun_fraction": sun_frac,
        "earth_fraction": earth_frac,
        "sunlit_at_arrival": sunlit,
    }


def score_days(days: list[dict], priorities: Sequence[str]) -> list[dict]:
    """Оцінки факторів 0…1 і бал 0…100 для кожної дати (чиста функція над результатами day_metrics)."""
    if not days:
        return days
    fuel = scoring.normalize([d["dv_total_m_s"] for d in days], higher_is_better=False)
    weights = scoring.roc_weights(len(priorities))
    for d, f in zip(days, fuel, strict=True):
        factors = {"fuel": float(f), "light": d["sun_fraction"], "comms": d["earth_fraction"],
                   "windows": d["windows_per_day"] / 2.0}
        d["factors"] = {k: round(factors[k], 4) for k in priorities}
        d["score_pct"] = round(float(100.0 * np.dot([factors[k] for k in priorities], weights)), 2)
    return days


def launch_window(launch_site_id: str, lat: float, lon: float, start: datetime, end: datetime,
                  trajectory: str = "direct", priorities: Sequence[str] = FACTORS) -> dict:
    if trajectory not in TRAJECTORIES:
        raise LaunchWindowError(f"trajectory: допустимо {', '.join(TRAJECTORIES)}")
    site = next((s for s in catalogs.load_launch_sites() if s["id"] == launch_site_id), None)
    if site is None:
        raise LaunchSiteNotFound(f"Місце старту {launch_site_id} не знайдено")
    dates = _dates(start, end)
    eph = get_ephemeris()
    mask = horizon.load_mask(lat, lon)
    days = score_days([day_metrics(eph, mask, float(site["lat"]), lat, lon, d, trajectory) for d in dates],
                      priorities)
    best = max(days, key=lambda d: (d["score_pct"], -dates.index(date.fromisoformat(d["date"]))))
    return {
        "launch_site_id": launch_site_id,
        "trajectory": trajectory,
        "moon_point": {"lat": lat, "lon": lon},
        "priorities": list(priorities),
        "method": "patched_conic" if trajectory == "direct" else "estimate",
        "horizon_source": horizon.mask_source(lat, lon),
        "landed_days": LANDED_DAYS,
        "days": days,
        "best": {"date": best["date"], "score_pct": best["score_pct"]},
    }
