"""Готові пакети оброблених даних із GitHub Release (задача I9; виробник пакетів — I10).

Замість завантаження ≈ 3,4 ГБ сирих даних з PDS і їх обробки застосунок може одним архівом узяти вже оброблене
(десятки МБ). Опис пакетів — `app/data/data_packs.json`: id, набір даних, варіант (`full` | `light`), версія релізу,
посилання, розмір і **`sha256`**. Пакет, у якого немає посилання чи контрольної суми, вважається **неопублікованим**
і не використовується — застосунок збирає дані зі скриптів, як і раніше.

Гарантії:
  • **перевірка `sha256`** після завантаження: неспівпадіння — помилка, часткового файлу не лишається;
  • **докачування** (`Range`) перерваного завантаження;
  • **безпечне розпакування** — жодного файла поза каталогом набору (захист від `../` в архіві);
  • лише `https` (`http` — тільки для localhost, як в адаптері ШІ).
Чисті функції без Flask: мережа підміняється параметром `opener`.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
PACKS_FILE = ROOT / "app" / "data" / "data_packs.json"
VARIANTS = ("full", "light")
CHUNK = 1 << 20
TIMEOUT_S = 60


class PackError(RuntimeError):
    """Пакет не вдалося отримати чи перевірити (причина — у тексті, українською)."""


def load_packs(path: Path = PACKS_FILE) -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def is_published(pack: dict) -> bool:
    """Є посилання (https, або http на localhost) і контрольна сума sha256 — інакше пакет ще не опубліковано."""
    url, digest = pack.get("url"), pack.get("sha256")
    if not url or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))


def find(packs: Sequence[dict], dataset: str, variant: str) -> dict | None:
    """Опублікований пакет набору й варіанта (останній за порядком у файлі) або None."""
    if variant not in VARIANTS:
        raise ValueError(f"Невідомий варіант пакета {variant!r}; є {', '.join(VARIANTS)}")
    found = [p for p in packs if p.get("dataset") == dataset and p.get("variant") == variant and is_published(p)]
    return found[-1] if found else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download(pack: dict, work_dir: Path, progress: Callable[[int, int | None], None] | None = None,
             opener: Callable = urllib.request.urlopen) -> Path:
    """Завантажує архів пакета в `work_dir` з докачуванням і перевіркою sha256; повертає шлях до файла."""
    if not is_published(pack):
        raise PackError(f"Пакет {pack.get('id')} не опубліковано (немає посилання чи sha256)")
    work_dir.mkdir(parents=True, exist_ok=True)
    final = work_dir / f"{pack['id']}.zip"
    part = work_dir / f"{pack['id']}.zip.part"
    if final.is_file() and _sha256(final) == pack["sha256"]:
        return final  # уже завантажено раніше
    have = part.stat().st_size if part.is_file() else 0
    request = urllib.request.Request(pack["url"], headers={"Range": f"bytes={have}-"} if have else {})
    try:
        with opener(request, timeout=TIMEOUT_S) as resp:
            status = getattr(resp, "status", 200)
            if have and status != 206:
                have = 0  # сервер не підтримує докачування — починаємо спочатку
            length = resp.headers.get("Content-Length")
            total = (int(length) + have) if length and length.isdigit() else None
            with open(part, "ab" if have else "wb") as out:
                done = have
                while True:
                    block = resp.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if progress:
                        progress(done, total)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and part.is_file():  # весь файл уже є: перевіримо суму нижче
            pass
        else:
            raise PackError(f"Сервер відповів {exc.code} на {pack['url']}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise PackError(f"Не вдалося завантажити пакет {pack['id']}: {exc}") from exc
    if _sha256(part) != pack["sha256"]:
        part.unlink(missing_ok=True)  # зіпсований файл не лишаємо: наступна спроба почнеться з нуля
        raise PackError(f"Пакет {pack['id']}: контрольна сума не збігається з опублікованою (sha256) — файл відкинуто")
    part.replace(final)
    return final


def extract(archive: Path, dest: Path) -> list[str]:
    """Розпаковує zip у `dest`; файли поза каталогом (`../`, абсолютні шляхи) — помилка, нічого не записується."""
    dest = dest.resolve()
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            for name in names:
                target = (dest / name).resolve()
                if dest != target and dest not in target.parents:
                    raise PackError(f"Архів містить небезпечний шлях {name!r} — розпаковування скасовано")
            dest.mkdir(parents=True, exist_ok=True)
            zf.extractall(dest)
            return [n for n in names if not n.endswith("/")]
    except zipfile.BadZipFile as exc:
        raise PackError(f"Архів {archive.name} пошкоджений: {exc}") from exc


def install(pack: dict, dest: Path, work_dir: Path, progress: Callable[[int, int | None], None] | None = None,
            opener: Callable = urllib.request.urlopen) -> list[str]:
    """Завантажує, перевіряє й розпаковує пакет у `dest`; архів після успіху видаляється."""
    archive = download(pack, work_dir, progress, opener)
    files = extract(archive, dest)
    archive.unlink(missing_ok=True)
    return files
