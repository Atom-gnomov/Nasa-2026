"""Орієнтація Місяця ICRF → MOON_ME: модель IAU 2015 або ядра NAIF DE440 (docs/MATH.md, §3; задача M7).

Варіанти (§3):
    iau — аналітична модель IAU WGCCRE 2015 (`frames.icrf_to_moon_me`), точність ~0,01°, файлів не потребує;
    pck — бінарний PCK `moon_pa_de440_200625.bpc` (фізична лібрація DE440, система головних осей MOON_PA)
          + текстовий кадр `moon_de440_250416.tf` (сталий поворот PA → ME, кадр MOON_ME_DE440_ME421). Точність — метри.

Ядро PCK складається з кількох сегментів за датами (разом 1550–2650). skyfield у `build_frame_named` бере лише
один сегмент, тому кадр будується для кожного сегмента, а дата обирає свій (`build_frame(..., _segment=…)`).
Вибір — змінна `LSE_MOON_ORIENTATION=iau|pck` (за замовчуванням iau), каталог ядер — `LSE_KERNEL_DIR`
(за замовчуванням `data_cache/kernels`); завантаження — `python tools/download_kernels.py`.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.core import frames

ROOT = Path(__file__).resolve().parents[2]
PCK_FILE = "moon_pa_de440_200625.bpc"
FRAME_FILE = "moon_de440_250416.tf"
ME_FRAME = "MOON_ME_DE440_ME421"
KERNELS = {
    PCK_FILE: "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de440_200625.bpc",
    FRAME_FILE: "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_de440_250416.tf",
}
IAU_LABEL = "IAU 2015 (Archinal et al., 2018)"
PCK_LABEL = "NAIF DE440: moon_pa_de440_200625.bpc + moon_de440_250416.tf (MOON_ME_DE440_ME421)"


def kernel_dir() -> Path:
    return Path(os.environ.get("LSE_KERNEL_DIR", ROOT / "data_cache" / "kernels"))


class PckMoonOrientation:
    """ICRF → MOON_ME за ядрами NAIF DE440; дата обирає сегмент PCK."""

    def __init__(self, directory: Path | str | None = None):
        from jplephem.daf import DAF
        from jplephem.pck import PCK
        from skyfield.planetarylib import PlanetaryConstants

        d = Path(directory) if directory else kernel_dir()
        bpc, tf = d / PCK_FILE, d / FRAME_FILE
        missing = [p.name for p in (bpc, tf) if not p.is_file()]
        if missing:
            raise FileNotFoundError(
                f"Немає ядер {', '.join(missing)} у {d}: запустіть python tools/download_kernels.py")
        pc = PlanetaryConstants()
        with open(tf, "rb") as f:
            pc.read_text(f)
        integer = pc.variables[f"FRAME_{ME_FRAME}"]
        relative = pc.variables[f"TKFRAME_{integer}_RELATIVE"]
        pa_code = pc.variables[f"FRAME_{relative}"]
        self._file = open(bpc, "rb")  # noqa: SIM115 — сегменти читають файл ліниво
        segments = [s for s in PCK(DAF(self._file)).segments if s.body == pa_code]
        if not segments:
            raise ValueError(f"{PCK_FILE}: немає сегментів для кадру {relative}")
        self._frames = [(s.initial_jd, s.final_jd, pc.build_frame(integer, _segment=s))
                        for s in sorted(segments, key=lambda s: s.initial_jd)]
        self.coverage_jd = (self._frames[0][0], self._frames[-1][1])

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def __del__(self) -> None:
        file = getattr(self, "_file", None)
        if file is not None and not file.closed:
            file.close()

    def __call__(self, tdb_jd) -> np.ndarray:
        """Матриця(і) ICRF → MOON_ME форми (..., 3, 3), як у frames.icrf_to_moon_me."""
        jd = np.asarray(tdb_jd, dtype=float)
        flat = np.atleast_1d(jd).ravel()
        out = np.empty((flat.size, 3, 3))
        done = np.zeros(flat.size, dtype=bool)
        for start, end, frame in self._frames:
            mask = (flat >= start) & (flat <= end) & ~done
            if mask.any():
                r = frame.rotation_at(SimpleNamespace(tdb=flat[mask]))
                out[mask] = np.moveaxis(np.asarray(r).reshape(3, 3, -1), -1, 0)
                done |= mask
        if not done.all():
            raise ValueError("Дата поза покриттям ядра PCK Місяця (1550–2650)")
        return out.reshape(jd.shape + (3, 3))


def load(mode: str | None = None):
    """(функція орієнтації, опис джерела). mode — iau|pck; без нього — зі змінної LSE_MOON_ORIENTATION.

    Якщо запитано pck, а ядер немає, — модель IAU з поясненням в описі (сайт працює далі).
    """
    mode = (mode or os.environ.get("LSE_MOON_ORIENTATION", "iau")).strip().lower()
    if mode not in ("iau", "pck"):
        raise ValueError("LSE_MOON_ORIENTATION: допустимо iau або pck")
    if mode == "pck":
        try:
            return PckMoonOrientation(), PCK_LABEL
        except (OSError, ValueError, KeyError) as exc:
            return frames.icrf_to_moon_me, f"{IAU_LABEL} — PCK недоступний: {exc}"
    return frames.icrf_to_moon_me, IAU_LABEL
