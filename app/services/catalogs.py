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
