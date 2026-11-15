"""Підключає 3D-модель ракети для симуляції польоту в «Системі» з локального файлу glTF/GLB.

Модель — «NASA SLS Block 1 Crew V4», автор Clarence365, ліцензія CC BY 4.0 (потрібна вказівка авторства — програма
показує її в блоці «Джерела» сцени):
    https://sketchfab.com/3d-models/nasa-sls-block-1-crew-v4-2d521014700b44dbbc7662f648974e98

Файл завеликий для git (≈7 МБ, 246 тис. вершин), тому в репозиторій не входить: його копіюють у data_cache/system/ і
записують у system.json (ключ rocket). Без нього сцена малює просту ракету-конус — нічого не ламається.

Запуск:  python tools/import_rocket_model.py <шлях до nasa_sls_block_1_crew_v4.glb>
Повторна збірка build_system_assets.py запис rocket зберігає.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_cache" / "system"
FILE_NAME = "sls_block1_crew.glb"
MAX_BYTES = 40 * 1024 * 1024

META = {
    "file": FILE_NAME,
    "page": "https://sketchfab.com/3d-models/nasa-sls-block-1-crew-v4-2d521014700b44dbbc7662f648974e98",
    "credit": "«NASA SLS Block 1 Crew V4», Clarence365 (Sketchfab), CC BY 4.0",
    "license": "CC-BY-4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "note": "Модель ракети SLS Block 1 Crew для симуляції польоту; розмір — справжній відносно планети (98,3 м)",
    "length_m": 98.3,
    "length_source": "NASA, Space Launch System Reference Guide (2022): висота Block 1 — 322,4 фути (98,3 м)",
    "length_url": "https://www.nasa.gov/wp-content/uploads/2022/03/sls_reference_guide_2022_web.pdf",
}


def read_glb(path: Path) -> dict:
    """Перевіряє заголовок GLB 2.0 і повертає його JSON-частину (опис meshes і materials)."""
    with path.open("rb") as f:
        magic, version, length = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF" or version != 2:
            raise SystemExit(f"{path.name}: це не GLB 2.0")
        chunk_len, chunk_type = struct.unpack("<I4s", f.read(8))
        if chunk_type != b"JSON":
            raise SystemExit(f"{path.name}: перша частина не JSON")
        return json.loads(f.read(chunk_len))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("glb", type=Path, help="шлях до .glb")
    path = parser.parse_args().glb.expanduser()
    if not path.is_file():
        raise SystemExit(f"немає файлу: {path}")
    if path.stat().st_size > MAX_BYTES:
        raise SystemExit(f"файл більший за {MAX_BYTES // 1024 // 1024} МБ — для вебсторінки завеликий")
    gltf = read_glb(path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, OUT_DIR / FILE_NAME)
    meta_path = OUT_DIR / "system.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"assets": {}}
    meta.setdefault("assets", {})["rocket"] = {
        **META,
        "meshes": len(gltf.get("meshes", [])),
        "materials": len(gltf.get("materials", [])),
        "bytes": (OUT_DIR / FILE_NAME).stat().st_size,
    }
    meta["version"] = int(time.time())  # інакше браузер візьме стару копію з кешу
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"готово: {OUT_DIR / FILE_NAME} ({meta['assets']['rocket']['bytes'] // 1024} КБ), запис rocket у system.json")


if __name__ == "__main__":
    main()
