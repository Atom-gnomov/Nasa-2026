"""Ранжування точок і порівняння (контракт RankRequest / RankResponse; docs/MATH.md, §19).

Підсумки точки за період беруться з сервісу /timeline (Сонце, Земля, DSN, маска горизонту з LOLA),
частка відкритого неба — з /horizon, температура — з Diviner (лише якщо запитано фактор temperature).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.core import mission_profile, site_score
from app.core.site_score import Requirements, ScoreParams
from app.services import catalogs, sites, temperature, timeline

MAX_POINTS = 30
SUPPORTED = site_score.FACTORS
DEFAULT_PRIORITIES = ("energy", "comms")


class RankError(ValueError):
    """Помилка запиту (400)."""


class SiteNotFound(RankError):
    """Невідомий site_id (404)."""


def _resolve_points(raw: list[dict]) -> list[dict]:
    if not 2 <= len(raw) <= MAX_POINTS:
        raise RankError(f"Потрібно від 2 до {MAX_POINTS} точок")
    out = []
    for item in raw:
        if item.get("site_id"):
            site = sites.get_site(item["site_id"])
            if site is None:
                raise SiteNotFound(f"Місце {item['site_id']} не знайдено")
            out.append({"site_id": site.id, "name": item.get("name") or site.name, "lat": site.lat, "lon": site.lon})
        elif "lat" in item and "lon" in item:
            lat, lon = float(item["lat"]), float(item["lon"])
            if not -90 <= lat <= 90 or not -180 <= lon <= 360:
                raise RankError("lat має бути в [-90, 90], lon — в [-180, 360]")
            out.append({"site_id": None, "name": item.get("name"), "lat": lat, "lon": lon})
        else:
            raise RankError("Точка має містити site_id або lat і lon")
    return out


def thermal_fraction(lat: float, lon: float, when: datetime, params: ScoreParams) -> float:
    """Частка місячної доби, коли температура поверхні в [temp_min_k, temp_max_k] (за добовою кривою Diviner)."""
    curve = temperature.temperature_point(lat, lon, when)["diurnal"]
    values = np.array([c["tbol_k"] for c in curve if c["tbol_k"] is not None], dtype=float)
    if values.size == 0:
        raise RankError("У цій точці немає вимірювань температури Diviner")
    return float(np.mean((values >= params.temp_min_k) & (values <= params.temp_max_k)))


def evaluate_point(p: dict, start: datetime, end: datetime, step_h: float, height_m: float,
                   need_thermal: bool, params: ScoreParams) -> tuple[dict, str, dict[str, float]]:
    """Підсумки точки за період (як /timeline) + частка відкритого неба (+ температура), джерело горизонту
    й години доступності кожної станції DSN: {station_id: години}."""
    tl = timeline.timeline(p["lat"], p["lon"], start, end, step_h, height_m)
    summary = dict(tl["summary"])
    summary["sky_view_fraction"] = timeline.horizon_mask(p["lat"], p["lon"], height_m)["sky_view_fraction"]
    summary["thermal_fraction"] = thermal_fraction(p["lat"], p["lon"], start, params) if need_thermal else None
    station_hours = {st["station_id"]: round(sum(st["available"]) * tl["step_h"], 2) for st in tl["stations"]}
    return summary, tl["horizon_source"], station_hours


def _resolve_profile(request: dict, start: datetime, end: datetime) -> mission_profile.ResolvedProfile | None:
    """Профіль місії (M17) для запиту; без `mission_profile` — None й поведінка `/rank` не змінюється."""
    name = request.get("mission_profile")
    if name is None:
        if request.get("crew") is not None:
            raise RankError("crew задається лише разом із mission_profile")
        return None
    try:
        return mission_profile.resolve(name, catalogs.load_mission_thresholds(), crew=request.get("crew"),
                                       priorities=request.get("priorities") or None)
    except ValueError as exc:
        raise RankError(str(exc)) from exc


def rank(request: dict, start: datetime, end: datetime) -> dict:
    """request — перевірене тіло запиту; start/end — розібрані моменти. Повертає відповідь RankResponse."""
    profile = _resolve_profile(request, start, end)
    priorities = list(request.get("priorities") or (profile.priorities if profile else DEFAULT_PRIORITIES))
    bad = [f for f in priorities if f not in SUPPORTED]
    if bad:
        raise RankError(f"Фактор ще не підтримується: {', '.join(bad)}")
    mode = request.get("mode", "weighted")
    try:
        params = ScoreParams(**(request.get("params") or {}))
    except TypeError as exc:
        raise RankError(f"Невідомий параметр шкали: {exc}") from exc
    explicit = request.get("requirements") or {}
    try:
        req = Requirements(**explicit)
    except TypeError as exc:
        raise RankError(f"Невідома вимога: {exc}") from exc
    if profile is not None:
        period_h = (end - start).total_seconds() / 3600.0
        from_profile = profile.requirements(period_h)
        # Явні значення запиту переважають профіль поле за полем
        req = Requirements(
            min_sun_hours=req.min_sun_hours if "min_sun_hours" in explicit else from_profile.min_sun_hours,
            min_comm_hours=req.min_comm_hours if "min_comm_hours" in explicit else from_profile.min_comm_hours)
    step_h = float(request.get("step_h", 1.0))
    height_m = float(request.get("height_m", 0.0))
    points = _resolve_points(request["points"])

    summaries, sources = [], []
    for p in points:
        summary, source, _ = evaluate_point(p, start, end, step_h, height_m, "temperature" in priorities, params)
        summaries.append(summary)
        sources.append(source)

    try:
        scored = site_score.score_points(summaries, priorities, mode, req, params)
    except ValueError as exc:
        raise RankError(str(exc)) from exc
    weights = site_score.priority_weights(priorities)

    ranking = []
    for sp in scored:
        p = points[sp.index]
        s = sp.summary
        ranking.append({
            "rank": sp.rank,
            "point": {"site_id": p["site_id"], "name": p["name"], "lat": p["lat"],
                      "lon": (p["lon"] + 180.0) % 360.0 - 180.0},
            "feasible": sp.feasible,
            "violations": sp.violations,
            "score_pct": sp.score_pct,
            "pareto": sp.pareto,
            "factors": {f: round(v, 4) for f, v in sp.factors.items()},
            "summary": {k: s[k] for k in ("sun_hours", "comm_hours", "sun_fraction", "comm_fraction",
                                          "longest_night_h", "longest_comm_gap_h", "energy_wh_per_m2",
                                          "sky_view_fraction", "thermal_fraction") if s.get(k) is not None},
            "horizon_source": sources[sp.index],
        })
    return {
        "period": {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "period_h": round((end - start).total_seconds() / 3600.0, 3), "step_h": step_h},
        "mode": mode,
        "priorities": priorities,
        "weights": {f: round(w, 4) for f, w in weights.items()},
        "params": params.to_dict(),
        "ranking": ranking,
        "comparison": site_score.compare(scored[0], scored[1], weights),
        "profile": profile.to_dict() if profile else None,
    }
