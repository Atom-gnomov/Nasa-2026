"""Звідки летіти до Місяця: найкращий космодром і найкраща довільна точка Землі (П-12; уточнення користувача).

Критерії:
    fuel  — економія пального: чекаємо вікна, коли майданчик потрапляє в площину з найменшим допустимим нахилом
            i = max(|φ|, |δ_Місяця|), і беремо найкращий за Δv прямий переліт 3–5 діб;
    speed — швидкість: старт одразу (без очікування) у площину через майданчик і Місяць, переліт 3 доби
            (найкоротший прямий); нахил і Δv при цьому більші.
Опції (scope):
    spaceports — космодроми й платформи з каталогу `launch_sites.json`;
    any        — довільна точка Землі: велике коло з нахилом |δ| через напрямок на Місяць; рекомендовано висхідний
                 вузол на екваторі в момент старту — найменше пального **і** без очікування.
Δv — перехід (transfer.py: TLI + гальмування біля Місяця) + недобір прибавки від обертання Землі для нахилу площини
(launch_optimum.rotation_penalty_m_s). Ракета тут не вибирається — це Δv і час для точки старту.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from app.core import launch_optimum as lo
from app.core import transfer
from app.core.ephemeris import get_ephemeris
from app.core.launch import best_inclination_deg
from app.services import catalogs

CRITERIA = ("fuel", "speed")
SCOPES = ("spaceports", "any")
FUEL_TOF_DAYS = np.arange(3.0, 5.0 + 1e-9, 0.5)
SPEED_TOF_DAYS = np.array([3.0])
SITE_KINDS = ("spaceport", "sea_platform")
FUEL_TIE_M_S = 5.0  # різниця Δv, меншу за яку не вважаємо перевагою (зшиті конічні перерізи — оцінка)


class LaunchOptimumError(ValueError):
    """Помилка запиту (400)."""


def _utc(when: datetime) -> datetime:
    return when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _best_transfer(eph, departure: datetime, tofs) -> transfer.TransferPoint:
    return min(transfer.dv_curve(eph, departure, tofs), key=lambda p: p.dv_total_m_s)


def _moon_dir_fn(eph, tof_days: float):
    def fn(departure: datetime) -> np.ndarray:
        r, _ = transfer.moon_state_icrf(eph, departure + timedelta(days=tof_days))
        return r / np.linalg.norm(r)

    return fn


def _option(site: dict, criterion: str, start: datetime, departure: datetime, point: transfer.TransferPoint,
            inclination: float, normal: np.ndarray, note: str) -> dict:
    penalty = lo.rotation_penalty_m_s(inclination)
    return {
        "site": {"id": site["id"], "name": site["name"], "kind": site.get("kind", "custom"),
                 "lat": float(site["lat"]), "lon": float(site["lon"])},
        "criterion": criterion,
        "departure_utc": _iso(departure),
        "arrival_utc": _iso(point.arrival_utc),
        "wait_h": round(lo.wait_hours(start, departure), 2),
        "tof_days": point.tof_days,
        "total_h": round(lo.wait_hours(start, point.arrival_utc), 2),
        "inclination_deg": round(inclination, 3),
        "dv_transfer_m_s": round(point.dv_total_m_s, 1),
        "dv_site_penalty_m_s": round(penalty, 1),
        "dv_total_m_s": round(point.dv_total_m_s + penalty, 1),
        "normal_icrf": [float(x) for x in normal],
        "note": note,
        "_point": point,
    }


def _any_point(eph, start: datetime, criterion: str) -> dict:
    tofs = FUEL_TOF_DAYS if criterion == "fuel" else SPEED_TOF_DAYS
    point = _best_transfer(eph, start, tofs)
    r_m, _ = transfer.moon_state_icrf(eph, point.arrival_utc)
    u = r_m / np.linalg.norm(r_m)
    delta = abs(lo.declination_deg(u))
    normal = lo.planes_through(u, delta)[0]
    lon = lo.ascending_node_lon(normal, start)
    site = {"id": "any-point", "name": "Довільна точка: вузол на екваторі", "kind": "custom", "lat": 0.0, "lon": lon}
    note = (f"Однаково найкращі за паливом усі точки великого кола з нахилом {delta:.1f}° через напрямок на Місяць "
            f"(траса на Землі); вузол на екваторі — старт без очікування (морська платформа)")
    return _option(site, criterion, start, start, point, delta, normal, note)


def _spaceport(eph, site: dict, start: datetime, criterion: str, ref: transfer.TransferPoint) -> dict | None:
    lat, lon = float(site["lat"]), float(site["lon"])
    if criterion == "speed":
        point = _best_transfer(eph, start, SPEED_TOF_DAYS)
        r_m, _ = transfer.moon_state_icrf(eph, point.arrival_utc)
        normal = lo.plane_through_site(lo.site_icrf(lat, lon, start), r_m)
        return _option(site, criterion, start, start, point, lo.inclination_deg(normal), normal,
                       "Старт одразу: площина через майданчик і Місяць, найкоротший прямий переліт")
    moon_dir = _moon_dir_fn(eph, ref.tof_days)
    inclination = best_inclination_deg(lat, abs(lo.declination_deg(moon_dir(start))))
    window = lo.earliest_window(lat, lon, moon_dir, start, inclination)
    if window is None:
        return None
    departure, normal = window
    inclination = lo.inclination_deg(normal)
    point = _best_transfer(eph, departure, FUEL_TOF_DAYS)
    return _option(site, criterion, start, departure, point, inclination, normal,
                   "Очікування вікна з найменшим нахилом площини, найкращий за Δv прямий переліт")


def plan(when: datetime, criterion: str = "fuel", scope: str = "spaceports") -> dict:
    """Найкращий старт для критерію й опції; для космодромів — також відсортовані альтернативи."""
    if criterion not in CRITERIA:
        raise LaunchOptimumError(f"criterion: допустимо {', '.join(CRITERIA)}")
    if scope not in SCOPES:
        raise LaunchOptimumError(f"scope: допустимо {', '.join(SCOPES)}")
    start = _utc(when).replace(microsecond=0)
    eph = get_ephemeris()
    if scope == "any":
        options = [_any_point(eph, start, criterion)]
    else:
        ref = _best_transfer(eph, start, FUEL_TOF_DAYS)
        sites = [s for s in catalogs.load_launch_sites() if s.get("kind") in SITE_KINDS]
        options = [o for o in (_spaceport(eph, s, start, criterion, ref) for s in sites) if o is not None]
        if not options:
            raise LaunchOptimumError("Немає майданчиків із вікном старту")
    if criterion == "fuel":
        # у межах FUEL_TIE_M_S варіанти рівні за паливом (точність моделі) — тоді кращий той, що раніше прибуває
        floor = min(o["dv_total_m_s"] for o in options)
        options.sort(key=lambda o: (o["dv_total_m_s"] > floor + FUEL_TIE_M_S,
                                    o["total_h"] if o["dv_total_m_s"] <= floor + FUEL_TIE_M_S else o["dv_total_m_s"]))
    else:
        options.sort(key=lambda o: (o["total_h"], o["dv_total_m_s"]))
    best = options[0]
    return {
        "criterion": criterion,
        "scope": scope,
        "start_utc": _iso(start),
        "best": best,
        "alternatives": options[1:],
    }


def public(option: dict) -> dict:
    """Варіант без службових полів (для JSON)."""
    return {k: v for k, v in option.items() if not k.startswith("_")}
