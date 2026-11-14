"""Перехід Земля → Місяць за зшитими конічними перерізами (docs/MATH.md, §21.5; задача M10).

Модель («нульова сфера дії», двотільні ділянки):
    1. Апарат на коловій паркувальній орбіті Землі радіуса r₀ = R_З + h_пар.
    2. Для часу перельоту T розв'язуємо задачу Ламберта від точки паркувальної орбіти до положення центру
       Місяця в момент прибуття t_прибуття = t_старту + T (положення й швидкість Місяця — DE440).
       Δv_TLI = |v₁ − v_кол|; кут переходу θ вибираємо так, щоб мінімізувати сумарний Δv.
    3. Біля Місяця: надлишкова швидкість v∞ = |v₂ − v_Місяця|; гальмування на колову орбіту висоти h_LLO:
       Δv_LOI = √(v∞² + 2μ_М/r) − √(μ_М/r).
    4. Площина переходу — площина орбіти Місяця (найменший v∞). Нахил площини паркувальної орбіти до екватора
       Землі має бути не меншим за |схилення Місяця| у момент прибуття — це вихід для M19 (§21.3).

Результат — крива Δv(T) («паливо ↔ час») і дата прибуття. Економний (низькоенергетичний) варіант двотільна модель
не описує (там суттєве тяжіння Сонця), тому він — оцінка діапазоном відносно найкращого прямого (§21.5).

⚠️ Це інженерна оцінка, а не розрахунок траєкторії конкретної місії: точність зшитих конічних перерізів —
порядку десятків м/с у Δv_TLI і годин у часі перельоту. Площина — ICRF (екватор J2000), прецесію не враховуємо.
Чисті функції на numpy, без Flask.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.constants import R_EARTH_KM, R_MOON_KM
from app.core.launch import TRAJECTORIES
from app.core.orbits import GM_EARTH, GM_MOON, osculating_orbit

Range = tuple[float, float]

# Економія сумарного Δv низькоенергетичного переходу відносно прямого, м/с (MATH §21.5; джерела розходяться).
LOW_ENERGY_DV_SAVING_M_S: Range = (100.0, 400.0)


@dataclass(frozen=True)
class TransferParams:
    """Опорні орбіти переходу.

    ⚠️ Опорні значення, а не вимоги місії: паркувальна орбіта ≈ 185 км (100 морських миль, як у Apollo),
    низька колова орбіта Місяця 100 км. Обидва параметри можна змінити.
    """

    parking_altitude_km: float = 185.0
    llo_altitude_km: float = 100.0
    min_angle_deg: float = 90.0  # межі пошуку кута переходу θ
    max_angle_deg: float = 179.5  # 180° — вироджений випадок задачі Ламберта


DEFAULT_PARAMS = TransferParams()


@dataclass(frozen=True)
class TransferPoint:
    """Одна точка кривої «паливо ↔ час»."""

    tof_days: float
    departure_utc: datetime | None
    arrival_utc: datetime | None
    dv_tli_m_s: float
    c3_km2_s2: float  # характеристична енергія після TLI (для місткості ракет «на траєкторію до Місяця»)
    v_inf_km_s: float  # надлишкова швидкість відносно Місяця
    dv_loi_m_s: float
    dv_total_m_s: float
    transfer_angle_deg: float
    moon_distance_km: float
    min_parking_inclination_deg: float  # |схилення Місяця| у момент прибуття

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TransferOption:
    """Підсумок варіанта траєкторії діапазонами."""

    trajectory: str  # "direct" | "low_energy"
    name: str
    method: str  # "patched_conic" — розрахунок; "estimate" — оцінка відносно прямого
    duration_days: Range
    arrival_utc: tuple[datetime, datetime]
    dv_tli_m_s: Range | None
    dv_loi_m_s: Range | None
    dv_total_m_s: Range
    best: TransferPoint | None

    def to_dict(self) -> dict:
        return asdict(self)


# --- задача Ламберта (універсальні змінні, Curtis «Orbital Mechanics for Engineering Students», алг. 5.2) ------


def _stumpff_c(z: float) -> float:
    if z > 1e-4:
        return (1.0 - math.cos(math.sqrt(z))) / z
    if z < -1e-4:
        return (math.cosh(math.sqrt(-z)) - 1.0) / (-z)
    return 0.5 - z / 24.0 + z * z / 720.0


def _stumpff_s(z: float) -> float:
    if z > 1e-4:
        s = math.sqrt(z)
        return (s - math.sin(s)) / s**3
    if z < -1e-4:
        s = math.sqrt(-z)
        return (math.sinh(s) - s) / s**3
    return 1.0 / 6.0 - z / 120.0 + z * z / 5040.0


def lambert(r1_km, r2_km, tof_s: float, mu: float = GM_EARTH, normal=None) -> tuple[np.ndarray, np.ndarray]:
    """Швидкості v₁, v₂ (км/с) на дузі з r₁ у r₂ за час tof_s (менше одного оберту).

    normal — напрямок кутового моменту руху (прямий рух навколо нього); за замовчуванням вісь z.
    """
    r1 = np.asarray(r1_km, dtype=float)
    r2 = np.asarray(r2_km, dtype=float)
    if tof_s <= 0:
        raise ValueError("Час перельоту має бути додатним")
    n1, n2 = float(np.linalg.norm(r1)), float(np.linalg.norm(r2))
    cos_theta = float(np.clip(r1 @ r2 / (n1 * n2), -1.0, 1.0))
    theta = math.acos(cos_theta)
    ref = np.array([0.0, 0.0, 1.0]) if normal is None else np.asarray(normal, dtype=float)
    if float(np.cross(r1, r2) @ ref) < 0:
        theta = 2 * math.pi - theta
    if abs(1.0 - cos_theta) < 1e-12 or abs(math.sin(theta)) < 1e-9:
        raise ValueError("Кут переходу 0° або 180°: задача Ламберта вироджена")
    a = math.sin(theta) * math.sqrt(n1 * n2 / (1.0 - cos_theta))

    def y(z: float) -> float:
        return n1 + n2 + a * (z * _stumpff_s(z) - 1.0) / math.sqrt(_stumpff_c(z))

    target = math.sqrt(mu) * tof_s

    def f(z: float) -> float:
        yz = y(z)
        if yz <= 0:
            return -target  # область без розв'язку: «замало часу» — від'ємне значення тримає брекет
        return (yz / _stumpff_c(z)) ** 1.5 * _stumpff_s(z) + a * math.sqrt(yz) - target

    lo, hi = -1.0e3, 4 * math.pi**2 * (1.0 - 1e-6)  # один оберт: z < 4π² (у самій межі C(z) → 0)
    f_lo, f_hi = f(lo), f(hi)
    if not (f_lo < 0 < f_hi):
        raise ValueError("Задача Ламберта не має розв'язку на одному оберті")
    # метод Іллінойса (хибне положення з гарантованим брекетом)
    side = 0
    z = lo
    for _ in range(200):
        z = (lo * f_hi - hi * f_lo) / (f_hi - f_lo)
        fz = f(z)
        if abs(fz) < 1e-10 * target or hi - lo < 1e-14:
            break
        if fz * f_hi > 0:
            hi, f_hi = z, fz
            if side == 1:
                f_lo /= 2
            side = 1
        else:
            lo, f_lo = z, fz
            if side == -1:
                f_hi /= 2
            side = -1
    yz = y(z)
    f_ = 1.0 - yz / n1
    g = a * math.sqrt(yz / mu)
    gdot = 1.0 - yz / n2
    v1 = (r2 - f_ * r1) / g
    v2 = (gdot * r2 - r1) / g
    return v1, v2


# --- окремі ділянки --------------------------------------------------------------------------------------------


def circular_speed_km_s(radius_km: float, mu: float = GM_EARTH) -> float:
    return math.sqrt(mu / radius_km)


def loi_dv_m_s(v_inf_km_s, altitude_km: float = DEFAULT_PARAMS.llo_altitude_km, mu: float = GM_MOON) -> np.ndarray:
    """Гальмування біля Місяця з гіперболи v∞ на колову орбіту висоти altitude_km, м/с."""
    r = R_MOON_KM + altitude_km
    v = np.asarray(v_inf_km_s, dtype=float)
    return 1000.0 * (np.sqrt(v * v + 2 * mu / r) - np.sqrt(mu / r))


def hohmann_dv_m_s(r1_km: float, r2_km: float, mu: float = GM_EARTH) -> tuple[float, float]:
    """Перший імпульс і час гомановського переходу між коловими орбітами (м/с, доби) — для перевірок."""
    a = (r1_km + r2_km) / 2
    dv = math.sqrt(mu * (2 / r1_km - 1 / a)) - math.sqrt(mu / r1_km)
    return 1000.0 * dv, math.pi * math.sqrt(a**3 / mu) / 86400.0


def _declination_deg(r) -> float:
    r = np.asarray(r, dtype=float)
    return math.degrees(math.asin(float(np.clip(r[2] / np.linalg.norm(r), -1.0, 1.0))))


def _transfer_plane(r_m: np.ndarray, v_m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Базис площини переходу (площина орбіти Місяця): e1 — на Місяць, e2 — за рухом, h — нормаль."""
    h = np.cross(r_m, v_m)
    h_hat = h / np.linalg.norm(h)
    e1 = r_m / np.linalg.norm(r_m)
    return e1, np.cross(h_hat, e1), h_hat


