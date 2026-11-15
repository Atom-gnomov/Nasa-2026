"""Склад екіпажу за ролями й план підготовки (M27; дані — app/data/crew_roles.json).

Чисті функції без Flask. Правила складу й години підготовки — ⚠️ тимчасові (див. поле `provisional` даних).
Роль задає типову активність людини (від неї залежать потреби в енергії, O₂, воді й їжі), якщо активність не вказана.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence


def role_ids(data: Mapping) -> list[str]:
    return [r["id"] for r in data["roles"]]


def role(data: Mapping, role_id: str) -> Mapping:
    for r in data["roles"]:
        if r["id"] == role_id:
            return r
    raise ValueError(f"role: допустимо {', '.join(role_ids(data))}")


def composition(roles: Sequence[str], data: Mapping) -> dict:
    """Перевірка складу: яких ролей бракує за правилами й що радимо додати. Порожній список — місія без людей."""
    known = set(role_ids(data))
    bad = sorted(set(roles) - known)
    if bad:
        raise ValueError(f"Невідомі ролі: {', '.join(bad)} (є {', '.join(role_ids(data))})")
    n = len(roles)
    have = Counter(roles)
    needed: list[str] = []
    for rule in data["composition_rules"]:
        if n >= rule["min_crew"]:
            needed = rule["require"]
    missing = [r for r in needed if not have[r]]
    advice = [{"role": r["role"], "reason": r["reason"]} for r in data["recommend"]
              if n >= r["min_crew"] and not have[r["role"]]]
    return {"crew": n, "roles": dict(have), "required": needed, "missing": missing, "ok": not missing,
            "recommended": advice}


def training_plan(roles: Sequence[str], data: Mapping) -> dict:
    """План підготовки (human-rating): модулі кожної ролі з годинами; усього годин на людину й на екіпаж."""
    modules = {m["id"]: m for m in data["training_modules"]}
    people = []
    total = 0.0
    for r in roles:
        mods = [modules[m] for m in role(data, r)["training"]]
        hours = float(sum(m["hours"] for m in mods))
        total += hours
        people.append({"role": r, "hours": hours, "modules": [m["id"] for m in mods]})
    shared = Counter(m for p in people for m in p["modules"])
    return {"people": people, "total_hours": total, "modules": [
        {"id": m["id"], "name": m["name"], "name_en": m.get("name_en"), "hours": m["hours"],
         "people": shared[m["id"]]}
        for m in data["training_modules"] if shared[m["id"]]]}
