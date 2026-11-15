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

from app.core import launch as launch_core
from app.core.launch import TRAJECTORIES
from app.services import launch_ranking, mission, search, transfer_cache

SEARCH_KEYS = {"region", "include_catalog", "grid_step_deg", "max_candidates", "step_h", "height_m", "priorities",
               "mode", "params", "min_sun_hours", "min_comm_hours", "max_slope_deg", "min_earth_fraction",
               "min_sun_fraction", "mission_profile", "crew", "earth_target"}
PLAN_KEYS = {"start", "end", "departure", "days", "sizes", "vehicle", "trajectories", "launch_priorities",
             "launch_mode", "include_design_targets", "allow_multiple_launches", "landing_candidates", "limit",
             "surface_after_arrival", "anchor", "launch_site_id", "landing_point", "crew_members",
             "supply_days",
             "reserve_fraction"}
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
                     ("allow_multiple_launches", "allow_multiple_launches"), ("launch_site_id", "site_id")):
        if src in body:
            out[dst] = body[src]
    return out


def _assumed_flight_days(body: Mapping) -> float:
    """Типовий переліт, діб, для оцінки дати посадки до вибору ракети: перша з запитаних траєкторій (інакше пряма)."""
    names = body.get("trajectories") or ["direct"]
    if not isinstance(names, list) or not names or names[0] not in TRAJECTORIES:
        raise PlanError(f"trajectories: допустимо {', '.join(TRAJECTORIES)}")
    lo, hi = TRAJECTORIES[names[0]]["duration_days"]
    return (lo + hi) / 2.0


DIRECT_TOF_GRID = (3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0)
ANCHORS = ("landing", "departure")


def _departure_for_landing(landing: datetime, body: Mapping) -> tuple[datetime, float]:
    """Календар — дата посадки, умови Місяця головні, старт підлаштовується: дата старту = посадка − час перельоту.
    Прямий: час перельоту з найменшим Δv серед тих, що прибувають рівно в день посадки; економний — типові ≈ 105 діб."""
    names = body.get("trajectories") or ["direct"]
    if not isinstance(names, list) or not names or names[0] not in TRAJECTORIES:
        raise PlanError(f"trajectories: допустимо {', '.join(TRAJECTORIES)}")
    if names[0] == "low_energy":
        tof = _assumed_flight_days(body)
        return landing - timedelta(days=tof), tof
    best = transfer_cache.best_arrival_anchored(landing, DIRECT_TOF_GRID)
    return best.departure_utc, float(best.tof_days)


