"""Спільна пам'ять розрахунків переходу Земля → Місяць (правило «не рахувати одне двічі»).

Крива «Δv ↔ час» і варіанти переходу залежать лише від дати старту (не від точки посадки, майданчика чи маси), а
планувальник, «Вікно запуску», рейтинг запусків і сцена «Системи» питають їх для тих самих дат десятки разів. Тут кожна
дата рахується один раз за життя процесу (ефемериди незмінні), решта викликів беруть готове. Повертаються незмінні
кортежі/словники лише для читання.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from app.core import transfer
from app.core.ephemeris import get_ephemeris

MAX_DATES = 512  # скільки дат старту тримаємо (≈ рік щодоби й запас)


def _key(departure: datetime) -> str:
    when = departure.astimezone(timezone.utc) if departure.tzinfo else departure.replace(tzinfo=timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _when(key: str) -> datetime:
    return datetime.strptime(key, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)


@lru_cache(maxsize=MAX_DATES)
def _curve(key: str, tofs: tuple) -> tuple:
    return tuple(transfer.dv_curve(get_ephemeris(), _when(key), list(tofs)))


@lru_cache(maxsize=MAX_DATES)
def _options(key: str) -> dict:
    return transfer.transfer_options(get_ephemeris(), _when(key))


def dv_curve(departure: datetime, tof_days) -> list:
    """`transfer.dv_curve` для дати старту: однакові (дата, набір часів перельоту) рахуються один раз."""
    return list(_curve(_key(departure), tuple(float(x) for x in tof_days)))


def transfer_options(departure: datetime) -> dict:
    """`transfer.transfer_options` для дати старту: один раз на дату (результат лише для читання)."""
    return _options(_key(departure))


@lru_cache(maxsize=MAX_DATES)
def _moon_state(key: str) -> tuple:
    r, v = transfer.moon_state_icrf(get_ephemeris(), _when(key))
    return tuple(float(x) for x in r), tuple(float(x) for x in v)


def moon_state(when: datetime) -> tuple[tuple, tuple]:
    """Положення (км) і швидкість (км/с) Місяця в ICRF у момент `when` — один раз на момент (спільна пам'ять)."""
    return _moon_state(_key(when))


def cache_info() -> dict:
    return {"curve": _curve.cache_info()._asdict(), "options": _options.cache_info()._asdict()}


def best_arrival_anchored(arrival: datetime, tof_grid) -> "transfer.TransferPoint":
    """Найекономніший прямий перехід, що **прибуває рівно в `arrival`** (календар = дата посадки): для кожного часу
    перельоту старт — за tof діб до посадки; береться мінімум Δv. Кожна дата старту рахується один раз."""
    points = [dv_curve(arrival - timedelta(days=float(t)), [float(t)])[0] for t in tof_grid]
    return min(points, key=lambda p: p.dv_total_m_s)
