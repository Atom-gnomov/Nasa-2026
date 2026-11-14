"""Рейтинг стартів до точки Місяця для API (контракт LaunchRankingRequest / LaunchRankingResponse; задача B15).

Збирає ядро: перехід Земля → Місяць (`core.transfer`, M10) → ранжування майданчиків і ракет (`core.launch_rank`,
M20) за каталогами D6 (`launch_sites`, `launch_systems`) і D7 (`rockets`). Маса на Місяці — з запиту або з моделі
місії (`services.mission`, B9). Ціни й імовірності відмови тимчасові, тому `provisional: true`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from app.core import launch_rank, risk, transfer
from app.core.ephemeris import get_ephemeris
from app.core.launch import TRAJECTORIES
from app.services import catalogs
from app.services import mission as mission_service

ALLOWED = {"lat", "lon", "datetime", "mass_moon_kg", "crew", "days", "sizes", "vehicle", "trajectories", "priorities",
           "mode", "include_design_targets", "allow_multiple_launches", "limit"}
FACTOR_LABELS = {"fuel": "паливо (маса на НОО)", "speed": "швидкість перельоту", "windows": "вікна запуску на добу",
                 "cost": "вартість запуску", "risk": "ризик"}
MAX_LIMIT = 200


class LaunchRankingError(ValueError):
    """Помилка запиту (400)."""


class VehicleNotFound(LaunchRankingError):
    """Невідома ракета чи система запуску (404)."""


def _number(body: Mapping, key: str, low: float, high: float, default: float | None = None) -> float:
    value = body.get(key, default)
    if value is None:
        raise LaunchRankingError(f"Потрібне поле {key}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LaunchRankingError(f"{key} має бути числом")
    if not low <= value <= high:
        raise LaunchRankingError(f"{key} має бути в межах {low}…{high}")
    return float(value)


def _flag(body: Mapping, key: str, default: bool) -> bool:
    value = body.get(key, default)
    if not isinstance(value, bool):
        raise LaunchRankingError(f"{key} має бути true або false")
    return value


def _departure(value) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if not isinstance(value, str):
        raise LaunchRankingError("datetime має бути рядком ISO 8601")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LaunchRankingError("Невірний формат datetime, очікується ISO 8601") from exc
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _list(body: Mapping, key: str, allowed, default) -> list[str]:
    value = body.get(key, list(default))
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise LaunchRankingError(f"{key} має бути непорожнім списком рядків")
    if len(set(value)) != len(value):
        raise LaunchRankingError(f"{key}: значення мають бути унікальними")
    bad = [v for v in value if v not in allowed]
    if bad:
        raise LaunchRankingError(f"{key}: невідомі значення {', '.join(bad)} (допустимо {', '.join(allowed)})")
    return value


def _mass(body: Mapping) -> float:
    if "mass_moon_kg" in body:
        if any(k in body for k in ("crew", "days", "sizes")):
            raise LaunchRankingError("Задайте або mass_moon_kg, або crew/days/sizes, не разом")
        mass = body["mass_moon_kg"]
        if isinstance(mass, bool) or not isinstance(mass, (int, float)) or mass <= 0:
            raise LaunchRankingError("mass_moon_kg має бути додатним числом")
        return float(mass)
    mission = mission_service.compute({k: body[k] for k in ("crew", "days", "sizes") if k in body})
    return float(mission["payload"]["total_kg"])


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _transfer_dict(opt: transfer.TransferOption) -> dict:
    return {
        "trajectory": opt.trajectory, "name": opt.name, "method": opt.method,
        "duration_days": list(opt.duration_days), "arrival_utc": [_iso(t) for t in opt.arrival_utc],
        "dv_tli_m_s": None if opt.dv_tli_m_s is None else list(opt.dv_tli_m_s),
        "dv_loi_m_s": None if opt.dv_loi_m_s is None else list(opt.dv_loi_m_s),
        "dv_total_m_s": list(opt.dv_total_m_s),
        "c3_km2_s2": None if opt.best is None else opt.best.c3_km2_s2,
    }


def _option_dict(o: launch_rank.LaunchOption) -> dict:
    c = o.candidate
    return {
        "rank": o.rank, "score_pct": o.score_pct, "pareto": o.pareto, "fits": o.fits, "fit_note": o.fit_note,
        "site": {"id": c.site_id, "name": c.site_name, "kind": c.site_kind, "lat": c.lat, "lon": c.lon},
        "vehicle": {"id": c.vehicle_id, "name": c.vehicle_name, "catalog": c.catalog, "status": c.status,
                    "verified_by_flight": c.verified_by_flight},
        "trajectory": o.trajectory, "inclination_deg": o.inclination_deg, "windows_per_day": o.windows_per_day,
        "inertial_azimuths_deg": list(o.inertial_azimuths_deg), "dv_total_m_s": list(o.dv_total_m_s),
        "dv_site_penalty_m_s": o.dv_site_penalty_m_s, "duration_days": list(o.duration_days),
        "mass_leo_kg": o.mass_leo_kg, "capacity_basis": o.capacity_basis, "utilization": o.utilization,
        "launches": o.launches, "launch_cost_usd": list(o.launch_cost_usd),
        "risk": {"p": o.risk_p, "range": list(o.risk_range), "band": o.risk_band,
                 "band_label": risk.BAND_LABELS[o.risk_band]},
        "factors": dict(o.factors), "provisional_fields": list(o.provisional_fields),
    }


def _label(o: launch_rank.LaunchOption) -> str:
    return f"{o.candidate.site_name} + {o.candidate.vehicle_name} ({TRAJECTORIES[o.trajectory]['name'].lower()})"


def explain_leader(options: list[launch_rank.LaunchOption]) -> str | None:
    """Чому перший варіант кращий за наступний допустимий: фактор із найбільшою перевагою."""
    feasible = [o for o in options if o.fits]
    if not feasible:
        return "Жоден варіант не вміщує масу в одну ракету; зменште масу або дозвольте кілька пусків."
    if len(feasible) == 1:
        return f"Єдиний допустимий варіант: {_label(feasible[0])}."
    a, b = feasible[0], feasible[1]
    diffs = {f: a.factors[f] - b.factors[f] for f in a.factors}
    best = max(diffs, key=lambda f: diffs[f])
    if diffs[best] <= 1e-9:
        return f"{_label(a)} і {_label(b)} рівноцінні за факторами; порядок — за назвою."
    worse = [FACTOR_LABELS[f] for f, d in diffs.items() if d < -1e-9]
    text = f"{_label(a)} випереджає {_label(b)}: найбільша перевага — {FACTOR_LABELS[best]}"
    return text + (f"; поступається: {', '.join(worse)}." if worse else ".")


def compute(body: Mapping) -> dict:
    """Рейтинг стартів за тілом запиту; `ValueError` (зокрема `LaunchRankingError`) — помилка вхідних даних,
    `RuntimeError` — немає ефемерид (503)."""
    if not isinstance(body, Mapping):
        raise LaunchRankingError("Тіло запиту має бути об'єктом")
    unknown = set(body) - ALLOWED
    if unknown:
        raise LaunchRankingError(f"Невідомі поля: {', '.join(sorted(unknown))}")
    lat = _number(body, "lat", -90.0, 90.0)
    lon = _number(body, "lon", -180.0, 360.0)
    departure = _departure(body.get("datetime"))
    mass = _mass(body)
    trajectories = _list(body, "trajectories", tuple(TRAJECTORIES), TRAJECTORIES)
    priorities = _list(body, "priorities", launch_rank.FACTORS, launch_rank.FACTORS)
    mode = body.get("mode", "weighted")
    if mode not in launch_rank.MODES:
        raise LaunchRankingError(f"mode: допустимо {', '.join(launch_rank.MODES)}")
    include_design = _flag(body, "include_design_targets", True)
    multi = _flag(body, "allow_multiple_launches", False)
    limit = body.get("limit", 30)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise LaunchRankingError(f"limit має бути цілим від 1 до {MAX_LIMIT}")

    rockets, systems = catalogs.load_rockets(), catalogs.load_launch_systems()
    vehicle = body.get("vehicle", "any")
    if not isinstance(vehicle, str):
        raise LaunchRankingError("vehicle має бути рядком")
    if vehicle != "any":
        rockets = [r for r in rockets if r["id"] == vehicle]
        systems = [s for s in systems if s["id"] == vehicle]
        if not rockets and not systems:
            raise VehicleNotFound(f"Ракету чи систему запуску {vehicle} не знайдено")

    transfers = transfer.transfer_options(get_ephemeris(), departure)
    result = launch_rank.rank_launches(
        catalogs.load_launch_sites(), transfers, mass, rockets=rockets, launch_systems=systems,
        trajectories=trajectories, priorities=priorities, mode=mode, include_design_targets=include_design,
        allow_multiple_launches=multi,
    )
    options = result["options"]
    return {
        "departure_utc": _iso(departure),
        "moon_point": {"lat": lat, "lon": lon},
        "mass_moon_kg": mass,
        "moon_declination_deg": result["moon_declination_deg"],
        "priorities": priorities,
        "mode": mode,
        "provisional": True,
        "transfers": {t: _transfer_dict(transfers[t]) for t in trajectories},
        "options": [_option_dict(o) for o in options[:limit]],
        "excluded": result["excluded"],
        "total_options": len(options),
        "leader_explanation": explain_leader(options) if options else None,
    }
