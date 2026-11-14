"""Бекенд 3D-моделей Сонця, Землі й Місяця: маніфест моделей і опис сцени (контракти ModelsManifest, Scene).

Маніфест каже, які моделі й текстури є на сервері (готують tools/build_system_assets.py і
tools/build_globe_textures.py у data_cache/), звідки вони, під якою ліцензією, і чим замінити відсутні (кулька
потрібного кольору). Сцена збирає положення, орієнтацію й освітлення тіл (app.services.system.system_state),
маркери (станції DSN на Землі, місця каталогу на Місяці) і вибрану точку — одним запитом, щоб фронтенд не
повторював астрономію. Одиниці: км; вектори маркерів — одиничні, у системі тіла (ITRS для Землі, MOON_ME для Місяця).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from flask import current_app
from skyfield.api import wgs84

from app.core import frames, launch, transfer
from app.core.constants import R_EARTH_KM, R_MOON_KM, R_SUN_KM
from app.core.ephemeris import get_ephemeris
from app.services import catalogs, dsn, sites, system

NASA_MEDIA = "NASA-матеріали: вільне використання з посиланням на джерело (NASA Media Usage Guidelines)"
# Земля — WGS84 (стиснення 1/298,257223563); Сонце й Місяць — кулі
EARTH_FLATTENING = 1.0 / 298.257223563

BODIES = {
    "sun": {"name": "Сонце", "radius_km": R_SUN_KM,
            "fallback": {"kind": "sphere", "color": "#ffd27a", "emissive": True}},
    "earth": {"name": "Земля", "radius_km": R_EARTH_KM, "flattening": EARTH_FLATTENING,
              "fallback": {"kind": "sphere", "color": "#2f6fb5", "emissive": False}},
    "moon": {"name": "Місяць", "radius_km": R_MOON_KM,
             "fallback": {"kind": "sphere", "color": "#b9b9b5", "emissive": False}},
}

# Файли в data_cache/<підкаталог>; url віддає app/routes/pages.py (/assets/system, /assets/globe)
ASSETS = [
    {"id": "sun-glb", "body": "sun", "kind": "gltf", "dir": "system", "file": "sun.glb",
     "source": "NASA (HEAT, 3D Resources)", "source_url": "https://science.nasa.gov/learn/heat/resource/sun-3d-model/",
     "license": NASA_MEDIA, "note": "Схематична текстура світіння, не знімок конкретної дати",
     "build": "python tools/build_system_assets.py"},
    {"id": "earth-texture", "body": "earth", "kind": "texture", "dir": "system", "file": "earth.jpg",
     "source": "USGS & NASA/Jet Propulsion Laboratory", "source_url": "https://science.nasa.gov/3d-resources/earth-a/",
     "license": NASA_MEDIA, "note": "Рельєф, розфарбований як суходіл/океан (не фото); довгота 0° по центру",
     "build": "python tools/build_system_assets.py"},
    {"id": "moon-color", "body": "moon", "kind": "texture", "dir": "globe", "file": "color.jpg",
     "source": "NASA SVS, CGI Moon Kit (LROC WAC; південніше 70° — альбедо LOLA)", "source_url": "https://svs.gsfc.nasa.gov/4720",
     "license": NASA_MEDIA, "note": "Карта для візуалізації, не для науки",
     "build": "python tools/build_globe_textures.py"},
    {"id": "moon-height", "body": "moon", "kind": "heightmap", "dir": "globe", "file": "height.bin",
     "source": "LOLA GDR (LDEM_16), PDS Geosciences Node",
     "source_url": "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/",
     "license": NASA_MEDIA, "note": "Висоти вершин сітки 0,25° (int16, м), рядки з півночі на південь",
     "build": "python tools/build_globe_textures.py"},
    {"id": "moon-slope", "body": "moon", "kind": "slope", "dir": "globe", "file": "slope.webp",
     "source": "LOLA GDR (LDEM_16), PDS Geosciences Node",
     "source_url": "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/",
     "license": NASA_MEDIA, "note": "Нахили кулі: R — схід, G — північ; 128 = 0",
     "build": "python tools/build_globe_textures.py"},
]


def _asset(spec: dict, cache: Path) -> dict:
    path = cache / spec["dir"] / spec["file"]
    exists = path.is_file()
    return {
        "id": spec["id"], "body": spec["body"], "kind": spec["kind"],
        "url": f"/assets/{spec['dir']}/{spec['file']}",
        "available": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "source": spec["source"], "source_url": spec["source_url"], "license": spec["license"], "note": spec["note"],
    }


def models_manifest() -> dict:
    cache = Path(current_app.config["CACHE_DIR"])
    assets = [_asset(spec, cache) for spec in ASSETS]
    bodies = []
    for body_id, info in BODIES.items():
        own = [a for a in assets if a["body"] == body_id]
        bodies.append({"id": body_id, **info, "assets": own, "complete": all(a["available"] for a in own)})
    missing = [spec for spec, a in zip(ASSETS, assets, strict=True) if not a["available"]]
    return {
        "bodies": bodies,
        "all_available": not missing,
        "missing": [spec["id"] for spec in missing],
        "build_commands": sorted({spec["build"] for spec in missing}),
        "note": "Без моделей і текстур 3D-вид малює кульки потрібного розміру й кольору (поле fallback).",
    }


def _unit(v) -> list[float]:
    v = np.asarray(v, dtype=float)
    return [round(float(x), 6) for x in v / np.linalg.norm(v)]


def _earth_unit(lat: float, lon: float, height_m: float = 0.0) -> list[float]:
    """Напрямок «з центру Землі на станцію» в ITRS (геодезичні WGS84 координати)."""
    return _unit(wgs84.latlon(lat, lon, height_m).itrs_xyz.km)


def _markers() -> dict:
    stations = [{"id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon,
                 "unit_itrs": _earth_unit(s.lat, s.lon, s.elevation_m)} for s in dsn.load_stations()]
    places = [{"id": s.id, "name": s.name, "lat": s.lat, "lon": (s.lon + 180.0) % 360.0 - 180.0,
               "category": s.category, "unit_me": _unit(frames.latlon_to_vector(s.lat, s.lon))}
              for s in sites.load_sites()]
    return {"earth": stations, "moon": places}


def _selected(lat: float, lon: float, when: datetime) -> dict:
    """Вибрана точка на Місяці: вектор у MOON_ME, напрямки на Сонце й Землю, їхні кути місця (гладка сфера)."""
    eph = get_ephemeris()
    t = eph.time(when)
    out = {"lat": lat, "lon": (lon + 180.0) % 360.0 - 180.0, "unit_me": _unit(frames.latlon_to_vector(lat, lon))}
    basis = frames.enu_basis(lat, lon)
    for name, track in (("sun", eph.sun_track(t, lat, lon)), ("earth", eph.earth_track(t, lat, lon))):
        vec = eph.sun_vector_me(t) if name == "sun" else eph.earth_vector_me(t)
        rel = vec - frames.site_vector(lat, lon)
        out[f"{name}_direction_me"] = _unit(rel)
        out[f"{name}_elevation_deg"] = round(float(track.elevation_deg), 3)
        out[f"{name}_azimuth_deg"] = round(float(track.azimuth_deg), 2)
        out[f"{name}_enu"] = _unit(basis @ rel)  # (схід, північ, зеніт) — для вигляду «з поверхні»
    return out


class LaunchSiteNotFound(LookupError):
    """Невідомий launch_site (404)."""


FLIGHT_TOF_DAYS = np.arange(3.0, 5.0 + 1e-9, 0.5)  # прямий переліт (launch.TRAJECTORIES["direct"])


def _flight_extras(when: datetime, launch_site_id: str, lat: float | None, lon: float | None) -> list[dict]:
    """Ракета на майданчику, траєкторія найкращого прямого перельоту зі старту (TLI) в момент `when` і модуль у
    вибраній точці (пропозиція П-5, задача G9). Траєкторія — дуга задачі двох тіл (docs/MATH.md, §21.5)."""
    site = next((s for s in catalogs.load_launch_sites() if s["id"] == launch_site_id), None)
    if site is None:
        raise LaunchSiteNotFound(f"Місце старту {launch_site_id} не знайдено")
    eph = get_ephemeris()
    when_utc = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
    best = min(transfer.dv_curve(eph, when_utc, FLIGHT_TOF_DAYS), key=lambda p: p.dv_total_m_s)
    r_m, v_m = transfer.moon_state_icrf(eph, best.arrival_utc)
    _, points = transfer.transfer_arc(r_m, v_m, best.tof_days, n=96)
    dep = launch.site_departure(site["lat"], launch.best_inclination_deg(site["lat"], best.min_parking_inclination_deg))
    iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    extras = [
        {"kind": "rocket", "id": f"rocket-{site['id']}", "site_id": site["id"], "name": site["name"],
         "lat": site["lat"], "lon": site["lon"], "unit_itrs": _earth_unit(site["lat"], site["lon"])},
        {"kind": "trajectory", "id": "transfer-direct", "frame": "icrf_geocentric_km",
         "points_km": [[round(float(c), 1) for c in p] for p in points],
         "departure_utc": iso(best.departure_utc), "arrival_utc": iso(best.arrival_utc),
         "tof_days": best.tof_days, "dv_tli_m_s": round(best.dv_tli_m_s, 1), "dv_loi_m_s": round(best.dv_loi_m_s, 1),
         "c3_km2_s2": round(best.c3_km2_s2, 3), "moon_at_arrival_km": [round(float(c), 1) for c in r_m],
         "launch_site_id": site["id"], "inclination_deg": round(dep.target_inclination_deg, 3),
         "windows_per_day": dep.windows_per_day,
         "note": "Найкращий прямий переліт (3–5 діб) зі старту TLI в момент сцени; дуга — задача двох тіл від "
                 "паркувальної орбіти 185 км до центру Місяця; ділянку виведення не показано"},
    ]
    if lat is not None and lon is not None:
        extras.append({"kind": "lander", "id": "lander", "lat": lat, "lon": (lon + 180.0) % 360.0 - 180.0,
                       "unit_me": _unit(frames.latlon_to_vector(lat, lon))})
    return extras


def scene(when: datetime, lat: float | None = None, lon: float | None = None, markers: bool = True,
          launch_site: str | None = None) -> dict:
    state = system.system_state(when)
    manifest = {b["id"]: b for b in models_manifest()["bodies"]}
    sun = np.asarray(state["sun_km"])
    bodies = [
        {"id": "sun", "position_km": state["sun_km"], "orientation": None, "rotation_deg": None,
         "unit_to_sun": None, "models": manifest["sun"]},
        {"id": "earth", "position_km": [0.0, 0.0, 0.0], "orientation": state["earth_orientation"],
         "rotation_deg": state["earth_rotation_deg"], "unit_to_sun": _unit(sun), "models": manifest["earth"]},
        {"id": "moon", "position_km": state["moon_km"], "orientation": state["moon_orientation"],
         "rotation_deg": None, "unit_to_sun": _unit(sun - np.asarray(state["moon_km"])), "models": manifest["moon"]},
    ]
    for b in bodies:
        info = BODIES[b["id"]]
        b.update(name=info["name"], radius_km=info["radius_km"], flattening=info.get("flattening", 0.0),
                 fallback=info["fallback"])
    result = {
        "datetime": state["datetime"],
        "frame": "icrf_geocentric_km",
        "orientation_note": "orientation — матриця 3×3 ICRF → система тіла (Земля — ITRS, Місяць — MOON_ME); "
                            "щоб повернути модель, застосуйте транспоновану (див. docs/CONTRACTS.md, §5.4)",
        "light": {"direction_icrf": _unit(sun), "source": "sun"},
        "bodies": bodies,
        "sub_solar_point": state["sub_solar_point"],
        "sub_earth_point": state["sub_earth_point"],
        "moon_illumination": state["moon_illumination"],
        "markers": _markers() if markers else {"earth": [], "moon": []},
        "selected": _selected(lat, lon, when) if lat is not None and lon is not None else None,
        # ракета, траєкторія й модуль (пропозиція П-5, G9) — лише коли задано launch_site
        "extras": _flight_extras(when, launch_site, lat, lon) if launch_site else [],
    }
    return result
