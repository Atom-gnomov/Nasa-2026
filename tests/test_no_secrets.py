"""Запобіжник: у файлах репозиторію (відстежуваних git) не мають з'являтися ключі й токени сервісів.

Ключі зберігаються лише в .env (у .gitignore), змінних середовища або секретах CI. Навіть «обфусковані» ключі
в репозиторії не є захистом: вони відновлюються, а історія git зберігає їх назавжди.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "ключ thk_live_": re.compile(r"thk_live_[A-Za-z0-9_\-]{16,}"),
    "ключ sk-": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "токен GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "приватний ключ": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "ключ AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Bearer-токен у коді": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{30,}"),
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".glb", ".gz", ".npz", ".bin", ".pyc"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=ROOT, check=False)
    if out.returncode != 0:
        pytest.skip("не git-репозиторій")
    return [ROOT / f for f in out.stdout.splitlines() if (ROOT / f).suffix.lower() not in SKIP_SUFFIXES]


def test_no_secrets_in_tracked_files():
    found = []
    for path in tracked_files():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                found.append(f"{path.relative_to(ROOT)}: {name}")
    assert not found, "Знайдено схожі на секрети значення (не комітьте їх): " + "; ".join(found)


def test_env_files_are_ignored_but_example_is_tracked():
    ignored = subprocess.run(["git", "check-ignore", ".env"], capture_output=True, cwd=ROOT, check=False)
    assert ignored.returncode == 0, ".env має бути в .gitignore"
    example = subprocess.run(["git", "check-ignore", ".env.example"], capture_output=True, cwd=ROOT, check=False)
    assert example.returncode != 0, ".env.example має комітитись"
