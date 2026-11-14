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
    """«Підбір» живе на сторінці «Місяць» під глобусом (результати позначаються на карті): стара адреса веде туди."""
    return redirect(url_for("pages.moon") + "#search")


@bp.get("/launch-window")
def launch_window():
    """Вкладка «Вікно запуску»: шкала дат старту з оцінкою у %, найкраща дата виділена (F7)."""
    return render_template("launch_window.html", active_tab="launch")


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
