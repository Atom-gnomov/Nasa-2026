"""Підбір найкращих точок у регіоні (контракт SearchRequest / SearchResponse; docs/MATH.md, §19).

Кандидати — сітка в регіоні (app.core.grid); кожен оцінюється як у /rank (app.services.ranking.evaluate_point
+ app.core.site_score). Пошук обмежений бюджетом часу: якщо його вичерпано, повертаються оцінені кандидати
й grid.truncated = true. Передрозрахунок сітки (M9) пришвидшить це, але для MVP не потрібен.
"""

from __future__ import annotations

import time
from datetime import datetime

from app.core import grid, site_score
from app.core.site_score import Requirements, ScoreParams
from app.services import ranking, sites
from app.services.ranking import RankError

BUDGET_S = 25.0  # скільки секунд сервер оцінює кандидатів (до першої відповіді користувачу)
MIN_EVALUATED = 2  # скільки кандидатів оцінюємо незалежно від бюджету, щоб було що порівнювати
DEFAULT_REGION = {"lat_min": -90.0, "lat_max": -80.0, "lon_min": -180.0, "lon_max": 180.0}
NOT_SUPPORTED = ("launch_site_ids", "trajectory")


def _num(body: dict, key: str, default: float, lo: float, hi: float) -> float:
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RankError(f"Поле {key} має бути числом")
    if not lo <= value <= hi:
        raise RankError(f"Поле {key} має бути в межах [{lo:g}, {hi:g}]")
    return float(value)


def _candidates(body: dict, step_deg: float, max_candidates: int) -> list[dict]:
    region = {**DEFAULT_REGION, **(body.get("region") or {})}
    unknown = set(region) - set(DEFAULT_REGION)
    if unknown:
        raise RankError(f"Невідомі поля region: {', '.join(sorted(unknown))}")
    try:
        points = grid.candidate_grid(float(region["lat_min"]), float(region["lat_max"]), float(region["lon_min"]),
                                     float(region["lon_max"]), step_deg, max_candidates)
    except (TypeError, ValueError) as exc:
        raise RankError(str(exc)) from exc
    out = [{"site_id": None, "name": None, "lat": lat, "lon": lon} for lat, lon in points]
    if body.get("include_catalog"):
        catalog = [{"site_id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon} for s in sites.load_sites()]
        taken = {(round(c["lat"], 4), round(c["lon"], 4)) for c in catalog}
        out = [c for c in out if (round(c["lat"], 4), round(c["lon"], 4)) not in taken] + catalog
        if len(out) > max_candidates:
            raise RankError(f"Разом із каталогом {len(out)} кандидатів, а дозволено {max_candidates}")
    return out


def _now() -> float:
    """Годинник бюджету часу (окремою функцією, щоб тест міг його підмінити)."""
    return time.monotonic()


def search(body: dict, start: datetime, end: datetime) -> dict:
    for key in NOT_SUPPORTED:
        if body.get(key):
            raise RankError(f"{key} ще не підтримується: потрібна модель запусків (задача M10)")
    priorities = list(body.get("priorities") or ranking.DEFAULT_PRIORITIES)
    bad = [f for f in priorities if f not in ranking.SUPPORTED]
    if bad:
        raise RankError(f"Фактор ще не підтримується: {', '.join(bad)}")
    mode = body.get("mode", "weighted")
    try:
        params = ScoreParams(**(body.get("params") or {}))
    except TypeError as exc:
        raise RankError(f"Невідомий параметр шкали: {exc}") from exc
    requirements = Requirements(*(None if body.get(k) is None else _num(body, k, 0, 0, 1e6)
                                  for k in ("min_sun_hours", "min_comm_hours")))
    step_h = _num(body, "step_h", 6.0, 1.0, 24.0)
    height_m = _num(body, "height_m", 0.0, 0.0, 1000.0)
    step_deg = _num(body, "grid_step_deg", 2.0, 0.25, 30.0)
    max_candidates = int(_num(body, "max_candidates", 200, 1, grid.MAX_CANDIDATES_LIMIT))
    limit = int(_num(body, "limit", 20, 1, 100))
    candidates = _candidates(body, step_deg, max_candidates)

    started = _now()
    summaries, sources, stations, evaluated = [], [], [], []
    need_thermal = "temperature" in priorities
    for cand in candidates:
        if len(evaluated) >= MIN_EVALUATED and _now() - started > BUDGET_S:
            break
        summary, source, station_hours = ranking.evaluate_point(
            cand, start, end, step_h, height_m, need_thermal, params)
        evaluated.append(cand)
        summaries.append(summary)
        sources.append(source)
        stations.append(station_hours)

    try:
        scored = site_score.score_points(summaries, priorities, mode, requirements, params)
    except ValueError as exc:
        raise RankError(str(exc)) from exc
    weights = site_score.priority_weights(priorities)
    earth_target = body.get("earth_target")

    chains = []
    for sp in scored[:limit]:
        cand = evaluated[sp.index]
        hours = stations[sp.index]
        best = max(hours, key=hours.get) if hours and max(hours.values()) > 0 else None
        s = sp.summary
        chains.append({
            "rank": sp.rank,
            "moon_site": {"site_id": cand["site_id"], "name": cand["name"], "lat": cand["lat"],
                          "lon": (cand["lon"] + 180.0) % 360.0 - 180.0},
            "dsn_station_id": best,
            "dsn_hours": hours[best] if best else 0.0,
            "launch_site_id": None,
            "earth_target": earth_target,
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
        "grid": {"step_deg": step_deg, "candidates": len(candidates), "evaluated": len(evaluated),
                 "truncated": len(evaluated) < len(candidates), "budget_s": BUDGET_S},
        "chains": chains,
        "comparison": site_score.compare(scored[0], scored[1], weights) if len(scored) >= 2 else None,
    }
