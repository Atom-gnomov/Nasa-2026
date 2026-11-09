"""Станції Deep Space Network та рекомендація станції для зв'язку."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache

from flask import current_app


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    antenna: str
    lat: float
    lon: float  # градуси на схід
    elevation_m: float
    min_elevation_deg: float = 6.0  # мінімальний кут місця антени (TODO: звірити з 810-005, модуль 301)

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _load(path: str) -> tuple[Station, ...]:
    with open(path, encoding="utf-8") as f:
        return tuple(Station(**item) for item in json.load(f))


def load_stations() -> tuple[Station, ...]:
    return _load(str(current_app.config["DATA_DIR"] / "dsn_stations.json"))


def recommend_station(when: datetime) -> Station | None:
    """Станція DSN, з якої Місяць найвище над горизонтом у момент `when`.

    TODO: обчислити кут місця Місяця для кожної станції через app.services.ephemeris.
    """
    raise NotImplementedError("Рекомендація станції DSN ще не реалізована")
