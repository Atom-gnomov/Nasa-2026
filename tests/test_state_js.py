"""JS-тести фронтенду (tests/js/test_*.mjs) у Node: спільний стан, календар, порівняння.

Кожен файл — окремий тест pytest. Без Node.js тести пропускаються — решта набору від них не залежить.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
SCRIPTS = sorted((Path(__file__).parent / "js").glob("test_*.mjs"))


@pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_js(script):
    proc = subprocess.run(
        [NODE, "--test", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
