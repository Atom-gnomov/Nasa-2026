"""HTML-сторінки (вкладки інтерфейсу)."""

from flask import Blueprint, current_app, redirect, render_template, send_from_directory, url_for

bp = Blueprint("pages", __name__)

SYSTEM_MODES = ("earth-moon", "sun-moon-earth")


@bp.get("/")
def index():
    return redirect(url_for("pages.moon"))


@bp.get("/moon")
def moon():
    """Вкладка «Місяць»: глобус із вибором локації та порівнянням."""
    return render_template("moon.html", active_tab="moon")


@bp.get("/search")
def search():
    """Вкладка «Підбір»: найкращі точки за вимогами й пріоритетами (POST /api/search)."""
    return render_template("search.html", active_tab="search")


@bp.get("/system")
@bp.get("/system/<mode>")
def system(mode: str = "earth-moon"):
    """3D-вид системи з двома синхронізованими режимами."""
    if mode not in SYSTEM_MODES:
        mode = "earth-moon"
    return render_template("system.html", active_tab="system", mode=mode)


@bp.get("/assets/globe/<path:filename>")
def globe_asset(filename: str):
    """Текстури глобуса з data_cache/globe (готує tools/build_globe_textures.py)."""
    return send_from_directory(current_app.config["CACHE_DIR"] / "globe", filename, max_age=86400)


@bp.get("/assets/system/<path:filename>")
def system_asset(filename: str):
    """Моделі й текстури 3D-виду системи з data_cache/system (готує tools/build_system_assets.py)."""
    return send_from_directory(current_app.config["CACHE_DIR"] / "system", filename, max_age=86400)
