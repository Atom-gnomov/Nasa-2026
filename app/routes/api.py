"""JSON API для фронтенду."""

from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from app.services import catalogs, dsn, elevation, metrics, sites, system, temperature
from app.services import timeline as timeline_service

bp = Blueprint("api", __name__)

API_VERSION = "1.0.0"

# Коди помилок контракту (contracts/openapi.yaml → Error.error)
ERROR_CODES = {400: "bad_request", 404: "not_found", 501: "not_implemented", 503: "unavailable"}


def _error(status: int, detail: str):
    return jsonify(error=ERROR_CODES.get(status, "internal"), detail=detail), status


def _not_implemented(what: str):
    """Операція з контракту, реалізації якої ще немає (x-status: planned)."""
    return _error(501, f"{what} ще не реалізовано; контракт — contracts/openapi.yaml")


def _parse_datetime(value: str | None) -> datetime:
    """Розбирає ISO-дату з запиту; без дати — поточний момент UTC."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        abort(400, description="Невірний формат дати, очікується ISO 8601")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_float(name: str, lo: float, hi: float) -> float:
    try:
        value = float(request.args[name])
    except (KeyError, ValueError):
        abort(400, description=f"Параметр {name} обов'язковий і має бути числом")
    if not lo <= value <= hi:
        abort(400, description=f"Параметр {name} має бути в межах [{lo}, {hi}]")
    return value


def _parse_optional_float(name: str, default: float, lo: float, hi: float) -> float:
    return _parse_float(name, lo, hi) if name in request.args else default


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/sites")
def list_sites():
    return jsonify([s.to_dict() for s in sites.load_sites()])


@bp.get("/sites/<site_id>")
def get_site(site_id: str):
    site = sites.get_site(site_id)
    if site is None:
        abort(404, description="Місце не знайдено")
    return jsonify(site.to_dict())


@bp.get("/dsn")
def list_dsn():
    return jsonify([s.to_dict() for s in dsn.load_stations()])


@bp.get("/launch-sites")
def list_launch_sites():
    return jsonify(catalogs.load_launch_sites())


@bp.get("/metrics")
def get_metrics():
    """Метрики для оверлею: /api/metrics?lat=-89.5&lon=0&datetime=2027-01-01T00:00Z&height=2

    height — висота щогли/панелі над ґрунтом, метри (необов'язково, 0…1000).
    """
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    when = _parse_datetime(request.args.get("datetime"))
    height_m = _parse_optional_float("height", 0.0, 0.0, 1000.0)
    try:
        result = metrics.site_metrics(lat, lon, when, height_m)
    except NotImplementedError as exc:
        return _error(501, str(exc))
    except RuntimeError as exc:  # немає файлу ефемерид тощо
        current_app.logger.exception("metrics unavailable")
        return _error(503, str(exc))
    return jsonify(result.to_dict())


@bp.get("/compare")
def compare():
    """Порівняння місць: /api/compare?site=apollo-11&site=shackleton&datetime=..."""
    ids = request.args.getlist("site")
    if len(ids) < 2:
        abort(400, description="Потрібно щонайменше два параметри site")
    when = _parse_datetime(request.args.get("datetime"))
    selected = []
    for site_id in ids:
        site = sites.get_site(site_id)
        if site is None:
            abort(404, description=f"Місце {site_id} не знайдено")
        selected.append(site)
    try:
        results = [metrics.site_metrics(s.lat, s.lon, when).to_dict() for s in selected]
    except NotImplementedError as exc:
        return _error(501, str(exc))
    except RuntimeError as exc:
        return _error(503, str(exc))
    return jsonify([{"site": s.to_dict(), "metrics": m} for s, m in zip(selected, results, strict=True)])


# --- Операції з контракту, які ще не реалізовано (x-status: planned) ---------------

@bp.get("/meta")
def meta():
    return _not_implemented("/api/meta")


@bp.get("/horizon")
def horizon_mask():
    """Маска горизонту з рельєфу LOLA: /api/horizon?lat=-89.67&lon=129.78&height=2"""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    height_m = _parse_optional_float("height", 0.0, 0.0, 1000.0)
    return jsonify(timeline_service.horizon_mask(lat, lon, height_m))


@bp.get("/timeline")
def timeline():
    """Ряди й підсумки за період: /api/timeline?lat=..&lon=..&start=..&end=..&step_h=1"""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    height_m = _parse_optional_float("height", 0.0, 0.0, 1000.0)
    if "start" not in request.args or "end" not in request.args:
        abort(400, description="Параметри start і end обов'язкові")
    start = _parse_datetime(request.args["start"])
    end = _parse_datetime(request.args["end"])
    step_h = _parse_optional_float("step_h", 1.0, 0.1, 24.0)
    try:
        return jsonify(timeline_service.timeline(lat, lon, start, end, step_h, height_m))
    except ValueError as exc:
        return _error(400, str(exc))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.get("/events")
def events_list():
    return _not_implemented("/api/events")


@bp.get("/system")
def system_state():
    """Стан системи для 3D-сцен і освітлення глобуса: /api/system?datetime=2027-01-01T00:00Z"""
    when = _parse_datetime(request.args.get("datetime"))
    try:
        return jsonify(system.system_state(when))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.get("/orbits")
def get_orbits():
    """Оскулюючі орбіти Місяця й Землі для 3D-виду: /api/orbits?datetime=2027-01-01T00:00Z"""
    when = _parse_datetime(request.args.get("datetime"))
    try:
        return jsonify(system.orbits(when))
    except (RuntimeError, ValueError) as exc:
        return _error(503, str(exc))


@bp.get("/temperature")
def get_temperature():
    """Температура в точці (Diviner): /api/temperature?lat=-89.67&lon=129.78&datetime=2027-01-01T00:00Z"""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    when = _parse_datetime(request.args.get("datetime"))
    try:
        return jsonify(temperature.temperature_point(lat, lon, when))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.get("/temperature/map")
def get_temperature_map():
    """Мапа температури для шару глобуса: /api/temperature/map?kind=now&datetime=..."""
    kind = request.args.get("kind", "now")
    when = _parse_datetime(request.args.get("datetime"))
    try:
        return jsonify(temperature.temperature_map(kind, when))
    except ValueError as exc:
        return _error(400, str(exc))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.get("/elevation")
def get_elevation():
    """Висота LOLA в точці: /api/elevation?lat=-89.67&lon=129.78"""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    try:
        return jsonify(elevation.elevation(lat, lon))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.post("/search")
def search():
    return _not_implemented("/api/search")


@bp.get("/launch-window")
def launch_window():
    return _not_implemented("/api/launch-window")


@bp.post("/advice")
def advice():
    return _not_implemented("/api/advice")


@bp.errorhandler(HTTPException)
def json_error(err: HTTPException):
    return _error(err.code or 500, err.description or err.name)
