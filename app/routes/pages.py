"""HTML-сторінки (вкладки інтерфейсу)."""

from flask import Blueprint, redirect, render_template, url_for

bp = Blueprint("pages", __name__)

SYSTEM_MODES = ("earth-moon", "sun-moon-earth")


@bp.get("/")
def index():
    return redirect(url_for("pages.moon"))


@bp.get("/moon")
def moon():
    """Вкладка «Місяць»: глобус із вибором локації та порівнянням."""
    return render_template("moon.html", active_tab="moon")


@bp.get("/system")
@bp.get("/system/<mode>")
def system(mode: str = "earth-moon"):
    """3D-вид системи з двома синхронізованими режимами."""
    if mode not in SYSTEM_MODES:
        mode = "earth-moon"
    return render_template("system.html", active_tab="system", mode=mode)