def _departure_point(theta_deg: float, r0: float, e1: np.ndarray, e2: np.ndarray) -> np.ndarray:
    """Точка відльоту на паркувальній орбіті: на θ «позаду» напрямку на Місяць за рухом."""
    th = math.radians(theta_deg)
    return r0 * (math.cos(th) * e1 - math.sin(th) * e2)


def coplanar_transfer(r_moon_km, v_moon_km_s, tof_days: float,
                      params: TransferParams = DEFAULT_PARAMS) -> TransferPoint:
    """Найкращий (за сумарним Δv) перехід у площині орбіти Місяця за час tof_days.

    r_moon_km, v_moon_km_s — геоцентричний стан Місяця в момент прибуття (ICRF).
    """
    if tof_days <= 0:
        raise ValueError("Час перельоту має бути додатним")
    r_m = np.asarray(r_moon_km, dtype=float)
    v_m = np.asarray(v_moon_km_s, dtype=float)
    e1, e2, h_hat = _transfer_plane(r_m, v_m)
    r0 = R_EARTH_KM + params.parking_altitude_km
    v_circ = circular_speed_km_s(r0)
    tof_s = tof_days * 86400.0

    def evaluate(theta_deg: float):
        r1 = _departure_point(theta_deg, r0, e1, e2)
        v1, v2 = lambert(r1, r_m, tof_s, normal=h_hat)
        dv_tli = float(np.linalg.norm(v1 - v_circ * np.cross(h_hat, r1 / r0)))
        v_inf = float(np.linalg.norm(v2 - v_m))
        total = 1000.0 * dv_tli + float(loi_dv_m_s(v_inf, params.llo_altitude_km))
        return total, dv_tli, v_inf, v1

    # грубий перебір кута, потім уточнення золотим перетином
    grid = np.append(np.arange(params.min_angle_deg, params.max_angle_deg, 2.0), params.max_angle_deg)
    totals = []
    for th in grid:
        try:
            totals.append(evaluate(float(th))[0])
        except ValueError:
            totals.append(math.inf)
    k = int(np.argmin(totals))
    if not math.isfinite(totals[k]):
        raise ValueError("Не знайдено переходу за заданий час")
    lo = float(grid[max(k - 1, 0)])
    hi = float(grid[min(k + 1, len(grid) - 1)])
    phi = (math.sqrt(5) - 1) / 2
    for _ in range(40):
        a = hi - phi * (hi - lo)
        b = lo + phi * (hi - lo)
        if evaluate(a)[0] <= evaluate(b)[0]:
            hi = b
        else:
            lo = a
    theta = (lo + hi) / 2
    total, dv_tli, v_inf, v1 = evaluate(theta)
    c3 = float(v1 @ v1) - 2 * GM_EARTH / r0
    return TransferPoint(
        tof_days=float(tof_days),
        departure_utc=None,
        arrival_utc=None,
        dv_tli_m_s=1000.0 * dv_tli,
        c3_km2_s2=c3,
        v_inf_km_s=v_inf,
        dv_loi_m_s=total - 1000.0 * dv_tli,
        dv_total_m_s=total,
        transfer_angle_deg=theta,
        moon_distance_km=float(np.linalg.norm(r_m)),
        min_parking_inclination_deg=abs(_declination_deg(r_m)),
    )


