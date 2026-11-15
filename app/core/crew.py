"""Модель екіпажу й запасів (задача M24; docs/RESOURCES.md §10; docs/MATH.md, §20).

Кожна людина має стать, вік, масу, зріст і рівень активності. Від них рахується добова потреба в енергії (рівняння
EER, NASA-STD-3001 Vol.2 Table 7.1-1; коефіцієнти — рівняння IOM DRI 2005, ⚠️ точні коефіцієнти таблиці NASA не звірено),
а O₂, CO₂, питна вода й їжа — пропорційно до енергії (коефіцієнти звірено з BVAD NASA/TP-2015-218570 Rev2, Table 3-31:
3 035 ккал → 0,892 кг O₂ проти 0,895 кг у BVAD). Із цього — запаси на місію з рекомендованим резервом, журнал розходу
по добах (відсоток залишку кожного запасу) і попередження про нестачу.

⚠️ Резерв за замовчуванням (15 %) і еталонні профілі — тимчасові значення, не нормативні. Чисті функції без Flask.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

SEXES = ("male", "female")
# Коефіцієнт фізичної активності PA рівнянь EER (IOM DRI 2005): малорухомий / помірний / активний / дуже активний
ACTIVITY_PA = {
    "male": {"sedentary": 1.0, "low": 1.11, "active": 1.25, "very_active": 1.48},
    "female": {"sedentary": 1.0, "low": 1.12, "active": 1.27, "very_active": 1.45},
}
ACTIVITIES = tuple(ACTIVITY_PA["male"])
SUPPLIES = ("oxygen", "water", "food")  # запаси, які везуть і витрачають (CO₂ лише рахується)
LIMITS = {"age": (19.0, 80.0), "mass_kg": (35.0, 160.0), "height_m": (1.40, 2.15)}
MAX_DAYS = 365.0


@dataclass(frozen=True)
class CrewParams:
    """⚠️ Коефіцієнти перерахунку енергії в потреби (див. модуль) і резерв за замовчуванням."""

    o2_kg_per_kcal: float = 0.000294  # RQ ≈ 0,87; 3 035 ккал → 0,892 кг (BVAD: 0,895)
    co2_kg_per_kcal: float = 0.000353
    water_kg_per_kcal: float = 0.001  # ≈ 1 мл питної води на ккал
    food_kg_per_kcal: float = 1.0 / 3790.0  # суха їжа без упаковки: 0,8 кг на 3 035 ккал
    packaging_factor: float = 2.99  # 2,39 кг із упаковкою / 0,8 кг без упаковки (ISS)
    reserve_fraction: float = 0.15  # рекомендований запас понад потребу ⚠️ тимчасово


DEFAULT_PARAMS = CrewParams()


@dataclass(frozen=True)
class CrewMember:
    sex: str
    mass_kg: float
    height_m: float
    age: float = 35.0
    activity: str = "active"


# Еталонні профілі для підстановки за замовчуванням ⚠️ (не нормативні)
REFERENCE = {
    "male": CrewMember("male", 82.0, 1.78),
    "female": CrewMember("female", 62.0, 1.65),
}


def parse_member(raw: Mapping) -> CrewMember:
    """Член екіпажу з тіла запиту; відсутні поля беруться з еталонного профілю статі. ValueError — помилка даних."""
    if not isinstance(raw, Mapping):
        raise ValueError("Кожен член екіпажу має бути об'єктом")
    unknown = set(raw) - {"sex", "age", "mass_kg", "height_m", "activity"}
    if unknown:
        raise ValueError(f"Невідомі поля члена екіпажу: {', '.join(sorted(unknown))}")
    sex = raw.get("sex")
    if sex not in SEXES:
        raise ValueError(f"sex: допустимо {', '.join(SEXES)}")
    ref = REFERENCE[sex]
    activity = raw.get("activity", ref.activity)
    if activity not in ACTIVITIES:
        raise ValueError(f"activity: допустимо {', '.join(ACTIVITIES)}")
    values = {}
    for key in ("age", "mass_kg", "height_m"):
        value = raw.get(key, getattr(ref, key))
        lo, hi = LIMITS[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
            raise ValueError(f"{key} має бути числом у межах {lo:g}…{hi:g}")
        values[key] = float(value)
    return CrewMember(sex=sex, activity=activity, **values)


def energy_kcal(member: CrewMember) -> float:
    """Добова потреба в енергії, ккал: EER = a − b·вік + PA·(c·маса + d·зріст_м) (дорослі від 19 років)."""
    pa = ACTIVITY_PA[member.sex][member.activity]
    if member.sex == "male":
        return 662.0 - 9.53 * member.age + pa * (15.91 * member.mass_kg + 539.6 * member.height_m)
    return 354.0 - 6.91 * member.age + pa * (9.36 * member.mass_kg + 726.0 * member.height_m)


def daily_needs(member: CrewMember, params: CrewParams = DEFAULT_PARAMS) -> dict[str, float]:
    """Добові потреби однієї людини: енергія (ккал) і маси (кг) O₂, CO₂ (утворюється), води, їжі (суха й з упак.)."""
    kcal = energy_kcal(member)
    food = kcal * params.food_kg_per_kcal
    return {
        "energy_kcal": kcal,
        "oxygen_kg": kcal * params.o2_kg_per_kcal,
        "co2_kg": kcal * params.co2_kg_per_kcal,
        "water_kg": kcal * params.water_kg_per_kcal,
        "food_dry_kg": food,
        "food_kg": food * params.packaging_factor,  # те, що везуть: їжа разом з упаковкою
    }


def _check_days(days: float, supply_days: float) -> None:
    for name, value in (("days", days), ("supply_days", supply_days)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= MAX_DAYS:
            raise ValueError(f"{name} має бути числом у межах 0…{MAX_DAYS:g}")


def crew_totals(members: Sequence[CrewMember], params: CrewParams = DEFAULT_PARAMS) -> dict[str, float]:
    """Сумарні добові потреби екіпажу (ключі як у `daily_needs`)."""
    out: dict[str, float] = {}
    for m in members:
        for key, value in daily_needs(m, params).items():
            out[key] = out.get(key, 0.0) + value
    return out


MAX_SUPPLY_KG = 100_000.0  # верхня межа довільного обсягу одного запасу, кг


def _check_supply_kg(supply_kg: Mapping | None) -> dict[str, float]:
    """Довільні обсяги запасів, кг: ключі з SUPPLIES, значення — числа 0…MAX_SUPPLY_KG; відсутні — не задані."""
    if supply_kg is None:
        return {}
    if not isinstance(supply_kg, Mapping):
        raise ValueError("supply_kg має бути об'єктом")
    unknown = set(supply_kg) - set(SUPPLIES)
    if unknown:
        raise ValueError(f"supply_kg: невідомі запаси {', '.join(sorted(unknown))} (є {', '.join(SUPPLIES)})")
    out = {}
    for key, value in supply_kg.items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= MAX_SUPPLY_KG:
            raise ValueError(f"supply_kg.{key} має бути числом у межах 0…{MAX_SUPPLY_KG:g}")
        out[key] = float(value)
    return out


def _resource_rows(per_day: Mapping[str, float], days: float, loaded: Mapping[str, float], reserve: float,
                   custom: Mapping[str, float]) -> dict[str, dict]:
    """По кожному запасу: завезено, потрібно, рекомендовано, на скільки діб вистачить, доба вичерпання, баланс,
    надлишок, нестача."""
    out = {}
    for s in SUPPLIES:
        rate = per_day[_KEY[s]]
        required = rate * days
        recommended = required * (1.0 + reserve)
        covers = loaded[s] / rate if rate > 0 else math.inf
        out[s] = {
            "loaded_kg": loaded[s], "required_kg": required, "recommended_kg": recommended, "rate_kg_per_day": rate,
            "covers_days": covers,
            "runs_out_day": covers if days > 0 and covers < days - 1e-9 else None,  # доба, коли запас закінчиться
            "balance_kg": loaded[s] - required,
            "excess_kg": max(0.0, loaded[s] - recommended),  # понад потребу й рекомендований резерв
            "deficit_kg": max(0.0, required - loaded[s]),
            "custom": s in custom,
        }
    return out


def _summary(rows: Mapping[str, Mapping]) -> dict:
    short = [(r["runs_out_day"], s) for s, r in rows.items() if r["runs_out_day"] is not None]
    first = min(short) if short else None
    return {
        "mission_ok": not short,
        "first_shortage_day": first[0] if first else None,
        "first_shortage_resource": first[1] if first else None,
        "excess_kg": sum(r["excess_kg"] for r in rows.values()),
        "deficit_kg": sum(r["deficit_kg"] for r in rows.values()),
        "critical": bool(short),  # нестача життєзабезпечення — місія не виконується
    }


def supplies_report(members: Sequence[CrewMember], days: float, supply_days: float | None = None,
                    params: CrewParams = DEFAULT_PARAMS, supply_kg: Mapping | None = None) -> dict:
    """Запаси на місію, журнал розходу, баланс по запасах і попередження.

    days — тривалість місії, діб; supply_days — на скільки діб запаси везуть (за замовчуванням — із рекомендованим
    резервом: days·(1 + reserve)). Запаси O₂, води й їжі = добова потреба · supply_days; розхід — потреба · доба.
    supply_kg — довільні обсяги окремих запасів, кг (перекривають supply_days для цих запасів; решта — як зазвичай).
    """
    if not members:
        raise ValueError("Потрібен хоча б один член екіпажу")
    planned = days * (1.0 + params.reserve_fraction) if supply_days is None else supply_days
    _check_days(days, planned)
    custom = _check_supply_kg(supply_kg)
    per_day = crew_totals(members, params)
    recommended_days = days * (1.0 + params.reserve_fraction)
    loaded = {s: custom.get(s, per_day[_KEY[s]] * planned) for s in SUPPLIES}
    required = {s: per_day[_KEY[s]] * days for s in SUPPLIES}
    rows = _resource_rows(per_day, days, loaded, params.reserve_fraction, custom)
    if custom:  # на скільки діб вистачить найменшого запасу — і є «планований» запас місії
        planned = min(r["covers_days"] for r in rows.values())
        if not math.isfinite(planned):
            planned = float(days)
    reserve_pct = (planned - days) / days if days > 0 else None
    warnings = []
    if custom:
        for s, r in rows.items():
            label = SUPPLY_LABELS[s]
            if days > 0 and r["loaded_kg"] < r["required_kg"] - 1e-9:
                warnings.append({"kind": "shortage", "resource": s, "message": (
                    f"{label}: завезено {r['loaded_kg']:.0f} кг, потрібно {r['required_kg']:.0f} кг — "
                    f"запас закінчиться на добі {r['runs_out_day']:.1f} з {days:g}")})
            elif days > 0 and r["loaded_kg"] < r["recommended_kg"] - 1e-9:
                warnings.append({"kind": "low_reserve", "resource": s, "message": (
                    f"{label}: завезено {r['loaded_kg']:.0f} кг — менше за рекомендовані {r['recommended_kg']:.0f} кг "
                    f"(резерв {params.reserve_fraction * 100:.0f} %)")})
    elif days > 0 and planned < days:
        warnings.append({"kind": "shortage", "message": f"Запасів на {planned:g} діб, а місія триває {days:g}: "
                                                       f"нестача {days - planned:g} діб"})
    elif days > 0 and planned < recommended_days - 1e-9:
        warnings.append({"kind": "low_reserve", "message": (
            f"Запас {planned - days:g} діб ({reserve_pct * 100:.0f} %) менший за рекомендований "
            f"{recommended_days - days:g} діб ({params.reserve_fraction * 100:.0f} %)")})
    return {
        "members": [{**asdict(m), "needs_per_day": daily_needs(m, params)} for m in members],
        "per_day": per_day,
        "days": float(days),
        "supply_days": float(planned),
        "recommended_supply_days": recommended_days,
        "reserve_fraction_recommended": params.reserve_fraction,
        "reserve_fraction_planned": reserve_pct,
        "loaded_kg": loaded,
        "required_kg": required,
        "loaded_total_kg": sum(loaded.values()),
        "resources": rows,
        "summary": _summary(rows),
        "warnings": warnings,
        "log": consumption_log(per_day, days, planned, params.reserve_fraction, loaded),
    }


def economics(report: Mapping, usd_per_kg: tuple[float, float]) -> dict:
    """Гроші на запаси (діапазон мін–макс): усе завезене, надлишок понад потребу з резервом і вартість закриття нестачі.

    usd_per_kg — вартість доставки 1 кг запасів на Місяць (cost.delivery_usd_per_kg). Надлишок — «зайві» гроші;
    нестача —
    скільки коштувало б докласти, щоб запасів вистачило. ⚠️ Ціни тимчасові (див. cost.py) — результат provisional."""
    def money(kg: float) -> list[float]:
        return [kg * usd_per_kg[0], kg * usd_per_kg[1]]

    rows = report["resources"]
    return {
        "usd_per_kg": list(usd_per_kg),
        "loaded_usd": money(report["loaded_total_kg"]),
        "excess_kg": report["summary"]["excess_kg"],
        "excess_usd": money(report["summary"]["excess_kg"]),
        "deficit_kg": report["summary"]["deficit_kg"],
        "deficit_usd": money(report["summary"]["deficit_kg"]),
        "by_resource": {s: {"excess_usd": money(r["excess_kg"]), "deficit_usd": money(r["deficit_kg"])}
                        for s, r in rows.items()},
        "provisional": True,
    }


def consumption_log(per_day: Mapping[str, float], days: float, supply_days: float,
                    reserve_fraction: float, loaded_kg: Mapping[str, float] | None = None) -> list[dict]:
    """Журнал розходу: на кінець кожної доби — відсоток залишку кожного запасу від завезеного й стан
    (`ok`; `reserve` — вже витрачається резерв; `shortage` — запас вичерпано). Остання запис — кінець місії."""
    n = int(math.ceil(days))
    out = []
    for day in range(0, n + 1):
        t = min(float(day), days)
        entry: dict = {"day": t, "remaining_pct": {}, "status": {}}
        worst = "ok"
        for s in SUPPLIES:
            rate = per_day[_KEY[s]]
            loaded = rate * supply_days if loaded_kg is None else loaded_kg[s]
            left = loaded - rate * t
            pct = 100.0 * left / loaded if loaded > 0 else 0.0
            entry["remaining_pct"][s] = round(max(pct, 0.0), 1)
            reserve_kg = rate * days * reserve_fraction
            status = "shortage" if left <= 1e-9 else "reserve" if left < reserve_kg - 1e-9 else "ok"
            entry["status"][s] = status
            worst = max(worst, status, key=("ok", "reserve", "shortage").index)
        entry["worst"] = worst
        out.append(entry)
    return out


_KEY = {"oxygen": "oxygen_kg", "water": "water_kg", "food": "food_kg"}
SUPPLY_LABELS = {"oxygen": "Кисень", "water": "Вода", "food": "Їжа"}
