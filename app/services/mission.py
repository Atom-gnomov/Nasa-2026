"""Модель місії для API (контракт MissionRequest / MissionResponse; docs/MATH.md, §20).

Збирає ядро: маса навантаження (`core.payload`) → вартість (`core.cost`) → ризик (`core.risk`).
Усі коефіцієнти ядра тимчасові (задача D4), тому відповідь завжди позначена `provisional: true`.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core import cost, payload, risk
from app.core.launch import TRAJECTORIES
from app.services import catalogs

ALLOWED = {"crew", "days", "sizes", "trajectory", "launch_site_id", "launch_lat", "longest_night_h"}


class MissionError(ValueError):
    """Помилка запиту (400)."""


class LaunchSiteNotFound(MissionError):
    """Невідомий launch_site_id (404)."""


def _number(body: Mapping, key: str, default: float, low: float, high: float | None = None) -> float:
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissionError(f"{key} має бути числом")
    if value < low or (high is not None and value > high):
        raise MissionError(f"{key} має бути в межах {low}…{high}" if high is not None else f"{key} має бути ≥ {low}")
    return float(value)


def _latitude(body: Mapping) -> tuple[float, str | None]:
    site_id, lat = body.get("launch_site_id"), body.get("launch_lat")
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


def compute(body: Mapping) -> dict:
    """Рахує місію за тілом запиту; `ValueError` (зокрема `MissionError`) — помилка вхідних даних."""
    if not isinstance(body, Mapping):
        raise MissionError("Тіло запиту має бути об'єктом")
    unknown = set(body) - ALLOWED
    if unknown:
        raise MissionError(f"Невідомі поля: {', '.join(sorted(unknown))}")

    crew = body.get("crew", 0)
    if isinstance(crew, bool) or not isinstance(crew, int) or not 0 <= crew <= payload.MAX_CREW:
        raise MissionError(f"crew має бути цілим від 0 до {payload.MAX_CREW}")
    days = _number(body, "days", 0.0, 0.0, payload.MAX_DAYS)
    night = _number(body, "longest_night_h", 0.0, 0.0)
    sizes = body.get("sizes")
    if sizes is not None and not isinstance(sizes, Mapping):
        raise MissionError("sizes має бути об'єктом")
    trajectory = body.get("trajectory", "direct")
    if trajectory not in TRAJECTORIES:
        raise MissionError(f"trajectory: допустимо {', '.join(TRAJECTORIES)}")
    lat, site_id = _latitude(body)

    budget = payload.payload_budget(sizes, crew=crew, days=days, longest_night_h=night)
    estimate = cost.mission_cost(budget.masses_kg, trajectory=trajectory, latitude_deg=lat)
    assessment = risk.assess(estimate.utilization, estimate.mass_moon_kg, budget.sizes, crew=crew,
                             trajectory=trajectory)
    return {
        "provisional": True,
        "launch_lat": lat,
        "launch_site_id": site_id,
        "payload": budget.to_dict(),
        "cost": estimate.to_dict(),
        "risk": assessment.to_dict(),
    }
