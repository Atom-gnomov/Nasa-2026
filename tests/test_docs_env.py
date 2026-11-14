"""Змінні середовища з коду описані в README (задача I8): документація не відстає від app/config.py."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _used_in_code() -> set[str]:
    names = set()
    for path in (ROOT / "app").rglob("*.py"):
        names |= set(re.findall(r"""["'](LSE_[A-Z_]+)["']""", path.read_text(encoding="utf-8")))
    return names


def test_every_env_variable_in_code_is_documented_in_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = sorted(n for n in _used_in_code() if f"`{n}`" not in readme)
    assert not missing, f"змінні без опису в README (розділ «Змінні середовища»): {missing}"


def test_env_example_has_no_secrets_and_lists_auto_prepare():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^LSE_LLM_API_KEY=\s*$", example, re.M)  # ключ порожній
    assert "LSE_AUTO_PREPARE=" in example and "LSE_AUTO_PREPARE_DATASETS=" in example