def transfer_arc(r_moon_km, v_moon_km_s, tof_days: float, params: TransferParams = DEFAULT_PARAMS,
                 n: int = 96) -> tuple[TransferPoint, np.ndarray]:
    """Найкращий перехід і n точок його дуги (ICRF, геоцентрично, км) від паркувальної орбіти до центру Місяця.

    Дуга — оскулюючий еліпс після TLI (задача двох тіл), від точки відльоту до точки прибуття за рухом. Для показу
    в 3D (задача G9, П-5); ділянку виведення на паркувальну орбіту не показуємо.
    """
    if n < 2:
        raise ValueError("Потрібно щонайменше 2 точки")
    point = coplanar_transfer(r_moon_km, v_moon_km_s, tof_days, params)
    r_m = np.asarray(r_moon_km, dtype=float)
    e1, e2, h_hat = _transfer_plane(r_m, np.asarray(v_moon_km_s, dtype=float))
    r1 = _departure_point(point.transfer_angle_deg, R_EARTH_KM + params.parking_altitude_km, e1, e2)
    v1, _ = lambert(r1, r_m, tof_days * 86400.0, normal=h_hat)
    orbit = osculating_orbit(r1, v1, GM_EARTH)  # перехід 3–5 діб — еліпс (C3 < 0); гіпербола — ValueError
    nu1 = math.atan2(float(r1 @ orbit.q_hat), float(r1 @ orbit.p_hat))
    nu2 = math.atan2(float(r_m @ orbit.q_hat), float(r_m @ orbit.p_hat))
    if nu2 <= nu1:
        nu2 += 2 * math.pi
    nu = np.linspace(nu1, nu2, n)
    points = orbit.radius(nu)[:, None] * (np.cos(nu)[:, None] * orbit.p_hat + np.sin(nu)[:, None] * orbit.q_hat)
    return point, points


