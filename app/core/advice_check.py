"""Перевірка відповіді ШІ: чи всі числа в ній є у вхідних даних (docs/CONTRACTS.md, §2.0).

Модель лише тлумачить готові числа й нічого не рахує. Якщо в тексті є число, якого немає у `facts`
(ні саме, ні як відсоток частки, ні як години → доби), відповідь позначається неперевіреною.
Чисті функції без залежностей.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

NUMBER = re.compile(r"(?<![\w.,])[-+−]?\d+(?:[.,]\d+)?")
TRIVIAL_MAX = 12  # лічильники й порядкові числа («на один крок», «2–3 поради», «1.») не вважаємо новими фактами


def _parse(token: str) -> float:
    return float(token.replace("−", "-").replace(",", "."))


def numbers_in(text: str) -> list[float]:
    return [_parse(t) for t in NUMBER.findall(text)]


def collect_fact_numbers(facts: object) -> set[float]:
    """Усі числа у facts: значення-числа, а також цифри, вбудовані в рядки (дати, назви на кшталт «Apollo 11»)."""
    out: set[float] = set()

    def walk(node: object) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            out.add(float(node))
        elif isinstance(node, str):
            out.update(numbers_in(node))
        elif isinstance(node, Mapping):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, Iterable):
            for v in node:
                walk(v)

    walk(facts)
    return out


def _derived(value: float) -> Iterable[float]:
    yield value
    yield value * 100  # частка → відсотки
    yield value / 24  # години → доби
    yield value * 24  # доби → години


def unknown_numbers(text: str, facts: object, rel_tol: float = 0.01, abs_tol: float = 0.06) -> list[str]:
    """Числа з тексту, яких немає у facts (з допуском на округлення). Порожній список — усе перевірено."""
    known = collect_fact_numbers(facts)
    derived = [d for v in known for d in _derived(v)]
    unknown = []
    for token in NUMBER.findall(text):
        n = abs(_parse(token))
        if n <= TRIVIAL_MAX and float(n).is_integer():
            continue
        if not any(abs(n - abs(d)) <= max(abs_tol, rel_tol * abs(d)) for d in derived):
            unknown.append(token)
    return unknown
