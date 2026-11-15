"""Розгінні ділянки польоту з урахуванням маси завантаження (задача G16; docs/MATH.md, §20).

Швидкість на пасивній ділянці після розгону задається енергією орбіти (Δv), а не масою апарата. Від маси залежать:
скільки палива потрібно, **прискорення й тривалість розгону** при заданій тязі, чи вміщується вантаж у ракету.
Тяга розгінного ступеня тут — частка ваги його повного завантаження: F = tw · g₀ · місткість_НОО (тяга розрахована
на ракету, тож легший вантаж розганяється з більшим прискоренням, важчий — повільніше). Прискорення обмежене
`max_g` (пілотована — менше). Тривалість із рівняння Ціолковського: t = m_пал · Isp · g₀ / F.

⚠️ Усі коефіцієнти (tw, Isp, обмеження перевантаження) — тимчасові орієнтовні значення. Чисті функції без Flask.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G0 = 9.80665


@dataclass(frozen=True)
class BurnParams:
    tli_tw: float = 0.35  # тяга розгінного ступеня / вага повного завантаження (місткість НОО) ⚠️ тимчасово
    max_g_robotic: float = 4.0  # обмеження прискорення, g
    max_g_crewed: float = 3.0


DEFAULT_PARAMS = BurnParams()


def burn(mass_start_kg: float, dv_m_s: float, isp_s: float, thrust_n: float) -> dict:
    """Розгін при сталій тязі: витрата палива, час, прискорення на початку й наприкінці (м/с² і g)."""
    if min(mass_start_kg, dv_m_s, isp_s, thrust_n) <= 0:
        raise ValueError("mass_start_kg, dv_m_s, isp_s і thrust_n мають бути додатними")
    ve = isp_s * G0
    mass_end = mass_start_kg * math.exp(-dv_m_s / ve)
    propellant = mass_start_kg - mass_end
    duration = propellant * ve / thrust_n
    a0, a1 = thrust_n / mass_start_kg, thrust_n / mass_end
    return {"mass_start_kg": mass_start_kg, "mass_end_kg": mass_end, "propellant_kg": propellant,
            "duration_s": duration, "thrust_n": thrust_n, "accel_start_m_s2": a0, "accel_end_m_s2": a1,
            "accel_start_g": a0 / G0, "accel_end_g": a1 / G0, "dv_m_s": dv_m_s, "isp_s": isp_s}


def tli_burn(mass_leo_kg: float, capacity_leo_kg: float, dv_m_s: float, isp_s: float, crewed: bool = False,
             params: BurnParams = DEFAULT_PARAMS) -> dict:
    """Розгін до Місяця (TLI) для маси на НОО й місткості ракети. Якщо вантаж більший за місткість — кілька пусків
    (маса на пуск), `overloaded: true`, попередження. Тяга зменшується, щоб не перевищити обмеження прискорення."""
    if mass_leo_kg <= 0 or capacity_leo_kg <= 0:
        raise ValueError("mass_leo_kg і capacity_leo_kg мають бути додатними")
    utilization = mass_leo_kg / capacity_leo_kg
    launches = max(1, math.ceil(utilization - 1e-9))
    per_launch = mass_leo_kg / launches
    max_g = params.max_g_crewed if crewed else params.max_g_robotic
    thrust = min(params.tli_tw * G0 * capacity_leo_kg, max_g * G0 * per_launch)
    out = burn(per_launch, dv_m_s, isp_s, thrust)
    warnings = []
    if utilization > 1.0:
        text = (f"Вантаж на НОО ({mass_leo_kg:,.0f} кг) більший за місткість ракети ({capacity_leo_kg:,.0f} кг): "
                f"потрібно {launches} пуски/пусків або більша ракета")
        warnings.append(text.replace(",", " "))
    elif utilization > 0.9:
        warnings.append("Ракета заповнена понад 90 %: майже немає запасу маси")
    if out["accel_end_g"] > max_g + 1e-9:
        out["accel_end_g"] = max_g  # наприкінці розгону тягу дроселюють
    return {**out, "utilization": utilization, "launches": launches, "overloaded": utilization > 1.0,
            "max_g": max_g, "warnings": warnings}
