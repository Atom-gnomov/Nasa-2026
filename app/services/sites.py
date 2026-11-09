"""Каталог місць посадки на Місяці."""

import json
from dataclasses import asdict, dataclass
from functools import lru_cache

from flask import current_app


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat: float  # селенографічна широта, градуси (пд. — від'ємна)
    lon: float  # селенографічна довгота, градуси на схід
    category: str  # apollo | clps | artemis | international | custom
    note: str = ""
    verified: bool = False  # координати звірено з першоджерелом

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _load(path: str) -> tuple[Site, ...]:
    with open(path, encoding="utf-8") as f:
        return tuple(Site(**item) for item in json.load(f))


def load_sites() -> tuple[Site, ...]:
    return _load(str(current_app.config["DATA_DIR"] / "sites.json"))


def get_site(site_id: str) -> Site | None:
    return next((s for s in load_sites() if s.id == site_id), None)