# --- з ефемеридами ---------------------------------------------------------------------------------------------


def _utc(when: datetime) -> datetime:
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


def moon_state_icrf(eph, when: datetime) -> tuple[np.ndarray, np.ndarray]:
    """Геоцентричні положення (км) і швидкість (км/с) Місяця в ICRF з ефемериди (app.core.ephemeris.Ephemeris)."""
    state = (eph.moon - eph.earth).at(eph.time(_utc(when)))
    return np.asarray(state.position.km, dtype=float), np.asarray(state.velocity.km_per_s, dtype=float)


def dv_curve(eph, departure: datetime, tof_days, params: TransferParams = DEFAULT_PARAMS) -> list[TransferPoint]:
    """Крива «паливо ↔ час»: для кожного часу перельоту — Δv і дата прибуття при старті (TLI) у departure."""
    dep = _utc(departure)
    points = []
    for tof in np.atleast_1d(np.asarray(tof_days, dtype=float)):
        arrival = dep + timedelta(days=float(tof))
        r_m, v_m = moon_state_icrf(eph, arrival)
        p = coplanar_transfer(r_m, v_m, float(tof), params)
        points.append(_with_dates(p, dep, arrival))
    return points


def _with_dates(p: TransferPoint, departure: datetime, arrival: datetime) -> TransferPoint:
    d = p.to_dict()
    d.update(departure_utc=departure.replace(microsecond=0), arrival_utc=arrival.replace(microsecond=0))
    return TransferPoint(**d)


def _span(values) -> Range:
    vals = list(values)
    return (float(min(vals)), float(max(vals)))


def transfer_options(eph, departure: datetime, params: TransferParams = DEFAULT_PARAMS,
                     step_days: float = 0.25) -> dict[str, TransferOption]:
    """Прямий (розрахунок) і економний (оцінка) варіанти для старту в departure."""
    dep = _utc(departure)
    t_min, t_max = TRAJECTORIES["direct"]["duration_days"]
    curve = dv_curve(eph, dep, np.arange(t_min, t_max + 1e-9, step_days), params)
    best = min(curve, key=lambda p: p.dv_total_m_s)
    direct = TransferOption(
        trajectory="direct",
        name=TRAJECTORIES["direct"]["name"],
        method="patched_conic",
        duration_days=(t_min, t_max),
        arrival_utc=(curve[0].arrival_utc, curve[-1].arrival_utc),
        dv_tli_m_s=_span(p.dv_tli_m_s for p in curve),
        dv_loi_m_s=_span(p.dv_loi_m_s for p in curve),
        dv_total_m_s=_span(p.dv_total_m_s for p in curve),
        best=best,
    )
    le_min, le_max = TRAJECTORIES["low_energy"]["duration_days"]
    save_min, save_max = LOW_ENERGY_DV_SAVING_M_S
    low_energy = TransferOption(
        trajectory="low_energy",
        name=TRAJECTORIES["low_energy"]["name"],
        method="estimate",
        duration_days=(le_min, le_max),
        arrival_utc=((dep + timedelta(days=le_min)).replace(microsecond=0),
                     (dep + timedelta(days=le_max)).replace(microsecond=0)),
        dv_tli_m_s=None,
        dv_loi_m_s=None,
        dv_total_m_s=(best.dv_total_m_s - save_max, best.dv_total_m_s - save_min),
        best=None,
    )
    return {"direct": direct, "low_energy": low_energy}
