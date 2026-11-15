"""B24: підсумковий звіт місії (П-14, крок 10) — усі вибори майстра, розрахунки, конфлікти й джерела.

Бере ті самі вибори, що й `POST /api/consistency` (рахує місію й перевірку один раз, через `consistency.analyze`),
і складає звіт у логічному порядку кроків: JSON-розділи й готовий Markdown. Нічого не вигадує: числа — з розрахунку,
пороги й характеристики приладів — із джерел NASA (їхні посилання додаються в `sources`).
"""

from __future__ import annotations

from collections.abc import Mapping

from app.services import catalogs
from app.services import consistency as consistency_service

GOAL_LABELS = {
    "samples": "Збір зразків",
    "ice": "Пошук води й льоду",
    "technology": "Випробування технологій",
    "science": "Наукові дослідження",
    "base": "Постійна база",
}
CHAIN = [
    "Назва місії",
    "Мета місії",
    "Тип місії",
    "Вікно запуску",
    "Тривалість",
    "Район і точка посадки",
    "Склад екіпажу або техніки",
    "Корисне навантаження",
    "Носій",
    "Перевірка узгодженості",
    "Підсумковий звіт",
]
SEVERITY_MARK = {"error": "✗", "warning": "!", "info": "·"}
CAVEATS = [
    "Усі коефіцієнти моделі тимчасові (чекають таблиць мас і цін): показано діапазони.",
    "Моделюється переліт до Місяця й перебування; зліт і повернення в моделі поки немає (задача M26), тому «разом» "
    "у часовій лінії — без повернення.",
]
CATEGORY_LABELS = {"equipment": "Обладнання", "life_support": "Життєзабезпечення", "comfort": "Умови й зручності"}


def _num(x: float, digits: int = 0) -> str:
    return f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")


def _kg(x: float) -> str:
    return f"{_num(x)} кг"


def _range(pair, unit: str = "", digits: int = 0) -> str:
    lo, hi = pair
    body = _num(lo, digits) if lo == hi else f"{_num(lo, digits)}–{_num(hi, digits)}"
    return f"{body} {unit}".strip()


def _usd(pair) -> str:
    lo, hi = pair
    div, name = (1e9, "млрд") if hi >= 1e9 else (1e6, "млн") if hi >= 1e6 else (1e3, "тис.") if hi >= 1e3 else (1.0, "")
    f = lambda v: _num(v / div, 0 if v / div >= 10 else 1)  # noqa: E731
    return f"${f(lo)}–{f(hi)} {name}".strip()


def _pct(pair) -> str:
    return f"{_num(pair[0] * 100, 1)}–{_num(pair[1] * 100, 1)} %"


def _utc(iso: str) -> str:
    return iso.replace("T", " ").replace("Z", " UTC")


def _row(label: str, value: str) -> dict:
    return {"label": label, "value": value}


