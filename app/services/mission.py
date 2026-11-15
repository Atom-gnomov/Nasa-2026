"""Модель місії для API (контракт MissionRequest / MissionResponse; docs/MATH.md, §20).

Збирає ядро: маса навантаження (`core.payload`) → вартість (`core.cost`) → ризик (`core.risk`).
Усі коефіцієнти ядра тимчасові (задача D4), тому відповідь завжди позначена `provisional: true`.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core import cost, crew as crew_model, launch_system, mission_profile, payload, risk
from app.core.launch import TRAJECTORIES
from app.services import catalogs

ALLOWED = {"crew", "days", "sizes", "trajectory", "launch_site_id", "launch_lat", "launch_system_id",
           "longest_night_h", "mission_profile", "parameters_basis", "crew_members", "supply_days", "reserve_fraction"}


class MissionError(ValueError):
    """Помилка запиту (400)."""


class LaunchSiteNotFound(MissionError):
    """Невідомий launch_site_id або launch_system_id (404)."""


def _number(body: Mapping, key: str, default: float, low: float, high: float | None = None) -> float:
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissionError(f"{key} має бути числом")
    if value < low or (high is not None and value > high):
        raise MissionError(f"{key} має бути в межах {low}…{high}" if high is not None else f"{key} має бути ≥ {low}")
    return float(value)


def _system(body: Mapping) -> launch_system.LaunchSystem | None:
    system_id = body.get("launch_system_id")
    if system_id is None:
        return None
    if not isinstance(system_id, str):
        raise MissionError("launch_system_id має бути рядком")
    found = next(((cat, r) for cat, r in catalogs.load_vehicles() if r["id"] == system_id), None)
    if found is None:
        raise LaunchSiteNotFound(f"Засіб запуску {system_id} не знайдено")
    return launch_system.from_catalog(found[1], found[0])


def _latitude(body: Mapping, system: launch_system.LaunchSystem | None = None) -> tuple[float, str | None]:
    """Широта старту: явні launch_site_id / launch_lat, інакше перше місце системи запуску, інакше екватор."""
    site_id, lat = body.get("launch_site_id"), body.get("launch_lat")
    if site_id is None and lat is None and system is not None and system.launch_site_ids:
        site_id = system.launch_site_ids[0]
    if site_id is not None and lat is not None:
        raise MissionError("Задайте або launch_site_id, або launch_lat, не обидва")
    if site_id is not None:
        if not isinstance(site_id, str):
            raise MissionError("launch_site_id має бути рядком")
        site = next((s for s in catalogs.load_launch_sites() if s["id"] == site_id), None)
        if site is None:
            raise LaunchSiteNotFound(f"Місце старту {site_id} не знайдено")
        return float(site["lat"]), site_id
    return _number(body, "launch_lat", 0.0, -90.0, 90.0), None


def _crew_members(body: Mapping) -> list | None:
    raw = body.get("crew_members")
    if raw is None:
        return None
    if not isinstance(raw, list) or not 1 <= len(raw) <= payload.MAX_CREW:
        raise MissionError(f"crew_members має бути списком від 1 до {payload.MAX_CREW} людей")
    try:
        return [crew_model.parse_member(m) for m in raw]
    except ValueError as exc:
        raise MissionError(str(exc)) from exc


def _categories(budget: payload.PayloadBudget, estimate: cost.CostEstimate) -> dict:
    """Числа кожної категорії навантаження для повзунків: розмір, маса, вартість (діапазон) і споживана потужність."""
    table = cost.DEFAULT_TABLE
    price = {"equipment": table.equipment_usd_per_kg, "life_support": table.life_support_usd_per_kg,
             "comfort": table.comfort_usd_per_kg}
    out = {}
    for name in payload.CATEGORIES:
        mass = budget.masses_kg[name]
        out[name] = {"size": budget.sizes[name], "mass_kg": mass,
                     "usd": [price[name][0] * mass, price[name][1] * mass],
                     "power_w": budget.power_by_category_w[name]}
    return out


def compute(body: Mapping) -> dict:
    """Рахує місію за тілом запиту; `ValueError` (зокрема `MissionError`) — помилка вхідних даних."""
    if not isinstance(body, Mapping):
        raise MissionError("Тіло запиту має бути об'єктом")
    unknown = set(body) - ALLOWED
    if unknown:
        raise MissionError(f"Невідомі поля: {', '.join(sorted(unknown))}")

    profile = None
    if body.get("mission_profile") is not None:
        try:
            profile = mission_profile.resolve(body["mission_profile"], catalogs.load_mission_thresholds(),
                                              crew=body.get("crew"))
        except ValueError as exc:
            raise MissionError(str(exc)) from exc
    members = _crew_members(body)
    if members is not None:  # M24: склад екіпажу задає кількість людей
        explicit = body.get("crew")
        if explicit is not None and explicit != len(members):
            raise MissionError(f"crew ({explicit}) не збігається з кількістю crew_members ({len(members)})")
        if profile is not None and profile.profile == "uncrewed":
            raise MissionError("crew_members не можна задавати для безпілотної місії")
        if body.get("mission_profile") is not None:
            try:
                profile = mission_profile.resolve(body["mission_profile"], catalogs.load_mission_thresholds(),
                                                  crew=len(members))
            except ValueError as exc:
                raise MissionError(str(exc)) from exc
    crew = len(members) if members is not None else (profile.crew if profile else body.get("crew", 0))
    if isinstance(crew, bool) or not isinstance(crew, int) or not 0 <= crew <= payload.MAX_CREW:
        raise MissionError(f"crew має бути цілим від 0 до {payload.MAX_CREW}")
    days = _number(body, "days", 0.0, 0.0, payload.MAX_DAYS)
    night = _number(body, "longest_night_h", 0.0, 0.0)
    sizes = body.get("sizes")
    if sizes is not None and not isinstance(sizes, Mapping):
        raise MissionError("sizes має бути об'єктом")
    basis = body.get("parameters_basis", "model")
    if basis not in payload.BASES:
        raise MissionError(f"parameters_basis: допустимо {', '.join(payload.BASES)}")
    params, applied = payload.DEFAULT_PARAMS, []
    if basis == "sourced":  # M22: маси й енергетика — діапазони з першоджерел NASA (D4), решта лишається тимчасовою
        params, applied = payload.params_from_tables(catalogs.load_payload_tables())
    trajectory = body.get("trajectory", "direct")
    if trajectory not in TRAJECTORIES:
        raise MissionError(f"trajectory: допустимо {', '.join(TRAJECTORIES)}")
    system = _system(body)
    lat, site_id = _latitude(body, system)

    supplies = None
    consumables = None
    if members is not None:
        crew_params = crew_model.CrewParams(reserve_fraction=_number(body, "reserve_fraction", 0.15, 0.0, 2.0))
        supply_days = body.get("supply_days")
        try:
            supplies = crew_model.supplies_report(members, days, None if supply_days is None else supply_days,
                                                  crew_params)
        except ValueError as exc:
            raise MissionError(str(exc)) from exc
        consumables = supplies["loaded_total_kg"]
    budget = payload.payload_budget(sizes, crew=crew, days=days, longest_night_h=night, params=params,
                                    consumables_kg=consumables)
    choice = launch_system.to_rocket(system, trajectory=trajectory) if system else None
    rocket_kwargs = {"rocket": choice.rocket} if choice else {}
    estimate = cost.mission_cost(budget.masses_kg, trajectory=trajectory, latitude_deg=lat, **rocket_kwargs)
    risk_kwargs = {"params": choice.risk_params()} if choice else {}  # база відмови — цієї ракети (M21)
    assessment = risk.assess(estimate.utilization, estimate.mass_moon_kg, budget.sizes, crew=crew,
                             trajectory=trajectory, **risk_kwargs)
    return {
        "provisional": True,
        "launch_lat": lat,
        "launch_site_id": site_id,
        "parameters_basis": basis,
        "sourced_parameters": applied,
        "profile": profile.to_dict() if profile else None,
        "launch_system": ({**choice.to_dict(),
                           "fit": launch_system.fit(estimate.mass_leo_kg, system, choice.rocket.capacity_leo_kg)}
                          if choice else None),
        "crew_supplies": supplies,
        "categories": _categories(budget, estimate),
        "payload": budget.to_dict(),
        "cost": estimate.to_dict(),
        "risk": assessment.to_dict(),
    }
