"""Збирає й публікує готові пакети оброблених даних (задача I10; споживач — app/services/datapack.py, I9).

Бере вже зібрані набори з `data_cache/` (температура, 3D-ресурси, глобус), пакує кожен у zip з файлами відносно
каталогу набору — без сирих завантажень (`src/`, `.part`, `.lock`, журнали), — рахує `sha256` і розмір, а за
`--publish` створює (або доповнює) GitHub Release за тегом і вписує посилання, розмір і `sha256` в
`app/data/data_packs.json`. Пакет без посилання й суми застосунок вважає неопублікованим і збирає дані зі скриптів.

Приклади:
    python tools/build_data_pack.py                       # лише зібрати архіви в data_cache/packs/ й показати суми
    python tools/build_data_pack.py --publish             # + Release data-v1 через `gh` і оновлення data_packs.json
    python tools/build_data_pack.py --datasets system --version data-v2 --repo owner/name --publish

Варіант `light` (менша роздільність, дані на найближчі дати) цим скриптом не збирається: його записи лишаються
неопублікованими. `gh` має бути залогінений (`gh auth status`) і мати право писати в репозиторій (`repo`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.bootstrap import DATASETS  # noqa: E402  (шлях до кореня додано вище)

PACKS_FILE = ROOT / "app" / "data" / "data_packs.json"
DEFAULT_REPO = "Atom-gnomov/Nasa-2026"
SKIP_DIRS = {"src"}  # сирі завантаження: у пакет не входять
SKIP_SUFFIXES = (".part", ".lock", ".log", ".tmp")


def cache_dir() -> Path:
    import os

    return Path(os.environ.get("LSE_CACHE_DIR", ROOT / "data_cache"))


def dataset_dir(dataset_id: str, cache: Path) -> Path:
    d = next(x for x in DATASETS if x.id == dataset_id)
    if d.root_key == "TEMP_DIR":
        import os

        return Path(os.environ.get("LSE_TEMP_DIR", cache / "temperature"))
    return cache / d.subdir if d.subdir else cache


def pack_files(base: Path) -> list[Path]:
    """Файли набору для пакета: усе, крім сирих завантажень і службових файлів; у стабільному порядку."""
    out = []
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base)
        if not path.is_file() or rel.parts[0] in SKIP_DIRS or path.name.endswith(SKIP_SUFFIXES):
            continue
        out.append(path)
    return out


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_zip(dataset_id: str, out_dir: Path, cache: Path) -> dict:
    """Збирає `<id>-full.zip`; повертає {id, path, size_bytes, sha256, files}. Помилка, якщо набір не зібрано."""
    d = next((x for x in DATASETS if x.id == dataset_id), None)
    if d is None:
        raise SystemExit(f"Невідомий набір {dataset_id!r}; є {', '.join(x.id for x in DATASETS)}")
    base = dataset_dir(dataset_id, cache)
    missing = [f for f in d.ready_files if not (base / f).is_file()]
    if missing:
        raise SystemExit(f"Набір {dataset_id} не зібрано (немає {', '.join(missing)}): спершу запустіть {d.script}")
    out_dir.mkdir(parents=True, exist_ok=True)
    pack_id = f"{dataset_id}-full"
    path = out_dir / f"{pack_id}.zip"
    files = pack_files(base)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files:
            zf.write(f, f.relative_to(base).as_posix())
    return {"id": pack_id, "dataset": dataset_id, "path": path, "size_bytes": path.stat().st_size,
            "sha256": sha256_of(path), "files": len(files)}


def release_url(repo: str, version: str, pack_id: str) -> str:
    return f"https://github.com/{repo}/releases/download/{version}/{pack_id}.zip"


def update_manifest(built: list[dict], version: str, repo: str, packs_file: Path = PACKS_FILE) -> list[dict]:
    """Вписує url, розмір, sha256 і версію в записи `full` зібраних наборів; решту записів не чіпає."""
    packs = json.loads(packs_file.read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in packs}
    for b in built:
        pack = by_id.get(b["id"])
        if pack is None:
            raise SystemExit(f"У {packs_file.name} немає запису {b['id']}")
        pack.update(version=version, url=release_url(repo, version, b["id"]), size_bytes=b["size_bytes"],
                    sha256=b["sha256"], published=True)
    packs_file.write_text(json.dumps(packs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return packs


def publish(built: list[dict], version: str, repo: str) -> None:
    """Release `version` у репозиторії: створює, якщо немає, і завантажує архіви (наявні замінює)."""
    paths = [str(b["path"]) for b in built]
    exists = subprocess.run(["gh", "release", "view", version, "--repo", repo], capture_output=True).returncode == 0
    if exists:
        cmd = ["gh", "release", "upload", version, *paths, "--clobber", "--repo", repo]
    else:
        notes = ("Готові оброблені пакети даних для застосунку (задача I10): " + ", ".join(b["id"] for b in built) +
                 ". Контрольні суми `sha256` — у app/data/data_packs.json; застосунок бере їх сам "
                 "(LSE_AUTO_PREPARE_MODE=pack).")
        cmd = ["gh", "release", "create", version, *paths, "--title", f"Пакети даних {version}", "--notes", notes,
               "--repo", repo]
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--datasets", nargs="+", default=[d.id for d in DATASETS], help="які набори пакувати")
    ap.add_argument("--version", default="data-v1", help="тег Release")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="owner/name репозиторію з Release")
    ap.add_argument("--out", type=Path, default=None, help="куди класти архіви (за замовчуванням data_cache/packs)")
    ap.add_argument("--publish", action="store_true", help="завантажити в Release і оновити data_packs.json")
    args = ap.parse_args(argv)

    cache = cache_dir()
    out_dir = args.out or cache / "packs"
    built = []
    for dataset_id in args.datasets:
        b = build_zip(dataset_id, out_dir, cache)
        print(f"{b['id']}: {b['files']} файлів, {b['size_bytes'] / 1e6:.1f} МБ, sha256 {b['sha256']}")
        built.append(b)
    if args.publish:
        publish(built, args.version, args.repo)
        update_manifest(built, args.version, args.repo)
        print(f"опубліковано в Release {args.version}; {PACKS_FILE.name} оновлено — закомітьте його")
    else:
        print("лише збірка; для публікації додайте --publish")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