def _sections(p: Mapping, check: Mapping) -> list[dict]:
    r, mission_body = p["result"], p["mission_body"]
    cost, risk = r["cost"], r["risk"]
    crewed = p["crewed"]
    lo, hi = cost["flight_time_days"]
    out: list[dict] = []

    goal = p["goal"]
    out.append(
        {
            "step": 1,
            "title": "Назва та мета",
            "rows": [
                _row("Назва", p["name"] or "не задано"),
                _row("Мета", GOAL_LABELS.get(goal, goal) if goal else "не задано"),
            ],
        }
    )
    crew = (r.get("profile") or {}).get("crew")
    out.append(
        {
            "step": 2,
            "title": "Тип місії",
            "rows": [
                _row("Тип", "пілотована" if crewed else "безпілотна"),
                *([_row("Екіпаж", f"{crew} осіб")] if crewed and crew else []),
            ],
        }
    )
    out.append(
        {
            "step": 4,
            "title": "Тривалість",
            "rows": [
                _row("Переліт до Місяця", _range([lo, hi], "діб", 1)),
                _row("Перебування на Місяці", f"{_num(p['stay'])} діб"),
                _row("Зліт і повернення", "не змодельовано (задача M26)"),
            ],
        }
    )
    site = p["site"]
    window = check.get("window")
    when = p["launch"]
    rows5 = [
        _row(
            "Точка",
            f"{p['site_name'] + ', ' if p['site_name'] else ''}{_num(site[0], 3)}°, {_num(site[1], 3)}°"
            if site
            else "не вибрано",
        ),
        _row("Дата посадки", when.strftime("%Y-%m-%d %H:%M UTC") if when else "не задано"),
    ]
    if window:
        rows5 += [
            _row("Перебування на місці (оцінка)", f"{_utc(window['start'])} — {_utc(window['end'])}"),
            _row("Сонце над горизонтом, % часу перебування", _num(window["sun_fraction"] * 100, 1)),
            _row("Земля над горизонтом, % часу перебування", _num(window["earth_fraction"] * 100, 1)),
            _row("Найдовша ніч", f"{_num(window['longest_night_h'])} год"),
        ]
    out.append({"step": 5, "title": "Район, дата й точка посадки", "rows": rows5})
    rows6 = [_row("Склад", f"екіпаж {crew} осіб" if crewed and crew else "безпілотна: без екіпажу")]
    cs = r.get("crew_supplies")
    if cs:
        rows6.append(
            _row(
                "Запаси життєзабезпечення",
                f"{_kg(cs['loaded_total_kg'])}; "
                + ("вистачає на всю місію" if cs["summary"]["mission_ok"] else "не вистачає"),
            )
        )
    eq = r.get("equipment")
    for it in (eq or {}).get("items", []):
        rows6.append(_row(it["name"], f"× {it['count']}; {_range(it['mass_kg'], 'кг', 1)}"))
    out.append({"step": 6, "title": "Екіпаж або техніка", "rows": rows6})
    rows7 = [
        _row(CATEGORY_LABELS[k], f"{_kg(v['mass_kg'])}; {_usd(v['usd'])}")
        for k, v in r["categories"].items()
        if k == "equipment" or crewed
    ]
    rows7 += [
        _row("Маса на Місяці", _kg(cost["mass_moon_kg"])),
        _row("Маса на низькій орбіті", _kg(cost["mass_leo_kg"])),
    ]
    if eq:
        rows7.append(_row("Доставка обладнання за каталогом NASA", _usd(eq["delivery_usd"])))
    if mission_body.get("longest_night_h"):
        rows7.append(_row("Найдовша ніч для акумуляторів", f"{_num(mission_body['longest_night_h'])} год"))
    out.append({"step": 7, "title": "Корисне навантаження", "rows": rows7})
    system = (r.get("launch_system") or {}).get("system")
    rows8 = [
        _row("Носій", system["name"] if system else "типова ракета (орієнтовна)"),
        _row("Траєкторія", "найекономніша" if cost["trajectory"] == "low_energy" else "пряма"),
        _row("Пусків", str(cost["launches"])),
        _row("Заповненість ракети", f"{_num(cost['utilization'] * 100)} %"),
        _row("Вартість польоту", _usd(cost["total_usd"])),
        _row("Ризик невдачі", f"{risk['band_label']} ({_pct(risk['p_total_range'])})"),
    ]
    if risk.get("p_crew_loss_range"):
        rows8.append(_row("Ризик втрати екіпажу", f"{risk['crew_band_label']} ({_pct(risk['p_crew_loss_range'])})"))
    out.append({"step": 8, "title": "Носій", "rows": rows8})
    c = check["counts"]
    rows9 = [_row("Підсумок", f"помилок {c['error']}, попереджень {c['warning']}, зауважень {c['info']}")]
    rows9 += [_row(f"{SEVERITY_MARK[x['severity']]} крок {x['step']}", x["message"]) for x in check["conflicts"]]
    rows9 += [_row("Не перевірено", x["reason"]) for x in check["skipped"]]
    out.append({"step": 9, "title": "Перевірка узгодженості", "rows": rows9})
    return out


def _sources(r: Mapping, check: Mapping) -> list[dict]:
    found: dict[str, dict] = {}
    for it in (r.get("equipment") or {}).get("items", []):
        s = it.get("source") or {}
        if s.get("url"):
            found.setdefault(s["url"], {"title": s.get("title", ""), "ref": s.get("ref", ""), "url": s["url"]})
    used = {x.get("values", {}).get("limit_id") for x in check["conflicts"]} - {None}
    for lim in catalogs.load_mission_thresholds():
        s = lim.get("source") or {}
        if lim.get("id") in used and s.get("url"):
            found.setdefault(s["url"], {"title": s.get("title", ""), "ref": s.get("ref", ""), "url": s["url"]})
    return list(found.values())


def to_markdown(rep: Mapping) -> str:
    """Звіт у Markdown: заголовок, застереження, розділи за кроками, схема рішень, джерела."""
    out = [f"# Місія: {rep['name'] or 'без назви'}", ""]
    out += [f"> ⚠️ {x}" for x in rep["caveats"]]
    for i, sec in enumerate(rep["sections"], 1):  # нумерація за порядком: крок «Дата посадки» злито з кроком 5
        out += ["", f"## {i}. {sec['title']}", ""]
        out += [f"- **{row['label']}:** {row['value']}" for row in sec["rows"]]
    out += ["", "## Послідовність рішень", "", " → ".join(rep["chain"])]
    if rep["sources"]:
        out += ["", "## Джерела", ""]
        out += [f"- {s['title']}{', ' + s['ref'] if s['ref'] else ''} — {s['url']}" for s in rep["sources"]]
    return "\n".join(out) + "\n"


def compute(body: Mapping) -> dict:
    """Звіт за вибором майстра; відповідь — `ReportResponse`. `ValueError` — помилка вхідних даних."""
    parsed, check = consistency_service.analyze(body)
    rep = {
        "name": parsed["name"],
        "goal": parsed["goal"] or None,
        "goal_label": GOAL_LABELS.get(parsed["goal"], parsed["goal"]) if parsed["goal"] else None,
        "ok": check["ok"],
        "provisional": check["provisional"],
        "sections": _sections(parsed, check),
        "conflicts": check["conflicts"],
        "sources": _sources(parsed["result"], check),
        "chain": CHAIN,
        "caveats": CAVEATS,
    }
    rep["markdown"] = to_markdown(rep)
    return rep
