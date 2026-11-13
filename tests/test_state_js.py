"""Спільний стан фронтенду (app/static/js/state.js): JS-тести tests/js/test_state.mjs у Node.

Без Node.js тест пропускається — решта набору від нього не залежить.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
SCRIPT = Path(__file__).parent / "js" / "test_state.mjs"


@pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")
def test_state_js():
    proc = subprocess.run(
        [NODE, "--test", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
