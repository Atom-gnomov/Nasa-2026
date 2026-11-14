"""JSON API для фронтенду."""

from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from app.services import catalogs, dsn, elevation, metrics, models3d, ranking, sites, system, temperature
from app.services import advice as advice_service
from app.services import search as search_service
from app.services import events as events_service
from app.services import meta as meta_service
from app.services import bootstrap
from app.services import mission as mission_service
from app.services import terrain as terrain_service
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


@bp.get("/data/status")
def data_status():
    """Стан підготовки даних NASA (температура, 3D-ресурси, глобус)."""
    return jsonify(bootstrap.preparer(current_app).status(bool(current_app.config["AUTO_PREPARE"])))


@bp.post("/data/prepare")
def data_prepare():
    """Запускає підготовку відсутніх наборів у фоні; відповідь одразу."""
    if not current_app.config["AUTO_PREPARE"]:
        return _error(400, "Автоматична підготовка даних вимкнена (LSE_AUTO_PREPARE=0); "
                           "запустіть скрипти tools/build_*.py")
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or set(body) - {"datasets"}:
        return _error(400, "Очікується {\"datasets\": [...]} або порожнє тіло")
    ids = body.get("datasets") or list(current_app.config["AUTO_PREPARE_DATASETS"])
    unknown = [i for i in ids if not isinstance(i, str) or i not in bootstrap.BY_ID]
    if unknown:
        return _error(400, f"Невідомі набори даних: {unknown}; є {', '.join(bootstrap.BY_ID)}")
    prep = bootstrap.preparer(current_app)
    started = prep.start(ids)
    return jsonify({"started": started, "status": prep.status(True)}), 202


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
    """Версії, джерела даних і ліміти: /api/meta"""
    return jsonify(meta_service.meta(API_VERSION))


@bp.get("/horizon")
def horizon_mask():
    """Маска горизонту з рельєфу LOLA: /api/horizon?lat=-89.67&lon=129.78&height=2"""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    height_m = _parse_optional_float("height", 0.0, 0.0, 1000.0)
    return jsonify(timeline_service.horizon_mask(lat, lon, height_m))


@bp.get("/terrain")
def terrain():
    """Ділянка рельєфу навколо точки з DEM LOLA: /api/terrain?lat=-89.67&lon=129.78&radius_km=5&n=201"""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    radius_km = (_parse_float("radius_km", terrain_service.MIN_RADIUS_KM, terrain_service.MAX_RADIUS_KM)
                 if "radius_km" in request.args else None)
    n = None
    if "n" in request.args:
        try:
            n = int(request.args["n"])
        except ValueError:
            abort(400, description="Параметр n має бути цілим числом")
        lo, hi = terrain_service.MIN_N, terrain_service.MAX_N
        if not lo <= n <= hi or n % 2 == 0:
            abort(400, description=f"Параметр n має бути непарним у межах [{lo}, {hi}]")
    return jsonify(terrain_service.terrain_patch(lat, lon, radius_km, n))


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
    """Сходи й заходи Сонця, Землі й доступність станцій DSN: /api/events?lat=..&lon=..&start=..&end=.."""
    lat = _parse_float("lat", -90, 90)
    lon = _parse_float("lon", -180, 360)
    height_m = _parse_optional_float("height", 0.0, 0.0, 1000.0)
    if "start" not in request.args or "end" not in request.args:
        abort(400, description="Параметри start і end обов'язкові")
    start = _parse_datetime(request.args["start"])
    end = _parse_datetime(request.args["end"])
    try:
        return jsonify(events_service.point_events(lat, lon, start, end, height_m))
    except ValueError as exc:
        return _error(400, str(exc))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.get("/models")
def models():
    """Маніфест 3D-моделей Сонця, Землі й Місяця: що є на сервері, джерела, ліцензії, запасний вигляд."""
    return jsonify(models3d.models_manifest())


@bp.get("/scene")
def scene():
    """Опис 3D-сцени на момент часу: положення, орієнтація, освітлення, маркери, вибрана точка Місяця.

    /api/scene?datetime=2027-07-01T00:00Z&lat=-89.5&lon=0  (lat і lon — разом, необов'язково)
    """
    when = _parse_datetime(request.args.get("datetime"))
    if ("lat" in request.args) != ("lon" in request.args):
        abort(400, description="Параметри lat і lon задаються разом")
    lat = _parse_float("lat", -90, 90) if "lat" in request.args else None
    lon = _parse_float("lon", -180, 360) if "lon" in request.args else None
    markers = request.args.get("markers", "1") not in ("0", "false")
    try:
        return jsonify(models3d.scene(when, lat, lon, markers))
    except RuntimeError as exc:
        return _error(503, str(exc))


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
    """Підбір найкращих точок у регіоні за вимогами й пріоритетами (docs/MATH.md, §19)."""
    try:
        body, start, end = _period_body()
        return jsonify(search_service.search(body, start, end))
    except ValueError as exc:  # включно з ranking.RankError і помилками періоду
        return _error(400, str(exc))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.get("/launch-window")
def launch_window():
    return _not_implemented("/api/launch-window")


@bp.post("/advice")
def advice():
    """Поради й пояснення від відкритої LLM до готових результатів (лише тлумачення, не розрахунок)."""
    try:
        return jsonify(advice_service.advise(request.get_json(silent=True)))
    except ValueError as exc:
        return _error(400, str(exc))
    except RuntimeError as exc:  # включно з advice.AdviceUnavailable і llm.LlmError
        return _error(503, str(exc))


def _utc(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _period_body(required: tuple[str, ...] = ()) -> tuple[dict, datetime, datetime]:
    """JSON-тіло POST-запиту з періодом: (тіло, start, end). Помилка запиту — ValueError (400)."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("Тіло запиту має бути JSON-об'єктом")
    for key in (*required, "start", "end"):
        if key not in body:
            raise ValueError(f"Поле {key} обов'язкове")
    try:
        return body, _utc(body["start"]), _utc(body["end"])
    except ValueError as exc:
        raise ValueError("Невірний формат start/end, очікується ISO 8601") from exc


@bp.post("/rank")
def rank():
    """Ранжування точок і порівняння найкращої з наступною (docs/MATH.md, §19)."""
    try:
        body, start, end = _period_body(("points",))
        if not isinstance(body["points"], list) or not all(isinstance(p, dict) for p in body["points"]):
            raise ValueError("points має бути списком об'єктів")
        return jsonify(ranking.rank(body, start, end))
    except ranking.SiteNotFound as exc:
        return _error(404, str(exc))
    except ValueError as exc:  # включно з ranking.RankError і помилками періоду
        return _error(400, str(exc))
    except RuntimeError as exc:
        return _error(503, str(exc))


@bp.post("/mission")
def mission():
    """Маса, вартість і ризик місії (docs/MATH.md, §20); коефіцієнти тимчасові."""
    body = request.get_json(silent=True)
    try:
        return jsonify(mission_service.compute(body if body is not None else {}))
    except mission_service.LaunchSiteNotFound as exc:
        return _error(404, str(exc))
    except ValueError as exc:  # включно з mission_service.MissionError і помилками ядра
        return _error(400, str(exc))


@bp.errorhandler(HTTPException)
def json_error(err: HTTPException):
    return _error(err.code or 500, err.description or err.name)
