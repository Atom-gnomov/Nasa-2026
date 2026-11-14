"""Які українські тексти інтерфейсу ще не мають англійського перекладу (F8).

Словник — app/static/js/i18n/en.json: «strings» (точний збіг тексту) і «phrases» (підрядки для складених
рядків із числами). Тексти шаблонів витягуються HTML-розбором (видимий текст і title / aria-label /
placeholder / alt), літерали JS — евристикою (рядки з кирилицею, без коментарів).

    python tools/i18n_missing.py            # зведення: покриття шаблонів і список непереведеного
    python tools/i18n_missing.py --js       # додатково літерали JS без точного збігу в словнику
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
JS_DIR = ROOT / "app" / "static" / "js"
DICTIONARY = JS_DIR / "i18n" / "en.json"
CYRILLIC = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
ATTRS = ("title", "aria-label", "placeholder", "alt")
SKIP_TAGS = {"script", "style"}


def normalize(text: str) -> str:
    """Пробіли згортаються так само, як у клієнтському перекладачі (i18n.js: normalize)."""
    return re.sub(r"\s+", " ", text).strip()


def _strip_jinja(source: str) -> str:
    """Прибирає коментарі й теги Jinja; текст усередині {% block %} лишається (напр. заголовок сторінки)."""
    source = re.sub(r"\{#.*?#\}", "", source, flags=re.S)
    return re.sub(r"\{%.*?%\}", " ", source, flags=re.S)


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.strings: set[str] = set()
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        for name, value in attrs:
            if name in ATTRS and value:
                self._add(value)

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._add(data)

    def _add(self, text: str) -> None:
        text = normalize(text)
        if text and CYRILLIC.search(text) and "{{" not in text:
            self.strings.add(text)


def template_strings(path: Path) -> set[str]:
    collector = _Collector()
    collector.feed(_strip_jinja(path.read_text(encoding="utf-8")))
    return collector.strings


def all_template_strings() -> dict[str, set[str]]:
    return {p.name: template_strings(p) for p in sorted(TEMPLATES.glob("*.html"))}


_JS_STRING = re.compile(r"""(?P<q>["'`])(?P<body>(?:\\.|(?!(?P=q)).)*?)(?P=q)""", re.S)


def js_strings(path: Path) -> set[str]:
    """Літерали з кирилицею без інтерполяції; коментарі `//` і `/* */` відкидаються."""
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    text = "\n".join(line.split("//")[0] if line.lstrip().startswith("//") else line for line in text.split("\n"))
    found = set()
    for m in _JS_STRING.finditer(text):
        body = m.group("body")
        if CYRILLIC.search(body) and "${" not in body and "\n" not in body:
            found.add(normalize(body))
    return found


def load_dictionary() -> dict:
    return json.loads(DICTIONARY.read_text(encoding="utf-8")) if DICTIONARY.exists() else {"strings": {}, "phrases": {}}


def main(argv: list[str]) -> int:
    dictionary = load_dictionary()
    strings = dictionary.get("strings", {})
    total = missing = 0
    for name, found in all_template_strings().items():
        absent = sorted(s for s in found if s not in strings)
        total += len(found)
        missing += len(absent)
        print(f"{name}: {len(found) - len(absent)}/{len(found)} перекладено")
        for s in absent:
            print(f"    · {s}")
    share = 100 * (total - missing) / total if total else 100.0
    print(f"Шаблони загалом: {total - missing}/{total} ({share:.0f} %)")
    if "--js" in argv:
        phrases = dictionary.get("phrases", {})
        for path in sorted(JS_DIR.glob("*.js")):
            absent = sorted(s for s in js_strings(path) if s not in strings and not any(p in s for p in phrases))
            if absent:
                print(f"{path.name}: {len(absent)} літералів без перекладу")
                for s in absent:
                    print(f"    · {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
