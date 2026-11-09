"""JSON API для фронтенду."""

from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, request

from app.services import dsn, metrics, sites

bp = Blueprint("api", __name__)


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


@bp.get("/metrics")
def get_metrics():
    """Метрики для оверлею: /api/metrics?lat=-89.5&lon=0&datetime=2027-01-01T00:00Z"""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    when = _parse_datetime(request.args.get("datetime"))
    try:
        result = metrics.site_metrics(lat, lon, when)
    except NotImplementedError as exc:
        return jsonify(error="not_implemented", detail=str(exc)), 501
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
        return jsonify(error="not_implemented", detail=str(exc)), 501
    return jsonify([{"site": s.to_dict(), "metrics": m} for s, m in zip(selected, results)])


@bp.errorhandler(400)
@bp.errorhandler(404)
def json_error(err):
    return jsonify(error=err.name, detail=err.description), err.code
