"""Дослідницький скрипт: перевірка математики розрахунків (docs/MATH.md).

Обчислює положення Сонця й Землі на небі точки на Місяці та виводить
контрольні числа, на які посилається docs/MATH.md.

Залежності (лише для цього скрипта):
    pip install skyfield numpy naif-de440

Запуск:
    python tools/research/lunar_geometry.py

Орієнтація Місяця — модель IAU WGCCRE 2015 (Archinal et al., 2018).
Для продакшну замінити на PCK DE440 (moon_pa_de440 + кадр MOON_ME), див. docs/MATH.md, §3.
"""

from __future__ import annotations

import numpy as np
from naif_de440 import de440
from skyfield.api import load, wgs84

R_MOON_KM = 1737.4
R_SUN_KM = 695_700.0
R_EARTH_KM = 6378.137
C_KM_S = 299_792.458
AU_KM = 149_597_870.7
SOLAR_CONSTANT_W_M2 = 1361.0

ts = load.timescale(builtin=True)
eph = load(de440)
SUN, EARTH, MOON = eph["sun"], eph["earth"], eph["moon"]


# --- §3. Орієнтація Місяця: модель IAU 2015 -----------------------------------
def iau_moon_angles(tdb_jd: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Повертає (alpha0, delta0, W) у радіанах для моменту(ів) TDB."""
    d = tdb_jd - 2451545.0
    T = d / 36525.0
    E = np.radians(np.array([
        125.045 - 0.0529921 * d,
        250.089 - 0.1059842 * d,
        260.008 + 13.0120009 * d,
        176.625 + 13.3407154 * d,
        357.529 + 0.9856003 * d,
        311.589 + 26.4057084 * d,
        134.963 + 13.0649930 * d,
        276.617 + 0.3287146 * d,
        34.226 + 1.7484877 * d,
        15.134 - 0.1589763 * d,
        119.743 + 0.0036096 * d,
        239.961 + 0.1643573 * d,
        25.053 + 12.9590088 * d,
    ]))
    s, c = np.sin(E), np.cos(E)
    a0 = (269.9949 + 0.0031 * T - 3.8787 * s[0] - 0.1204 * s[1] + 0.0700 * s[2]
          - 0.0172 * s[3] + 0.0072 * s[5] - 0.0052 * s[9] + 0.0043 * s[12])
    d0 = (66.5392 + 0.0130 * T + 1.5419 * c[0] + 0.0239 * c[1] - 0.0278 * c[2]
          + 0.0068 * c[3] - 0.0029 * c[5] + 0.0009 * c[6] + 0.0008 * c[9] - 0.0009 * c[12])
    W = (38.3213 + 13.17635815 * d - 1.4e-12 * d**2 + 3.5610 * s[0] + 0.1208 * s[1]
         - 0.0642 * s[2] + 0.0158 * s[3] + 0.0252 * s[4] - 0.0066 * s[5] - 0.0047 * s[6]
         - 0.0046 * s[7] + 0.0028 * s[8] + 0.0052 * s[9] + 0.0040 * s[10]
         + 0.0019 * s[11] - 0.0044 * s[12])
    return np.radians(a0), np.radians(d0), np.radians(W)


def icrf_to_moon_fixed(tdb_jd: np.ndarray) -> np.ndarray:
    """Матриці повороту ICRF → тіло Місяця, форма (3, 3, N). M = Rz(W)·Rx(90°−δ0)·Rz(90°+α0)."""
    a0, d0, W = iau_moon_angles(np.atleast_1d(tdb_jd))

    def rz(t):
        c, s = np.cos(t), np.sin(t)
        z, o = np.zeros_like(t), np.ones_like(t)
        return np.array([[c, s, z], [-s, c, z], [z, z, o]])

    def rx(t):
        c, s = np.cos(t), np.sin(t)
        z, o = np.zeros_like(t), np.ones_like(t)
        return np.array([[o, z, z], [z, c, s], [z, -s, c]])

    a, b, w = rz(np.pi / 2 + a0), rx(np.pi / 2 - d0), rz(W)
    return np.einsum("ijn,jkn,kln->iln", w, b, a)


# --- §4–5. Координати точки і топоцентрична система ----------------------------
def site_vector(lat_deg: float, lon_deg: float, height_km: float = 0.0) -> np.ndarray:
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    r = R_MOON_KM + height_km
    return r * np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


def enu_basis(lat_deg: float, lon_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Орти East, North, Up. На самому полюсі «північ» = напрямок на меридіан lon_deg."""
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    east = np.array([-np.sin(lon), np.cos(lon), 0.0])
    north = np.cross(up, east)
    return east, north, up


def sky_positions(lat: float, lon: float, t, height_km: float = 0.0):
    """Азимут/кут місця/відстань Сонця й Землі з точки на Місяці (масив моментів t)."""
    M = icrf_to_moon_fixed(t.tdb)
    moon = MOON.at(t)
    sun_rel = moon.observe(SUN).position.km           # з поправкою на час світла (~8,3 хв)
    earth_rel = (EARTH.at(t).position.km - moon.position.km)  # час світла 1,3 с — нехтуємо
    site_bf = site_vector(lat, lon, height_km)
    e, n, u = enu_basis(lat, lon)
    out = {}
    for name, rel in (("sun", sun_rel), ("earth", earth_rel)):
        bf = np.einsum("ijn,jn->in", M, rel) - site_bf[:, None]  # топоцентричний вектор
        dist = np.linalg.norm(bf, axis=0)
        dhat = bf / dist
        el = np.degrees(np.arcsin(np.clip(u @ dhat, -1, 1)))
        az = np.degrees(np.arctan2(e @ dhat, n @ dhat)) % 360
        out[name] = (az, el, dist)
    return out


# --- §6. Частка сонячного диска над горизонтом --------------------------------
def disk_fraction_above(el_deg, horizon_deg, radius_deg):
    """Точна частка площі диска над прямою лінією горизонту (сегмент круга)."""
    h = np.clip((np.asarray(el_deg) - horizon_deg) / radius_deg, -1, 1)
    return 1 - (np.arccos(h) - h * np.sqrt(1 - h * h)) / np.pi


def main() -> None:
    hours = np.arange(0, 24 * 365.25 * 2, 1.0)  # 2027–2028, крок 1 год
    t = ts.utc(2027, 1, 1, hours)

    print("== Лібрація: підземна точка Землі (sub-Earth point), 2027–2028 ==")
    M = icrf_to_moon_fixed(t.tdb)
    moon = MOON.at(t)
    for name, rel in (("Земля", EARTH.at(t).position.km - moon.position.km),
                      ("Сонце", moon.observe(SUN).position.km)):
        bf = np.einsum("ijn,jn->in", M, rel)
        lat = np.degrees(np.arcsin(bf[2] / np.linalg.norm(bf, axis=0)))
        lon = np.degrees(np.arctan2(bf[1], bf[0]))
        if name == "Земля":
            print(f"  {name}: широта {lat.min():+.2f}…{lat.max():+.2f}°, довгота {lon.min():+.2f}…{lon.max():+.2f}°")
        else:
            print(f"  {name}: широта підсонячної точки {lat.min():+.2f}…{lat.max():+.2f}°")

    d_earth = np.linalg.norm(EARTH.at(t).position.km - moon.position.km, axis=0)
    print("\n== Відстань і затримка сигналу ==")
    print(f"  центр–центр: {d_earth.min():,.0f}…{d_earth.max():,.0f} км")
    print(f"  затримка в один бік: {d_earth.min() / C_KM_S:.3f}…{d_earth.max() / C_KM_S:.3f} с")

    print("\n== Кутові розміри ==")
    sun_dist = np.linalg.norm(moon.observe(SUN).position.km, axis=0)
    print(f"  радіус диска Сонця: {np.degrees(np.arcsin(R_SUN_KM / sun_dist)).min():.4f}…"
          f"{np.degrees(np.arcsin(R_SUN_KM / sun_dist)).max():.4f}°")
    print(f"  радіус диска Землі: {np.degrees(np.arcsin(R_EARTH_KM / d_earth)).min():.3f}…"
          f"{np.degrees(np.arcsin(R_EARTH_KM / d_earth)).max():.3f}°")
    print(f"  сонячна стала біля Місяця: {(SOLAR_CONSTANT_W_M2 * (AU_KM / sun_dist) ** 2).min():.0f}…"
          f"{(SOLAR_CONSTANT_W_M2 * (AU_KM / sun_dist) ** 2).max():.0f} Вт/м²")

    print("\n== Гладка сфера (без рельєфу): кути й частка часу над горизонтом ==")
    print("  точка                    Сонце, кут місця     Сонце >0   Земля, кут місця     Земля >0")
    for lat, lon, label in [(-90, 0, "південний полюс"), (-89.5, 0, "89,5° пд. ш., 0°"),
                            (-89.5, 180, "89,5° пд. ш., 180°"), (-85, 0, "85° пд. ш., 0°"),
                            (-85, 180, "85° пд. ш., 180° (зворотний бік)"), (0.67, 23.47, "Apollo 11")]:
        p = sky_positions(lat, lon, t)
        se, ee = p["sun"][1], p["earth"][1]
        print(f"  {label:<32} {se.min():+6.2f}…{se.max():+6.2f}°  {np.mean(se > 0):6.1%}"
              f"   {ee.min():+6.2f}…{ee.max():+6.2f}°  {np.mean(ee > 0):6.1%}")

    print("\n== Швидкість руху Сонця по небу полюса ==")
    p = sky_positions(-89.5, 0, t)
    daz = np.abs((np.diff(p["sun"][0]) + 180) % 360 - 180)
    print(f"  азимут Сонця: {np.median(daz):.3f}°/год (≈ 360° за {360 / np.median(daz) / 24:.1f} доби)")
    print(f"  кут місця Сонця: до {np.abs(np.diff(p['sun'][1])).max():.4f}°/год")
    print(f"  кут місця Землі: до {np.abs(np.diff(p['earth'][1])).max():.4f}°/год")

    print("\n== Пониження геометричного горизонту для висоти щогли h ==")
    for h_m in (1, 2, 5, 10, 100):
        h = h_m / 1000
        dip = np.degrees(np.arccos(R_MOON_KM / (R_MOON_KM + h)))
        print(f"  h = {h_m:>3} м: пониження {dip:.3f}°, дальність горизонту {np.sqrt(2 * R_MOON_KM * h):.1f} км")

    print("\n== Сегмент диска: перевірка формули ==")
    for k in (-1, -0.5, 0, 0.5, 1):
        print(f"  центр на {k:+.1f} радіуса від горизонту → видно {disk_fraction_above(k, 0, 1):.3f} площі")

    print("\n== Схилення Місяця відносно екватора Землі (для запусків), 2026–2045 ==")
    t20 = ts.utc(2026, 1, np.arange(0, 365.25 * 20, 0.25))
    dec = EARTH.at(t20).observe(MOON).radec()[1].degrees
    years = 2026 + np.arange(t20.tt.size) * 0.25 / 365.25
    for y in range(2026, 2046, 2):
        m = (years >= y) & (years < y + 1)
        print(f"  {y}: макс. |схилення| {np.abs(dec[m]).max():.1f}°")

    print("\n== Видимість Місяця зі станцій DSN (кут місця > 10°), 2027 ==")
    t1 = ts.utc(2027, 1, 1, np.arange(0, 24 * 365, 0.25))
    above = []
    for name, lat, lon, h in [("Goldstone", 35.4259, -116.8895, 1002), ("Madrid", 40.4313, -4.2480, 865),
                              ("Canberra", -35.4024, 148.9813, 689)]:
        alt = (EARTH + wgs84.latlon(lat, lon, h)).at(t1).observe(MOON).apparent().altaz()[0].degrees
        above.append(alt > 10)
        print(f"  {name:<10} Місяць вище 10°: {np.mean(alt > 10):5.1%} часу")
    print(f"  хоча б одна станція: {np.mean(np.any(above, axis=0)):5.1%} часу")

    print("\n== Прибавка швидкості від обертання Землі ==")
    for name, lat in [("Куру", 5.2), ("Шрихарикота", 13.7), ("Канаверал", 28.5), ("Байконур", 45.9),
                      ("Восточний", 51.9), ("Екватор (морська платформа)", 0.0)]:
        v = 465.1 * np.cos(np.radians(lat))
        print(f"  {name:<28} {lat:5.1f}° → {v:5.1f} м/с; мін. нахил орбіти {lat:.1f}°")


if __name__ == "__main__":
    main()
