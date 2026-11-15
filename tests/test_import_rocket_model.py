"""tools/import_rocket_model.py: копіює GLB у data_cache/system і записує в system.json (з ліцензією й автором)."""

import importlib.util
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("import_rocket_model", ROOT / "tools" / "import_rocket_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _glb(path: Path, meshes: int = 2) -> Path:
    body = json.dumps({"asset": {"version": "2.0"}, "meshes": [{}] * meshes, "materials": [{}] * 3}).encode()
    body += b" " * (-len(body) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 20 + len(body)) + struct.pack("<I4s", len(body), b"JSON") + body)
    return path


def test_import_copies_model_and_registers_credit(tmp_path, monkeypatch):
    tool = _tool()
    out = tmp_path / "system"
    out.mkdir()
    start = {"version": 1, "assets": {"sun": {"file": "sun.glb"}}}
    (out / "system.json").write_text(json.dumps(start), encoding="utf-8")
    monkeypatch.setattr(tool, "OUT_DIR", out)
    monkeypatch.setattr(sys, "argv", ["import_rocket_model.py", str(_glb(tmp_path / "in.glb"))])
    tool.main()
    meta = json.loads((out / "system.json").read_text(encoding="utf-8"))
    rocket = meta["assets"]["rocket"]
    assert (out / rocket["file"]).exists() and rocket["meshes"] == 2 and rocket["materials"] == 3
    assert rocket["license"] == "CC-BY-4.0" and "Clarence365" in rocket["credit"], "вказівка авторства обов'язкова"
    assert meta["assets"]["sun"] == {"file": "sun.glb"}, "чужі записи не чіпаємо"
    assert meta["version"] > 1, "версія оновлюється, щоб браузер не брав стару копію з кешу"


def test_import_rejects_non_glb(tmp_path, monkeypatch):
    tool = _tool()
    bad = tmp_path / "bad.glb"
    bad.write_bytes(b"not a glb at all")
    monkeypatch.setattr(tool, "OUT_DIR", tmp_path / "system")
    monkeypatch.setattr(sys, "argv", ["import_rocket_model.py", str(bad)])
    with pytest.raises(SystemExit):
        tool.main()
