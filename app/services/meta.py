"""Версії, джерела даних і ліміти сервера (контракт Meta)."""

from __future__ import annotations

from pathlib import Path

from flask import current_app

from app.services import elevation, events, metrics, ranking, timeline


def _temperature_source() -> dict | None:
    d = Path(current_app.config["TEMP_DIR"])
    if not (d.is_dir() and any(d.iterdir())):
        return None
    return {"id": "diviner", "kind": "temperature",
            "description": "LRO Diviner: GCP (0,5°, місцевий час) і полярний PRP (0,5 км)",
            "url": "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/"}


def meta(api_version: str) -> dict:
    sources = [
        {"id": "de440", "kind": "ephemeris", "description": "JPL DE440 (Park et al., 2021) через skyfield",
         "version": "DE440", "url": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/"},
    ]
    dems = elevation.available()
    for dem in dems:
        sources.append({"id": dem.id, "kind": "dem", "description": f"LOLA GDR, крок ~{dem.resolution_m:g} м",
                        "url": elevation.source_url(dem)})
    sources.append({"id": "horizon_terrain" if dems else "flat", "kind": "horizon_masks",
                    "description": ("Маска горизонту з рельєфу LOLA, рахується на льоту" if dems
                                    else "Гладка сфера (DEM LOLA не завантажено)")})
    temp = _temperature_source()
    if temp:
        sources.append(temp)
    sources += [
        {"id": "sites", "kind": "sites", "description": "Каталог місць посадки (app/data/sites.json)"},
        {"id": "dsn", "kind": "stations", "description": "Станції DSN (app/data/dsn_stations.json)"},
        {"id": "launch_sites", "kind": "launch_sites", "description": "Місця старту (app/data/launch_sites.json)"},
    ]
    return {
        "api_version": api_version,
        "ephemeris": "JPL DE440",
        "moon_orientation": "IAU 2015 (Archinal et al., 2018)",
        "moon_radius_km": 1737.4,
        "data_sources": sources,
        "limits": {
            "max_period_days": timeline.MAX_PERIOD_DAYS,
            "max_points": timeline.MAX_POINTS,
            "event_search_hours": metrics.SEARCH_DAYS * 24,
            "max_event_period_days": events.MAX_PERIOD_DAYS,
            "max_rank_points": ranking.MAX_POINTS,
        },
    }
