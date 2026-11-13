"""DEM у форматі PDS: розбір міток і орієнтація проєкцій за dsmap.cat / dsmap_polar.cat.

Тут — синтетичні файли, тож тести не залежать від завантажених даних.
Перевірка на справжніх продуктах LOLA — tests/test_dem_validation.py.
"""

import numpy as np
import pytest

from app.core.dem import CylindricalDem, PolarDem, open_dem, parse_pds_label

CYL_LABEL = """PDS_VERSION_ID = PDS3
/* HEIGHT = (DN * SCALING_FACTOR). */
OBJECT = IMAGE
    LINES                 = {lines}
    LINE_SAMPLES          = {samples}
    SAMPLE_TYPE           = LSB_INTEGER
    SAMPLE_BITS           = 16
    UNIT                  = METER
    SCALING_FACTOR        = 0.5
    OFFSET                = 1737400.
END_OBJECT = IMAGE
OBJECT = IMAGE_MAP_PROJECTION
 MAP_PROJECTION_TYPE          = "SIMPLE CYLINDRICAL"
 MAP_RESOLUTION               = {ppd} <pix/deg>
 CENTER_LATITUDE              = 0 <deg>
 CENTER_LONGITUDE             = 180 <deg>
 LINE_PROJECTION_OFFSET       = {loff} <pix>
 SAMPLE_PROJECTION_OFFSET     = {soff} <pix>
END_OBJECT = IMAGE_MAP_PROJECTION
END
"""

POLAR_LABEL = """PDS_VERSION_ID = PDS3
OBJECT = IMAGE
    LINES                 = {n}
    LINE_SAMPLES          = {n}
    SAMPLE_TYPE           = LSB_INTEGER
    SAMPLE_BITS           = 16
    SCALING_FACTOR        = 0.5
    OFFSET                = 1737400.
END_OBJECT = IMAGE
OBJECT = IMAGE_MAP_PROJECTION
 MAP_PROJECTION_TYPE          = "POLAR STEREOGRAPHIC"
 CENTER_LATITUDE              = -90 <deg>
 CENTER_LONGITUDE             = 0 <deg>
 MAP_SCALE                    = {scale} <m/pix>
 MAXIMUM_LATITUDE             = -80 <deg>
 MINIMUM_LATITUDE             = -90 <deg>
END_OBJECT = IMAGE_MAP_PROJECTION
END
"""


def _write(tmp_path, name, label, data):
    (tmp_path / f"{name}.lbl").write_text(label, encoding="latin-1")
    data.astype("<i2").tofile(tmp_path / f"{name}.img")
    return tmp_path / f"{name}.lbl"


@pytest.fixture
def cyl(tmp_path):
    """1 пікс./град.: DN = 2·(номер стовпця) → висота = номер стовпця (м)."""
    lines, samples = 180, 360
    data = np.tile(np.arange(samples) * 2, (lines, 1))
    lbl = _write(tmp_path, "ldem_1", CYL_LABEL.format(lines=lines, samples=samples, ppd=1, loff=89.5, soff=179.5),
                 data)
    return open_dem(lbl)


def test_label_parsing_strips_units_and_quotes(tmp_path, cyl):
    label = parse_pds_label(tmp_path / "ldem_1.lbl")
    assert label["MAP_PROJECTION_TYPE"] == "SIMPLE CYLINDRICAL"
    assert label["MAP_RESOLUTION"] == "1"
    assert label["OFFSET"] == "1737400."
    assert isinstance(cyl, CylindricalDem)


def test_cylindrical_pixel_centres_follow_dsmap(cyl):
    # dsmap.cat: центр пікселя (SAMPLE=1) — довгота 0,5°; (LINE=1) — широта 89,5°
    line, sample = cyl.pixel(89.5, 0.5)
    assert line == pytest.approx(0.0) and sample == pytest.approx(0.0)
    assert float(cyl(0.0, 0.5)) == pytest.approx(0.0)
    assert float(cyl(0.0, 10.5)) == pytest.approx(10.0)
    assert float(cyl(0.0, -0.5)) == pytest.approx(359.0)  # −0,5° = 359,5° сх.
    assert float(cyl(0.0, 11.0)) == pytest.approx(10.5)  # між пікселями — білінійно


def test_cylindrical_rejects_truncated_file(tmp_path):
    lbl = _write(tmp_path, "ldem_bad", CYL_LABEL.format(lines=180, samples=360, ppd=1, loff=89.5, soff=179.5),
                 np.zeros((10, 10)))
    with pytest.raises(ValueError, match="неповний"):
        _ = open_dem(lbl).data


@pytest.fixture
def polar(tmp_path):
    """Південна полярна: DN = 2·стовпець + 2000·рядок → видно, куди лягає кожен напрямок."""
    n = 200
    rows, cols = np.mgrid[0:n, 0:n]
    lbl = _write(tmp_path, "ldem_80s_test", POLAR_LABEL.format(n=n, scale=1000), cols * 2 + rows * 2000)
    return open_dem(lbl)


def test_polar_orientation_matches_dsmap_polar(polar):
    """dsmap_polar.cat: на півдні 0° — угору від центру, 90° сх. — праворуч."""
    assert isinstance(polar, PolarDem) and polar.south and polar.edge_lat == -80
    c = polar.lines / 2 - 0.5
    line0, sample0 = polar.pixel(-89.0, 0.0)
    line90, sample90 = polar.pixel(-89.0, 90.0)
    assert sample0 == pytest.approx(c) and line0 < c  # 0° — вгору (менший номер рядка)
    assert line90 == pytest.approx(c) and sample90 > c  # 90° сх. — праворуч
    line180, _ = polar.pixel(-89.0, 180.0)
    assert line180 > c


def test_polar_roundtrip_and_scale(polar):
    for lat, lon in ((-85.0, 30.0), (-81.2, -120.0), (-89.99, 179.0)):
        x, y = polar.xy_m(lat, lon)
        la, lo = polar.latlon(x, y)
        assert la == pytest.approx(lat, abs=1e-9)
        assert lo == pytest.approx(lon, abs=1e-9)
    # 1° від полюса ≈ 30,3 км на сфері 1737,4 км (стереографічний масштаб біля полюса ≈ 1)
    x, y = polar.xy_m(-89.0, 0.0)
    assert np.hypot(x, y) == pytest.approx(np.radians(1) * 1_737_400, rel=1e-4)


def test_polar_coverage(polar):
    assert polar.covers(-89.5, 10.0)
    assert not polar.covers(10.0, 10.0)
    assert not polar.covers(-60.0, 0.0)  # поза зображенням 200 × 1 км
