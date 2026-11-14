"""Завантаження ядер NAIF для точної орієнтації Місяця (задача M7; docs/MATH.md, §3).

    python tools/download_kernels.py            # у data_cache/kernels (або LSE_KERNEL_DIR)
    python tools/download_kernels.py --force    # завантажити наново

Файли (≈ 13 МБ разом) — з офіційного сервера NAIF (naif.jpl.nasa.gov):
    moon_pa_de440_200625.bpc — орієнтація головних осей Місяця з DE440 (фізична лібрація), 1550–2650;
    moon_de440_250416.tf     — кадри MOON_PA_DE440 → MOON_ME_DE440_ME421.
Після завантаження ввімкніть: LSE_MOON_ORIENTATION=pck. Ефемериди DE440 (планети) дає пакет naif-de440.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.moon_orientation import KERNELS, kernel_dir  # noqa: E402


def download(target: Path, force: bool = False) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    done = []
    for name, url in KERNELS.items():
        path = target / name
        if path.is_file() and path.stat().st_size > 0 and not force:
            print(f"вже є: {path}")
            done.append(path)
            continue
        tmp = path.with_suffix(path.suffix + ".part")
        print(f"завантаження {url} …", flush=True)
        with urllib.request.urlopen(url, timeout=120) as res, open(tmp, "wb") as f:  # noqa: S310 — лише https NAIF
            while chunk := res.read(1 << 20):
                f.write(chunk)
        tmp.replace(path)
        print(f"готово: {path} ({path.stat().st_size / 1e6:.1f} МБ)")
        done.append(path)
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=None, help="каталог ядер (за замовчуванням LSE_KERNEL_DIR)")
    parser.add_argument("--force", action="store_true", help="завантажити наново")
    args = parser.parse_args()
    download(args.dir or kernel_dir(), args.force)
    print("Увімкніть точну орієнтацію: LSE_MOON_ORIENTATION=pck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
