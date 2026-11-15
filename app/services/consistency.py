"""B23: перевірка узгодженості виборів майстра планування місії (П-14, крок 9).

Бере ті самі вибори, що й `POST /api/mission` (склад, навантаження, ракета), і додає дату старту, точку посадки
й тривалість перебування. Нічого не вигадує: пороги — лише з профілю місії (`app/data/mission_thresholds.json`,
через відповідь `/api/mission`), освітлення й зв'язок — з `/api/timeline` на період перебування. Результат —
список конфліктів із серйозністю й номером кроку, який виправити; перевірки, яких не було чим виконати, — у `skipped`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from app.services import mission as mission_service
from app.services import timeline as timeline_service

ALLOWED = {"mission", "datetime", "site", "stay_days", "goal", "name"}
MAX_STAY_DAYS = 365.0
NIGHT_TOLERANCE_H = 1.0  # різниця до години — похибка кроку ряду, не конфлікт


class ConsistencyError(ValueError):
    """Некоректне тіло запиту (400)."""


def _conflict(cid: str, severity: str, step: int, message: str, **values) -> dict:
    out = {"id": cid, "severity": severity, "step": step, "message": message}
    if values:
        out["values"] = values
    return out


def _parse_when(raw) -> datetime | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ConsistencyError("datetime має бути рядком ISO 8601")
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConsistencyError("datetime: невірний формат, очікується ISO 8601") from exc
    return when.astimezone(UTC) if when.tzinfo else when.replace(tzinfo=UTC)


def _parse_site(raw) -> tuple[float, float] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ConsistencyError("site має бути об'єктом {lat, lon} або null")
    try:
        lat, lon = float(raw["lat"]), float(raw["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConsistencyError("site: потрібні числа lat і lon") from exc
    if isinstance(raw["lat"], bool) or isinstance(raw["lon"], bool) or not -90 <= lat <= 90 or not -180 <= lon <= 360:
        raise ConsistencyError("site: lat має бути в межах −90…90, lon — −180…360")
    return lat, lon


def _stay_days(body: Mapping, mission_body: Mapping) -> float:
    raw = body.get("stay_days", mission_body.get("days", 0))
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 <= raw <= MAX_STAY_DAYS:
        raise ConsistencyError(f"stay_days має бути числом від 0 до {MAX_STAY_DAYS:g}")
    return float(raw)


def _limit(result: Mapping, quantity: str) -> Mapping | None:
    limits = (result.get("profile") or {}).get("limits") or {}
    return next((x for x in limits.values() if x.get("quantity") == quantity and x.get("value") is not None), None)


def _mission_checks(result: Mapping, crewed: bool, stay: float, trajectory: str) -> list[dict]:
    out: list[dict] = []
    if crewed and stay <= 0:
        out.append(
            _conflict("stay-missing", "warning", 4, "Для пілотованої місії не задано тривалість перебування на Місяці.")
        )
    cs = result.get("crew_supplies")
    if crewed and cs is None:
        out.append(
            _conflict(
                "supplies-not-computed",
                "info",
                6,
                "Запаси екіпажу не розраховано: задайте стать, вік, масу, зріст і активність кожної людини.",
            )
        )
    elif cs is not None and not cs["summary"]["mission_ok"]:
        s = cs["summary"]
        out.append(
            _conflict(
                "supplies-shortage",
                "error",
                6,
                f"Запасів життєзабезпечення не вистачає: {s['first_shortage_resource']} закінчується на добі "
                f"{s['first_shortage_day']:.1f} з {cs['days']:g}.",
                resource=s["first_shortage_resource"],
                day=s["first_shortage_day"],
                deficit_kg=s["deficit_kg"],
            )
        )
    cost = result["cost"]
    if cost["launches"] > 1:
        out.append(
            _conflict(
                "capacity-exceeded",
                "warning",
                8,
                f"Маса не вміщується в одну ракету: потрібно {cost['launches']} пуски й стикування "
                f"(заповненість {cost['utilization'] * 100:.0f} %). Оберіть важчу ракету або зменште навантаження.",
                launches=cost["launches"],
                utilization=cost["utilization"],
            )
        )
    system = (result.get("launch_system") or {}).get("system") or {}
    if system.get("verified_by_flight") is False:
        out.append(_conflict("rocket-unverified", "warning", 8, "Обрана ракета ще не підтверджена польотом."))
    if crewed and trajectory == "low_energy":
        lo, hi = cost["flight_time_days"]
        out.append(
            _conflict(
                "route-long-for-crew",
                "warning",
                8,
                f"Найекономніша траєкторія для екіпажу: переліт {lo:g}–{hi:g} діб. Запаси мають покрити й дорогу.",
                flight_days=[lo, hi],
            )
        )
    return out


def _light_checks(result: Mapping, tl: Mapping, night_used_h: float, supply_power: bool) -> list[dict]:
    out: list[dict] = []
    sun_pct, earth_pct = tl["sun_fraction"] * 100, tl["earth_fraction"] * 100
    if tl["sun_fraction"] <= 0:
        out.append(
            _conflict(
                "light-none",
                "warning" if supply_power else "error",
                3,
                "Протягом перебування Сонце не піднімається над горизонтом точки: сонячна енергія неможлива. "
                "Змініть дату (крок 3) або точку (крок 5)"
                + (" — або покладайтеся на реактор." if supply_power else "."),
                sun_fraction=tl["sun_fraction"],
            )
        )
    else:
        lim = _limit(result, "sun_visible_fraction")
        if lim and sun_pct < lim["value"]:
            out.append(
                _conflict(
                    "light-low",
                    "warning",
                    3,
                    f"Сонце видно {sun_pct:.1f} % часу перебування — менше фільтра відбору NASA ({lim['value']:g} %). "
                    "Змініть дату (крок 3) або точку (крок 5).",
                    sun_percent=round(sun_pct, 2),
                    limit_percent=lim["value"],
                    limit_id=lim.get("id"),
                )
            )
    lim = _limit(result, "earth_visible_fraction")
    if lim and earth_pct < lim["value"]:
        out.append(
            _conflict(
                "earth-low",
                "warning",
                5,
                f"Земля над горизонтом {earth_pct:.1f} % часу перебування — менше фільтра відбору NASA "
                f"({lim['value']:g} %): зв'язок напряму із Землею обмежений. Змініть дату чи точку.",
                earth_percent=round(earth_pct, 2),
                limit_percent=lim["value"],
                limit_id=lim.get("id"),
            )
        )
    night = tl["longest_night_h"]
    if night > night_used_h + NIGHT_TOLERANCE_H and not supply_power:
        out.append(
            _conflict(
                "night-underestimated",
                "warning",
                7,
                f"У точці найдовша ніч за період перебування — {night:.0f} год, а акумулятори розраховано на "
                f"{night_used_h:.0f} год. Врахуйте її в розрахунку (кнопка «Врахувати найдовшу ніч»).",
                longest_night_h=night,
                used_h=night_used_h,
            )
        )
    return out


def analyze(body: Mapping) -> tuple[dict, dict]:
    """Перевіряє вибори майстра: (розібраний запит із розрахунком місії, відповідь перевірки).

    `ValueError` (зокрема `ConsistencyError`, `MissionError`) — помилка вхідних даних. Звіт (B24) бере той самий
    розрахунок, щоб не рахувати місію вдруге."""
    if not isinstance(body, Mapping):
        raise ConsistencyError("Тіло запиту має бути об'єктом")
    unknown = set(body) - ALLOWED
    if unknown:
        raise ConsistencyError(f"Невідомі поля: {', '.join(sorted(unknown))}")
    mission_body = body.get("mission", {})
    if not isinstance(mission_body, Mapping):
        raise ConsistencyError("mission має бути об'єктом (як тіло POST /api/mission)")
    launch = _parse_when(body.get("datetime"))
    site = _parse_site(body.get("site"))
    stay = _stay_days(body, mission_body)
    result = mission_service.compute(dict(mission_body))
    crewed = result["profile"]["profile"] == "crewed" if result.get("profile") else bool(mission_body.get("crew"))

    conflicts: list[dict] = []
    skipped: list[dict] = []
    if not body.get("goal"):
        conflicts.append(
            _conflict("goal-missing", "warning", 1, "Не обрано мету місії: від неї залежать район і навантаження.")
        )
    if not str(body.get("name") or "").strip():
        conflicts.append(
            _conflict("name-missing", "info", 1, "Не задано назву місії (формальність, на розрахунки не впливає).")
        )
    conflicts += _mission_checks(result, crewed, stay, mission_body.get("trajectory", "direct"))

    window = None
    suggested: dict = {}
    if launch is None:
        conflicts.append(
            _conflict("window-missing", "warning", 3, "Не задано дату запуску: освітлення й зв'язок не перевірено.")
        )
        skipped.append({"id": "light", "reason": "немає дати запуску"})
    elif site is None:
        conflicts.append(
            _conflict("site-missing", "warning", 5, "Не вибрано точку посадки: освітлення й зв'язок не перевірено.")
        )
        skipped.append({"id": "light", "reason": "немає точки посадки"})
    elif stay <= 0:
        skipped.append({"id": "light", "reason": "тривалість перебування не задана"})
    else:
        lo, hi = result["cost"]["flight_time_days"]
        start = launch + timedelta(days=(lo + hi) / 2)
        end = start + timedelta(days=stay)
        window = {
            "start": start.strftime("%Y-%m-%dT%H:%MZ"),
            "end": end.strftime("%Y-%m-%dT%H:%MZ"),
            "basis": "старт + середній переліт; перебування з вказаної тривалості",
        }
        try:
            tl = timeline_service.timeline(site[0], site[1], start, end, 1.0)["summary"]
        except (RuntimeError, ValueError) as exc:  # немає ефемерид чи даних
            skipped.append({"id": "light", "reason": str(exc)})
        else:
            supply_power = (result.get("equipment") or {}).get("supply_power_w", 0) > 0
            night_used = float(mission_body.get("longest_night_h") or 0.0)
            found = _light_checks(result, tl, night_used, supply_power)
            conflicts += found
            if any(c["id"] == "night-underestimated" for c in found):
                suggested["longest_night_h"] = round(tl["longest_night_h"], 1)
            window["sun_fraction"], window["earth_fraction"] = tl["sun_fraction"], tl["earth_fraction"]
            window["longest_night_h"] = tl["longest_night_h"]
    rank = {"error": 0, "warning": 1, "info": 2}
    conflicts.sort(key=lambda c: (rank[c["severity"]], c["step"]))
    counts = {s: sum(1 for c in conflicts if c["severity"] == s) for s in rank}
    out = {
        "ok": counts["error"] == 0,
        "counts": counts,
        "conflicts": conflicts,
        "skipped": skipped,
        "window": window,
        "suggested": suggested,
        "provisional": result.get("provisional", True),
        "steps_to_review": sorted({c["step"] for c in conflicts if c["severity"] != "info"}),
    }
    parsed = {"result": result, "launch": launch, "site": site, "stay": stay, "crewed": crewed,
              "mission_body": mission_body, "goal": body.get("goal"), "name": str(body.get("name") or "").strip(),
              "site_name": (body.get("site") or {}).get("name") if isinstance(body.get("site"), Mapping) else None}
    return parsed, out


def compute(body: Mapping) -> dict:
    """Перевіряє вибори майстра (B23); відповідь — `ConsistencyResponse`."""
    return analyze(body)[1]
