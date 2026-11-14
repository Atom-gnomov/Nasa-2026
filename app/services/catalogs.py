"""Прості каталоги з JSON-файлів app/data (схеми — contracts/schemas/)."""

from __future__ import annotations

import json
from functools import lru_cache

from flask import current_app


@lru_cache(maxsize=8)
def _load(path: str) -> tuple[dict, ...]:
    with open(path, encoding="utf-8") as f:
        return tuple(json.load(f))


def load_launch_sites() -> list[dict]:
    """Місця старту; відсутні необов'язкові поля заповнюються значеннями за замовчуванням."""
    records = _load(str(current_app.config["DATA_DIR"] / "launch_sites.json"))
    return [{"country": "", "note": "", "verified": False, **r} for r in records]


def load_launch_systems() -> list[dict]:
    """Системи запуску з першоджерел (app/data/launch_systems.json, задача D6)."""
    return list(_load(str(current_app.config["DATA_DIR"] / "launch_systems.json")))


def load_mission_thresholds() -> list[dict]:
    """Пороги профілів місії з першоджерел (app/data/mission_thresholds.json, задача D5)."""
    return list(_load(str(current_app.config["DATA_DIR"] / "mission_thresholds.json")))


def load_rockets() -> list[dict]:
    """Сучасні ракети з першоджерел (app/data/rockets.json, задача D7)."""
    return list(_load(str(current_app.config["DATA_DIR"] / "rockets.json")))


def load_vehicles() -> list[tuple[str, dict]]:
    """Єдиний каталог засобів запуску: системи D6 і ракети D7 як пари (каталог, рядок). Ідентифікатори унікальні."""
    pairs = [("launch_systems", r) for r in load_launch_systems()] + [("rockets", r) for r in load_rockets()]
    seen: set[str] = set()
    for _, row in pairs:
        if row["id"] in seen:
            raise ValueError(f"Дубль ідентифікатора засобу запуску: {row['id']}")
        seen.add(row["id"])
    return pairs
