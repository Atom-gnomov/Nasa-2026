"""Повний план місії одним викликом (контракт PlanRequest / PlanResponse; docs/TASKS.md, B18).

Оркеструє наявні сервіси: `/search` (місця посадки за вимогами) → `/mission` (маса корисного навантаження)
→ `/launch-ranking` (майданчик, ракета й траєкторія для кожного місця) → `/mission` для лідера (повна місія).

Автовибір: оптимум серед варіантів, де місце виконує всі жорсткі вимоги (M23). Якщо таких немає — варіанти
з найменшою кількістю порушень, із поясненням. Невідомі (`unchecked`) вимоги й м'які попередження лише
позначаються. Сітку кандидатів і бюджет часу задає `/search` (до 200 точок, 25 с).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from app.core.launch import TRAJECTORIES
from app.services import launch_ranking, launch_window, mission, search

SEARCH_KEYS = {"region", "include_catalog", "grid_step_deg", "max_candidates", "step_h", "height_m", "priorities",
               "mode", "params", "min_sun_hours", "min_comm_hours", "max_slope_deg", "min_earth_fraction",
               "min_sun_fraction", "mission_profile", "crew", "earth_target"}
PLAN_KEYS = {"start", "end", "departure", "days", "sizes", "vehicle", "trajectories", "launch_priorities",
             "launch_mode", "include_design_targets", "allow_multiple_launches", "landing_candidates", "limit",
             "departure_days", "surface_after_arrival"}
ALLOWED = SEARCH_KEYS | PLAN_KEYS
MAX_LANDING_CANDIDATES = 10
SEARCH_LIMIT = 100  # скільки місць повертає /search; з них вибираємо найкращі за вимогами


class PlanError(ValueError):
    """Помилка запиту (400)."""


def _int(body: Mapping, key: str, default: int, low: int, high: int) -> int:
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise PlanError(f"{key} має бути цілим від {low} до {high}")
    return value


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _landing_order(chain: dict) -> tuple:
    """Допустимі місця — першими (за рангом /search), далі — з найменшою кількістю порушень."""
    return (not chain["feasible"], len(chain["violations"]), chain["rank"])


def _landing(chain: dict) -> dict:
    keys = ("rank", "moon_site", "dsn_station_id", "dsn_hours", "score_pct", "pareto", "factors", "summary",
            "horizon_source")
    return {k: chain[k] for k in keys}


def _launch_body(chain: dict, departure: datetime, mass_kg: float, body: Mapping) -> dict:
    site = chain["moon_site"]
    out = {"lat": site["lat"], "lon": site["lon"], "datetime": _iso(departure), "mass_moon_kg": mass_kg,
           "limit": 1}
    for src, dst in (("vehicle", "vehicle"), ("trajectories", "trajectories"), ("launch_priorities", "priorities"),
                     ("launch_mode", "mode"), ("include_design_targets", "include_design_targets"),
                     ("allow_multiple_launches", "allow_multiple_launches")):
        if src in body:
            out[dst] = body[src]
    return out


def _best_departure(option: dict, chain: dict, departure: datetime, days: int) -> tuple[datetime, dict]:
    """Найкраща дата старту (B8) з `days` діб від `departure` для знайденого майданчика й траєкторії."""
    site = chain["moon_site"]
    day0 = departure.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    win = launch_window.launch_window(option["site"]["id"], site["lat"], site["lon"], day0,
                                      day0 + timedelta(days=days - 1), option["trajectory"])
    best = datetime.fromisoformat(win["best"]["date"]).replace(tzinfo=timezone.utc)
    scale = [{"date": d["date"], "score_pct": d["score_pct"], "arrival": d.get("arrival")} for d in win["days"]]
    return best, {"days": scale, "best": win["best"], "method": win["method"]}


def _assumed_flight_days(body: Mapping) -> float:
    """Типовий переліт, діб, для оцінки дати посадки до вибору ракети: перша з запитаних траєкторій (інакше пряма)."""
    names = body.get("trajectories") or ["direct"]
    if not isinstance(names, list) or not names or names[0] not in TRAJECTORIES:
        raise PlanError(f"trajectories: допустимо {', '.join(TRAJECTORIES)}")
    lo, hi = TRAJECTORIES[names[0]]["duration_days"]
    return (lo + hi) / 2.0


def _mission_body(body: Mapping, night_h: float | None) -> dict:
    out = {k: body[k] for k in ("crew", "days", "sizes", "mission_profile") if body.get(k) is not None}
    if night_h:
        out["longest_night_h"] = night_h
    return out


def _route(chain: dict, option: dict, transfer: dict) -> dict:
    site = chain["moon_site"]
    return {
        "launch_site": option["site"],
        "moon_site": {"site_id": site["site_id"], "name": site["name"], "lat": site["lat"], "lon": site["lon"]},
        "trajectory": option["trajectory"],
        "departure_utc": None,
        "arrival_utc": transfer["arrival_utc"],
        "duration_days": transfer["duration_days"],
        "dv_total_m_s": option["dv_total_m_s"],
    }


def _explain(plans: list[dict], hard_ok: bool) -> str:
    if not plans:
        return "Не знайдено жодного місця посадки в заданій області."
    lead = plans[0]
    site = lead["landing"]["moon_site"]
    where = site["name"] or f"{site['lat']:.2f}°, {site['lon']:.2f}°"
    req = lead["requirements"]
    if hard_ok:
        text = f"Обрано {where}: виконано всі жорсткі вимоги до місця посадки"
    else:
        text = (f"Жодне місце не виконує всіх жорстких вимог; обрано {where} із найменшою кількістю порушень "
                f"({len(req['violations'])})")
    if req["warnings"]:
        text += f"; м'які вимоги з попередженнями: {len(req['warnings'])}"
    if req["unchecked"]:
        text += f"; не перевірено (немає даних): {', '.join(req['unchecked'])}"
    launch = lead["launch"]
    if launch is None:
        return text + ". Для нього немає варіанта запуску, що вміщує масу."
    text += f". Старт: {launch['site']['name']}, ракета {launch['vehicle']['name']}, траєкторія {launch['trajectory']}"
    if not launch["fits"]:
        text += " (маса не вміщується в одну ракету)"
    return text + "."


def compute(body: Mapping, start: datetime, end: datetime) -> dict:
    """Повний план за тілом запиту й розібраним періодом; `ValueError` — помилка вхідних даних, `RuntimeError` —
    немає даних (ефемерид)."""
    if not isinstance(body, Mapping):
        raise PlanError("Тіло запиту має бути об'єктом")
    unknown = set(body) - ALLOWED
    if unknown:
        raise PlanError(f"Невідомі поля: {', '.join(sorted(unknown))}")
    n_landing = _int(body, "landing_candidates", 3, 1, MAX_LANDING_CANDIDATES)
    limit = _int(body, "limit", 5, 1, 20)
    departure_days = _int(body, "departure_days", 1, 1, launch_window.MAX_DAYS)
    departure = start
    if body.get("departure") is not None:
        try:
            departure = datetime.fromisoformat(str(body["departure"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise PlanError("departure: очікується ISO 8601") from exc
        if departure.tzinfo is None:
            departure = departure.replace(tzinfo=timezone.utc)

    # B20b: період, у який оцінюємо місце, — після прибуття (старт + типовий переліт), а не від дати старту
    after_arrival = body.get("surface_after_arrival", True)
    if not isinstance(after_arrival, bool):
        raise PlanError("surface_after_arrival має бути true або false")
    flight_days = _assumed_flight_days(body) if after_arrival else 0.0
    surface_start = departure + timedelta(days=flight_days) if after_arrival else start
    surface_end = surface_start + (end - start)
    # crew без профілю стосується лише маси корисного навантаження; /search приймає його тільки з профілем
    search_body = {k: body[k] for k in SEARCH_KEYS if k in body and (k != "crew" or "mission_profile" in body)}
    found = search.search({**search_body, "limit": SEARCH_LIMIT}, surface_start, surface_end)
    chains = sorted(found["chains"], key=_landing_order)
    hard_ok = bool(chains) and chains[0]["feasible"]
    selected = chains[:n_landing]

    plans = []
    for chain in selected:
        night = chain["summary"].get("longest_night_h")
        payload = mission.compute(_mission_body(body, night))["payload"]
        mass = float(payload["total_kg"])
        ranked = launch_ranking.compute(_launch_body(chain, departure, mass, body))
        option = ranked["options"][0] if ranked["options"] else None
        window = None
        when = departure
        if option and departure_days > 1:  # B20: перебір дат старту; потім рейтинг запусків уже на найкращу дату
            when, window = _best_departure(option, chain, departure, departure_days)
            on_date = {**_launch_body(chain, when, mass, body), "vehicle": option["vehicle"]["id"]}
            ranked = launch_ranking.compute(on_date)
            option = ranked["options"][0] if ranked["options"] else None
        launch_score = option["score_pct"] if option else 0.0
        plan = {
            "landing": _landing(chain),
            "requirements": {"feasible": chain["feasible"], "violations": chain["violations"],
                             "warnings": chain["warnings"], "unchecked": chain["unchecked"]},
            "mass_moon_kg": mass,
            "launch": option,
            "launch_explanation": ranked["leader_explanation"],
            "departure_window": window,
            "route": None,
            "mission": None,
            "score_pct": round(chain["score_pct"] * launch_score / 100.0, 2),
        }
        if option:
            plan["route"] = {**_route(chain, option, ranked["transfers"][option["trajectory"]]),
                             "departure_utc": ranked["departure_utc"]}
        plans.append(plan)

    plans.sort(key=lambda p: (not p["requirements"]["feasible"], len(p["requirements"]["violations"]),
                              p["launch"] is None, not (p["launch"] or {}).get("fits", False), -p["score_pct"]))
    for i, p in enumerate(plans, start=1):
        p["rank"] = i

    notes = []
    if after_arrival:
        for p in plans:
            if p["route"]:
                actual = datetime.fromisoformat(p["route"]["arrival_utc"][0].replace("Z", "+00:00"))
                if abs((actual - surface_start).total_seconds()) > 86400.0 * 1.5:
                    notes.append(f"План {p['rank']}: прибуття {p['route']['arrival_utc'][0][:10]} відрізняється від "
                                 f"припущеного ({surface_start.date()}) більш ніж на 1,5 доби — світло й зв'язок "
                                 "оцінено для припущеної дати.")
    if plans and plans[0]["launch"]:
        lead = plans[0]
        try:
            lead["mission"] = mission.compute({
                **_mission_body(body, lead["landing"]["summary"].get("longest_night_h")),
                "trajectory": lead["launch"]["trajectory"], "launch_site_id": lead["launch"]["site"]["id"],
                "launch_system_id": lead["launch"]["vehicle"]["id"]})
        except ValueError as exc:  # напр., ракета з каталогу D6 без запису в сервісі місії
            notes.append(f"Повну місію для лідера не пораховано: {exc}")
    return {
        "provisional": True,
        "period": found["period"],
        "surface_period": {"start": _iso(surface_start), "end": _iso(surface_end), "assumed_flight_days": flight_days,
                           "after_arrival": after_arrival},
        "departure_utc": _iso(departure),
        "grid": found["grid"],
        "landing_evaluated": len(found["chains"]),
        "hard_requirements_met": hard_ok,
        "auto_selected": plans[0]["rank"] if plans else None,
        "plans": plans[:limit],
        "explanation": _explain(plans, hard_ok),
        "notes": notes,
    }
