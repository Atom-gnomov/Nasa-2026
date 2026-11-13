"""Рельєф з офіційних продуктів LOLA GDR у форматі PDS3 (.IMG + .LBL).

Підтримувані проєкції (параметри читаються з мітки .LBL, формули — з документації PDS):
    SIMPLE CYLINDRICAL  — глобальні LDEM_4/16/64/128 (lrolol_1xxx/catalog/dsmap.cat);
    POLAR STEREOGRAPHIC — полярні LDEM_80S_80M, LDEM_875S_20M тощо (lrolol_1xxx/catalog/dsmap_polar.cat,
                          редакція 2022-01-15: «Longitude 0 extends straight up, 90 East — to the right»).

Значення: HEIGHT = DN · SCALING_FACTOR (метри) відносно сфери OFFSET = 1 737 400 м,
система координат — MEAN EARTH/POLAR AXIS (та сама, що в app.core.frames).
Файли відкриваються через numpy.memmap — у пам'ять нічого не вантажиться.
Класи реалізують протокол HeightSource з app.core.sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

R_MOON_M = 1_737_400.0

_KV = re.compile(r"^\s*([A-Z_^][A-Z0-9_]*)\s*=\s*(.+?)\s*$")


def parse_pds_label(path: str | Path) -> dict[str, str]:
    """Пари KEY = VALUE з мітки PDS3 (без вкладеності; одиниці <..> і лапки прибрано).

    Якщо ключ повторюється в різних OBJECT, лишається перше значення — для потрібних нам ключів
    (LINES, MAP_SCALE, …) це те, що треба.
    """
    out: dict[str, str] = {}
    for line in Path(path).read_text(encoding="latin-1").splitlines():
        if line.strip().startswith("/*"):
            continue
        m = _KV.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        value = re.sub(r"<[^>]*>", "", value).strip().strip('"').strip("'").strip()
        out.setdefault(key, value)
    return out


def _num(label: dict[str, str], key: str) -> float:
    return float(label[key].rstrip("."))


def _bilinear(img: np.ndarray, row: np.ndarray, col: np.ndarray, wrap_cols: bool) -> np.ndarray:
    """Білінійна інтерполяція в нецілих координатах пікселів (0 — центр першого пікселя)."""
    rows, cols = img.shape
    r0 = np.clip(np.floor(row).astype(np.int64), 0, rows - 2)
    fr = np.clip(row - r0, 0.0, 1.0)
    c0 = np.floor(col).astype(np.int64)
    fc = col - c0
    if wrap_cols:
        c0 %= cols
        c1 = (c0 + 1) % cols
    else:
        c0 = np.clip(c0, 0, cols - 2)
        fc = np.clip(col - c0, 0.0, 1.0)
        c1 = c0 + 1
    v00 = img[r0, c0].astype(np.float64)
    v01 = img[r0, c1].astype(np.float64)
    v10 = img[r0 + 1, c0].astype(np.float64)
    v11 = img[r0 + 1, c1].astype(np.float64)
    return (v00 * (1 - fc) + v01 * fc) * (1 - fr) + (v10 * (1 - fc) + v11 * fc) * fr


@dataclass(eq=False)  # хеш за ідентичністю — для кешу масок
class PdsDem:
    """Спільна частина: файл, розміри, масштабування висот."""

    id: str
    path: Path
    lines: int
    samples: int
    scale_factor: float
    resolution_m: float
    version: str
    label: dict

    def _open(self) -> np.ndarray:
        expected = self.lines * self.samples * 2
        if not self.path.exists():
            raise ValueError(f"{self.path.name}: файлу даних немає (неповний набір?)")
        size = self.path.stat().st_size
        if size != expected:
            raise ValueError(f"{self.path.name}: розмір {size} Б, за міткою має бути {expected} Б (файл неповний?)")
        return np.memmap(self.path, dtype="<i2", mode="r", shape=(self.lines, self.samples))

    @property
    def data(self) -> np.ndarray:
        if not hasattr(self, "_data"):
            self._data = self._open()
        return self._data

    def describe(self) -> dict:
        return {"id": self.id, "product_version": self.version, "resolution_m": self.resolution_m,
                "projection": self.label.get("MAP_PROJECTION_TYPE", "")}


@dataclass(eq=False)
class CylindricalDem(PdsDem):
    """Глобальна карта SIMPLE CYLINDRICAL (LDEM_<ppd>)."""

    ppd: float = 0.0
    center_lon: float = 180.0
    line_offset: float = 0.0
    sample_offset: float = 0.0

    def covers(self, lat: float, lon: float) -> bool:
        return -90.0 <= lat <= 90.0

    def covers_many(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        return np.ones(np.shape(lat), dtype=bool)

    def pixel(self, lat, lon) -> tuple[np.ndarray, np.ndarray]:
        """(рядок, стовпець) з нуля, де ціле — центр пікселя (dsmap.cat: LINE/SAMPLE_PROJECTION_OFFSET)."""
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        dlon = (lon - self.center_lon + 180.0) % 360.0 - 180.0
        line = self.line_offset - lat * self.ppd  # 1-базний індекс мінус 1
        sample = self.sample_offset + dlon * self.ppd
        return line, sample

    def __call__(self, lat, lon) -> np.ndarray:
        line, sample = self.pixel(lat, lon)
        return _bilinear(self.data, line, sample, wrap_cols=True) * self.scale_factor


@dataclass(eq=False)
class PolarDem(PdsDem):
    """Полярна стереографічна карта (LDEM_80S_80M тощо)."""

    map_scale_m: float = 0.0
    south: bool = True
    edge_lat: float = -80.0

    # Формули dsmap_polar.cat (2022): X = (I − N/2 − 0.5)·S, Y = (J − N/2 − 0.5)·S·NS,
    # LON = atan2(X, Y), |LAT| = 90 − 2·atan(R / (2·R_moon)); NS = −1 на півдні.
    def xy_m(self, lat, lon) -> tuple[np.ndarray, np.ndarray]:
        colat = np.radians(90.0 - np.abs(np.asarray(lat, dtype=float)))
        r = 2.0 * R_MOON_M * np.tan(colat / 2.0)
        lo = np.radians(np.asarray(lon, dtype=float))
        return r * np.sin(lo), r * np.cos(lo)

    def latlon(self, x_m, y_m) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(x_m, dtype=float)
        y = np.asarray(y_m, dtype=float)
        colat = 2.0 * np.arctan(0.5 * np.hypot(x, y) / R_MOON_M)
        lat = np.degrees(np.pi / 2 - colat) * (-1.0 if self.south else 1.0)
        lon = np.degrees(np.arctan2(x, y))
        return lat, lon

    def pixel(self, lat, lon) -> tuple[np.ndarray, np.ndarray]:
        """(рядок, стовпець) з нуля; ціле — центр пікселя."""
        x, y = self.xy_m(lat, lon)
        ns = -1.0 if self.south else 1.0
        sample = x / self.map_scale_m + self.samples / 2.0 + 0.5 - 1.0
        line = (y / ns) / self.map_scale_m + self.lines / 2.0 + 0.5 - 1.0
        return line, sample

    def covers(self, lat: float, lon: float) -> bool:
        return bool(self.covers_many(np.asarray(lat), np.asarray(lon)))

    def covers_many(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        line, sample = self.pixel(lat, lon)
        hemi = (lat < 0) if self.south else (lat > 0)
        return hemi & (line >= 0.0) & (line <= self.lines - 1) & (sample >= 0.0) & (sample <= self.samples - 1)

    def __call__(self, lat, lon) -> np.ndarray:
        line, sample = self.pixel(lat, lon)
        return _bilinear(self.data, line, sample, wrap_cols=False) * self.scale_factor


def mosaic_height_fn(dems: list[PdsDem]):
    """height_fn(lat, lon) для app.core.horizon.compute_mask: у кожній точці — найдетальніший DEM.

    dems — у порядку від найдетальнішого; останній має покривати все (глобальний).
    """
    def fn(lat, lon):
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        out = np.full(lat.shape, np.nan)
        for dem in dems:
            m = np.isnan(out) & dem.covers_many(lat, lon)
            if np.any(m):
                out[m] = dem(lat[m], lon[m])
        return out
    return fn


def open_dem(lbl_path: str | Path) -> PdsDem:
    """Відкриває DEM за міткою .lbl (файл даних — поруч, .img)."""
    lbl_path = Path(lbl_path)
    label = parse_pds_label(lbl_path)
    img = lbl_path.with_suffix(".img")
    if not img.exists():
        img = lbl_path.with_suffix(".IMG")
    if label.get("SAMPLE_TYPE") not in {"LSB_INTEGER"} or label.get("SAMPLE_BITS", "16") != "16":
        raise ValueError(f"{lbl_path.name}: непідтримуваний тип даних {label.get('SAMPLE_TYPE')}")
    if abs(_num(label, "OFFSET") - R_MOON_M) > 1e-6:
        raise ValueError(f"{lbl_path.name}: опорна сфера {label['OFFSET']} ≠ {R_MOON_M}")
    common = dict(
        id=lbl_path.stem.lower(), path=img, lines=int(_num(label, "LINES")),
        samples=int(_num(label, "LINE_SAMPLES")), scale_factor=_num(label, "SCALING_FACTOR"),
        version=label.get("PRODUCT_VERSION_ID", ""), label=label,
    )
    kind = label.get("MAP_PROJECTION_TYPE", "")
    if kind == "SIMPLE CYLINDRICAL":
        ppd = _num(label, "MAP_RESOLUTION")
        return CylindricalDem(
            **common, resolution_m=2 * np.pi * R_MOON_M / 360.0 / ppd, ppd=ppd,
            center_lon=_num(label, "CENTER_LONGITUDE"),
            line_offset=_num(label, "LINE_PROJECTION_OFFSET"),
            sample_offset=_num(label, "SAMPLE_PROJECTION_OFFSET"),
        )
    if kind == "POLAR STEREOGRAPHIC":
        south = _num(label, "CENTER_LATITUDE") < 0
        edge = _num(label, "MAXIMUM_LATITUDE") if south else _num(label, "MINIMUM_LATITUDE")
        scale = _num(label, "MAP_SCALE")
        return PolarDem(**common, resolution_m=scale, map_scale_m=scale, south=south, edge_lat=edge)
    raise ValueError(f"{lbl_path.name}: непідтримувана проєкція {kind!r}")