def _landing_point(body: Mapping) -> list[dict] | None:
    """Вибрана на кроці 5 точка посадки (landing_point) — єдиний кандидат: повторного пошуку по області немає."""
    raw = body.get("landing_point")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise PlanError("landing_point має бути об'єктом {lat, lon}")
    lat, lon = raw.get("lat"), raw.get("lon")
    for name, value, lo, hi in (("lat", lat, -90, 90), ("lon", lon, -180, 360)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
            raise PlanError(f"landing_point.{name} має бути числом у межах {lo}…{hi}")
    site_id = raw.get("site_id")
    name = raw.get("name")
    return [{"site_id": site_id if isinstance(site_id, str) else None, "name": name if isinstance(name, str) else None,
             "lat": float(lat), "lon": float(lon)}]


def _launch_moment(option: dict, departure: datetime, route: str) -> list[str]:
    """Моменти доби старту (UTC), коли майданчик проходить через площину перельоту: «коли саме запускати». Площина —
    орбітальна площина Місяця в момент прибуття; порожньо, якщо широта майданчика перевищує нахил площини (доворот)."""
    arrival = departure + timedelta(days=sum(TRAJECTORIES[route]["duration_days"]) / 2.0)
    r_m, v_m = transfer_cache.moon_state(arrival)
    normal = [r_m[1] * v_m[2] - r_m[2] * v_m[1], r_m[2] * v_m[0] - r_m[0] * v_m[2], r_m[0] * v_m[1] - r_m[1] * v_m[0]]
    day = departure.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    site = option["site"]
    try:
        windows = launch_core.launch_windows(float(site["lat"]), float(site["lon"]), normal, day, days=1.0)
    except ValueError:
        return []
    return [_iso(w.time_utc) for w in windows]


def _no_option_reason(body: Mapping, ranked: Mapping) -> str:
    """Чому для місця немає варіанта запуску: невдалий вибір ракети чи майданчика, а не лише «не вміщує масу»."""
    vehicle, site = body.get("vehicle", "any"), body.get("launch_site_id")
    excluded = {e["vehicle_id"]: e["reason"] for e in ranked.get("excluded", [])}
    if vehicle != "any" and site:  # рейтинг тут пише «майданчика немає», а для користувача це неузгоджений вибір
        return ("Вибрана ракета не стартує з вибраного майданчика. Змініть майданчик чи ракету "
                "або оберіть «підібрати автоматично».")
    if vehicle != "any" and vehicle in excluded:
        return (f"Вибрану ракету ({vehicle}) не можна використати: {excluded[vehicle]}. "
                "Оберіть іншу ракету або «підібрати автоматично».")
    if site:
        return ("З вибраного майданчика немає ракети, що вміщує масу. Оберіть інший майданчик "
                "або «підібрати автоматично».")
    return "Немає ракети, що вміщує масу; дозвольте кілька пусків або зменште масу."


def _mission_body(body: Mapping, night_h: float | None) -> dict:
    keys = ("crew", "days", "sizes", "mission_profile", "crew_members", "supply_days", "reserve_fraction")
    out = {k: body[k] for k in keys if body.get(k) is not None}
    if "crew_members" in out:  # M24: кількість людей задають самі члени екіпажу
        out.pop("crew", None)
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
        return text + f". Для нього немає варіанта запуску. {lead['launch_explanation'] or ''}".rstrip()
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
    crewed = body.get("mission_profile") == "crewed" or bool(body.get("crew_members")) or (body.get("crew") or 0) > 0
    restricted = False
    if crewed:  # пілотована місія: лише пряма траєкторія (3–5 діб); найекономніша — місяці в дорозі
        asked = body.get("trajectories")
        if asked is not None and (not isinstance(asked, list) or any(t != "direct" for t in asked)):
            raise PlanError("Для пілотованої місії дозволена лише пряма траєкторія (trajectories: [\"direct\"])")
        body = {**body, "trajectories": ["direct"]}
        restricted = True
    n_landing = _int(body, "landing_candidates", 3, 1, MAX_LANDING_CANDIDATES)
    limit = _int(body, "limit", 5, 1, 20)
    anchor = body.get("anchor", "landing")
    if anchor not in ANCHORS:
        raise PlanError(f"anchor: допустимо {', '.join(ANCHORS)}")
    if anchor == "landing" and not body.get("trajectories"):
        # дата старту залежить від маршруту (3–5 діб чи ≈ 105 діб до посадки), тож без явного вибору — швидкий (прямий)
        body = {**body, "trajectories": ["direct"]}
    explicit_departure = None
    if body.get("departure") is not None:
        try:
            explicit_departure = datetime.fromisoformat(str(body["departure"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise PlanError("departure: очікується ISO 8601") from exc
        if explicit_departure.tzinfo is None:
            explicit_departure = explicit_departure.replace(tzinfo=timezone.utc)
    after_arrival = body.get("surface_after_arrival", True)
    if not isinstance(after_arrival, bool):
        raise PlanError("surface_after_arrival має бути true або false")
    if anchor == "landing":
        # Календар = дата посадки: місце оцінюється від неї; старт — назад від посадки або явна дата `departure`
        surface_start = start
        if explicit_departure is not None:
            departure, flight_days = explicit_departure, (start - explicit_departure).total_seconds() / 86400.0
        else:
            departure, flight_days = _departure_for_landing(start, body)
        after_arrival = False
    else:  # режим сумісності: календар = старт; B20b: місце оцінюється після прибуття
        departure = explicit_departure or start
        flight_days = _assumed_flight_days(body) if after_arrival else 0.0
        surface_start = departure + timedelta(days=flight_days) if after_arrival else start
    surface_end = surface_start + (end - start)
    # crew без профілю стосується лише маси корисного навантаження; /search приймає його тільки з профілем
    search_body = {k: body[k] for k in SEARCH_KEYS if k in body and (k != "crew" or "mission_profile" in body)}
    chosen = _landing_point(body)
    if chosen:  # F34: точку вже вибрано на кроці 5 — оцінюємо лише її
        search_body = {**search_body, "include_catalog": False}
    found = search.search({**search_body, "limit": SEARCH_LIMIT}, surface_start, surface_end, points=chosen)
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
        launch_score = option["score_pct"] if option else 0.0
        plan = {
            "landing": _landing(chain),
            "requirements": {"feasible": chain["feasible"], "violations": chain["violations"],
                             "warnings": chain["warnings"], "unchecked": chain["unchecked"]},
            "mass_moon_kg": mass,
            "launch": option,
            "launch_explanation": ranked["leader_explanation"] or (None if option else _no_option_reason(body, ranked)),
            "route": None,
            "mission": None,
            "score_pct": round(chain["score_pct"] * launch_score / 100.0, 2),
        }
        plan["launch_windows_utc"] = []
        if option:
            dep_dt = datetime.fromisoformat(ranked["departure_utc"].replace("Z", "+00:00"))
            moments = _launch_moment(option, dep_dt, option["trajectory"])  # коли саме запускати цього дня
            plan["launch_windows_utc"] = moments
            plan["route"] = {**_route(chain, option, ranked["transfers"][option["trajectory"]]),
                             "departure_utc": moments[0] if moments else ranked["departure_utc"]}
        plans.append(plan)

    plans.sort(key=lambda p: (not p["requirements"]["feasible"], len(p["requirements"]["violations"]),
                              p["launch"] is None, not (p["launch"] or {}).get("fits", False), -p["score_pct"]))
    for i, p in enumerate(plans, start=1):
        p["rank"] = i

    notes = []
    if restricted:
        notes.append("Для пілотованої місії розглянуто лише пряму траєкторію (3–5 діб).")
    if chosen:
        pt = chosen[0]
        notes.append(f"Точку посадки взято з кроку 5 ({pt['lat']:.2f}°, {pt['lon']:.2f}°): пошуку по області немає.")
    if anchor == "landing" and explicit_departure is None:
        notes.append(f"Календар — дата посадки ({surface_start.date()}): старт обчислено за {flight_days:.2f} доби до "
                     f"неї ({_iso(departure)[:10]}).")
    if after_arrival or anchor == "landing":
        for p in plans:
            if p["route"]:
                a0, a1 = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in p["route"]["arrival_utc"])
                if not a0 - timedelta(days=1.5) <= surface_start <= a1 + timedelta(days=1.5):
                    notes.append(f"План {p['rank']}: прибуття {a0.date()}…{a1.date()} далеке від дати посадки "
                                 f"({surface_start.date()}) — світло й зв'язок оцінено для дати посадки.")
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
        "surface_period": {"start": _iso(surface_start), "end": _iso(surface_end),
                           "assumed_flight_days": round(flight_days, 2), "after_arrival": after_arrival,
                           "anchor": anchor},
        "departure_utc": _iso(departure),
        "grid": found["grid"],
        "landing_source": "selected" if chosen else "search",
        "landing_evaluated": len(found["chains"]),
        "hard_requirements_met": hard_ok,
        "auto_selected": plans[0]["rank"] if plans else None,
        "plans": plans[:limit],
        "explanation": _explain(plans, hard_ok),
        "notes": notes,
    }
