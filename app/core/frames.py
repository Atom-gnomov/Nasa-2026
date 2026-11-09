"""Системи координат (docs/MATH.md, розділи 3–5).

Позначення:
    lat, lon  — селенографічні широта/довгота, градуси (південь і захід — від'ємні)
    вектори   — масиви форми (..., 3)
    ME        — система Місяця Mean Earth / Polar axis (у ній задані карти LOLA)
"""

from __future__ import annotations

import numpy as np

from app.core.constants import J2000_JD, R_MOON_KM

# Аргументи E1…E13 моделі IAU 2015: (зсув, швидкість), градуси та градуси/добу.
_IAU_E = np.array([
    (125.045, -0.0529921), (250.089, -0.1059842), (260.008, 13.0120009),
    (176.625, 13.3407154), (357.529, 0.9856003), (311.589, 26.4057084),
    (134.963, 13.0649930), (276.617, 0.3287146), (34.226, 1.7484877),
    (15.134, -0.1589763), (119.743, 0.0036096), (239.961, 0.1643573),
    (25.053, 12.9590088),
])
# Коефіцієнти при sin/cos E1…E13 для α0 (sin), δ0 (cos), W (sin).
_A0 = np.array([-3.8787, -0.1204, 0.0700, -0.0172, 0.0, 0.0072, 0.0, 0.0, 0.0, -0.0052, 0.0, 0.0, 0.0043])
_D0 = np.array([1.5419, 0.0239, -0.0278, 0.0068, 0.0, -0.0029, 0.0009, 0.0, 0.0, 0.0008, 0.0, 0.0, -0.0009])
_W = np.array([3.5610, 0.1208, -0.0642, 0.0158, 0.0252, -0.0066, -0.0047, -0.0046, 0.0028, 0.0052,
               0.0040, 0.0019, -0.0044])


def iau_moon_angles(tdb_jd) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Кути орієнтації Місяця IAU 2015 (Archinal et al., 2018): α0, δ0, W у радіанах."""
    d = np.asarray(tdb_jd, dtype=float) - J2000_JD
    T = d / 36525.0
    E = np.radians(_IAU_E[:, 0, None] + _IAU_E[:, 1, None] * np.atleast_1d(d)[None, :])
    s, c = np.sin(E), np.cos(E)
    a0 = 269.9949 + 0.0031 * T + _A0 @ s
    d0 = 66.5392 + 0.0130 * T + _D0 @ c
    W = 38.3213 + 13.17635815 * d - 1.4e-12 * d**2 + _W @ s
    shape = np.shape(d)
    return (np.radians(a0).reshape(shape), np.radians(d0).reshape(shape), np.radians(W).reshape(shape))


def _rot_z(t: np.ndarray) -> np.ndarray:
    c, s = np.cos(t), np.sin(t)
    z, o = np.zeros_like(t), np.ones_like(t)
    return np.stack([np.stack([c, s, z], -1), np.stack([-s, c, z], -1), np.stack([z, z, o], -1)], -2)


def _rot_x(t: np.ndarray) -> np.ndarray:
    c, s = np.cos(t), np.sin(t)
    z, o = np.zeros_like(t), np.ones_like(t)
    return np.stack([np.stack([o, z, z], -1), np.stack([z, c, s], -1), np.stack([z, -s, c], -1)], -2)


def icrf_to_moon_me(tdb_jd) -> np.ndarray:
    """Матриця(і) повороту ICRF → Місяць (≈ME), форма (..., 3, 3).

    M = Rz(W) · Rx(90° − δ0) · Rz(90° + α0);  r_тіло = M @ r_ICRF.
    Точність моделі IAU ~0,01° — достатньо для метрик 0,1° (docs/MATH.md, §3, §15).
    """
    a0, d0, W = iau_moon_angles(tdb_jd)
    return _rot_z(W) @ _rot_x(np.pi / 2 - d0) @ _rot_z(np.pi / 2 + a0)


def rotate(matrices: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    """Застосовує матриці (..., 3, 3) до векторів (..., 3)."""
    return np.einsum("...ij,...j->...i", matrices, vectors)


def latlon_to_vector(lat, lon, radius=1.0) -> np.ndarray:
    """Селенографічні координати → декартовий вектор (..., 3)."""
    la, lo = np.radians(lat), np.radians(lon)
    r = np.asarray(radius, dtype=float)
    return np.stack([r * np.cos(la) * np.cos(lo), r * np.cos(la) * np.sin(lo), r * np.sin(la)], -1)


def vector_to_latlon(v) -> tuple[np.ndarray, np.ndarray]:
    """Декартовий вектор → (широта, довгота) у градусах; довгота в [−180, 180)."""
    v = np.asarray(v, dtype=float)
    r = np.linalg.norm(v, axis=-1)
    lat = np.degrees(np.arcsin(np.clip(v[..., 2] / r, -1, 1)))
    lon = (np.degrees(np.arctan2(v[..., 1], v[..., 0])) + 180) % 360 - 180
    return lat, lon


def site_vector(lat: float, lon: float, height_m: float = 0.0, radius_km: float = R_MOON_KM) -> np.ndarray:
    """Положення точки на поверхні (км) у системі ME; height_m — рельєф + щогла."""
    return latlon_to_vector(lat, lon, radius_km + height_m / 1000.0)


def enu_basis(lat: float, lon: float) -> np.ndarray:
    """Орти East, North, Up як рядки матриці 3×3.

    На самому полюсі «північ» не визначена; тут вона береться як напрямок на меридіан `lon`
    (grid north). Тому для полюса азимут залежить від переданої довготи — див. docs/MATH.md, §5.
    """
    la, lo = np.radians(lat), np.radians(lon)
    up = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    east = np.array([-np.sin(lo), np.cos(lo), 0.0])
    north = np.cross(up, east)
    return np.stack([east, north, up])


def azel(directions: np.ndarray, basis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Азимут (від півночі за годинниковою, 0–360) і кут місця, градуси, для векторів (..., 3)."""
    d = np.asarray(directions, dtype=float)
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    e, n, u = (d @ basis[0], d @ basis[1], d @ basis[2])
    el = np.degrees(np.arcsin(np.clip(u, -1, 1)))
    az = np.degrees(np.arctan2(e, n)) % 360
    return az, el
