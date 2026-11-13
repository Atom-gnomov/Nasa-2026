"""Оскулююча (миттєва) кеплерівська орбіта з вектора стану (docs/MATH.md, задача двох тіл).

Оскулююча орбіта — еліпс, яким тіло рухалося б, якби зникли всі збурення, крім тяжіння
центрального тіла. Він точно проходить через поточне положення тіла з поточною швидкістю.
Справжній шлях відхиляється від нього через збурення (для Місяця — головно від Сонця);
величину відхилення рахує app.services.system.orbits.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Гравітаційні параметри JPL DE440, км³/с² (Park et al. 2021, табл. 8)
GM_SUN = 132_712_440_041.279419
GM_EARTH = 398_600.435507
GM_MOON = 4_902.800118

ECLIPTIC_POLE_ICRF = np.array([0.0, -np.sin(np.radians(23.4392911)), np.cos(np.radians(23.4392911))])


@dataclass(frozen=True)
class Orbit:
    a_km: float
    e: float
    inclination_deg: float  # до площини екліптики J2000
    period_days: float
    periapsis_km: float
    apoapsis_km: float
    p_hat: np.ndarray  # одиничний вектор на перицентр
    q_hat: np.ndarray  # одиничний вектор у площині орбіти, +90° від перицентру за рухом
    h_hat: np.ndarray  # нормаль до площини орбіти

    def radius(self, nu) -> np.ndarray:
        """Відстань від фокуса за істинною аномалією ν (радіани)."""
        return self.a_km * (1 - self.e**2) / (1 + self.e * np.cos(nu))

    def points(self, n: int = 720) -> np.ndarray:
        """n точок замкненого еліпса (n, 3), км, у тій самій системі, що й вхідний вектор стану."""
        nu = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
        r = self.radius(nu)
        return r[:, None] * (np.cos(nu)[:, None] * self.p_hat + np.sin(nu)[:, None] * self.q_hat)

    def deviation_km(self, positions: np.ndarray) -> np.ndarray:
        """Відстань справжніх положень (N, 3) від еліпса: у площині — по радіусу, плюс поза площиною."""
        pos = np.atleast_2d(positions)
        out_of_plane = pos @ self.h_hat
        x, y = pos @ self.p_hat, pos @ self.q_hat
        nu = np.arctan2(y, x)
        in_plane = np.hypot(x, y) - self.radius(nu)
        return np.hypot(in_plane, out_of_plane)


def osculating_orbit(r_km, v_km_s, mu: float) -> Orbit:
    """Кеплерівські елементи з вектора стану (r, v) відносно центрального тіла."""
    r = np.asarray(r_km, dtype=float)
    v = np.asarray(v_km_s, dtype=float)
    rn, v2 = np.linalg.norm(r), float(v @ v)
    h = np.cross(r, v)
    h_hat = h / np.linalg.norm(h)
    e_vec = ((v2 - mu / rn) * r - (r @ v) * v) / mu
    e = float(np.linalg.norm(e_vec))
    a = 1.0 / (2.0 / rn - v2 / mu)
    if not (0.0 <= e < 1.0 and a > 0):
        raise ValueError("Орбіта не еліптична")
    p_hat = e_vec / e if e > 1e-12 else r / rn
    q_hat = np.cross(h_hat, p_hat)
    inc = float(np.degrees(np.arccos(np.clip(h_hat @ ECLIPTIC_POLE_ICRF, -1.0, 1.0))))
    period = 2 * np.pi * np.sqrt(a**3 / mu) / 86400.0
    return Orbit(a, e, inc, period, a * (1 - e), a * (1 + e), p_hat, q_hat, h_hat)
