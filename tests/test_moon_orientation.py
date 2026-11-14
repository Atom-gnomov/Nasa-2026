"""M7: орієнтація Місяця з ядер NAIF DE440 (PCK) як опція поряд із моделлю IAU 2015 (docs/MATH.md, §3).

Ядра (~13 МБ) у git не зберігаються: тести з ними пропускаються, якщо `python tools/download_kernels.py` не запускали.
"""

from datetime import datetime, timezone

import numpy as np
import pytest

from app.core import frames
from app.core import moon_orientation as mo

HAVE_KERNELS = all((mo.kernel_dir() / name).is_file() for name in mo.KERNELS)
needs_kernels = pytest.mark.skipif(not HAVE_KERNELS, reason="ядра NAIF не завантажено (tools/download_kernels.py)")


def _angle_deg(a, b):
    d = np.einsum("...ij,...kj->...ik", a, b)
    return np.degrees(np.arccos(np.clip((np.trace(d, axis1=-2, axis2=-1) - 1) / 2, -1, 1)))


def test_default_is_iau(monkeypatch):
    monkeypatch.delenv("LSE_MOON_ORIENTATION", raising=False)
    fn, label = mo.load()
    assert fn is frames.icrf_to_moon_me and label == mo.IAU_LABEL


def test_pck_without_kernels_falls_back_to_iau(tmp_path, monkeypatch):
    monkeypatch.setenv("LSE_KERNEL_DIR", str(tmp_path))
    fn, label = mo.load("pck")
    assert fn is frames.icrf_to_moon_me
    assert label.startswith(mo.IAU_LABEL) and "PCK недоступний" in label and "download_kernels" in label


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        mo.load("spice")


def test_kernel_registry_points_to_naif():
    assert set(mo.KERNELS) == {mo.PCK_FILE, mo.FRAME_FILE}
    assert all(url.startswith("https://naif.jpl.nasa.gov/") and url.endswith(name) for name, url in mo.KERNELS.items())


@needs_kernels
def test_pck_agrees_with_iau_within_model_accuracy():
    # MATH §3: точність IAU ~0,01°; ME і PA відрізняються на ~0,02° — PCK уже переведено в ME
    pck = mo.PckMoonOrientation()
    jd = 2451545.0 + np.linspace(9131, 21915, 200)  # 2025–2060, TDB
    ang = _angle_deg(pck(jd), frames.icrf_to_moon_me(jd))
    assert ang.max() < 0.01
    m = pck(jd)
    assert np.abs(np.einsum("nij,nkj->nik", m, m) - np.eye(3)).max() < 1e-12
    assert np.allclose(np.linalg.det(m), 1.0)


@needs_kernels
def test_pck_shapes_segments_and_coverage():
    pck = mo.PckMoonOrientation()
    assert pck(2461587.5).shape == (3, 3)
    assert pck(np.full((2, 4), 2461587.5)).shape == (2, 4, 3, 3)
    # дати з різних сегментів ядра (1600, 2027, 2500 рр.) — без помилок і узгоджені з IAU на ~0,1°
    jd = np.array([2305448.0, 2461587.5, 2634166.0])
    assert _angle_deg(pck(jd), frames.icrf_to_moon_me(jd)).max() < 0.1
    lo, hi = pck.coverage_jd
    assert lo < 2305448.0 and hi > 2634166.0
    with pytest.raises(ValueError):
        pck(hi + 10)


@needs_kernels
def test_ephemeris_with_pck_changes_vectors_by_metres():
    pytest.importorskip("naif_de440")
    from app.core.ephemeris import Ephemeris

    iau, pck = Ephemeris(moon_orientation_mode="iau"), Ephemeris(moon_orientation_mode="pck")
    assert pck.moon_orientation_source == mo.PCK_LABEL
    t = iau.time(datetime(2027, 7, 1, tzinfo=timezone.utc))
    a, b = iau.earth_vector_me(t), pck.earth_vector_me(t)
    ang = np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1)))
    assert 0 < ang < 0.01  # сотні метрів на поверхні — у межах точності IAU
    lat_a, lon_a = frames.vector_to_latlon(a)
    lat_b, lon_b = frames.vector_to_latlon(b)
    assert abs(lat_a - lat_b) < 0.01 and abs(lon_a - lon_b) < 0.01


def test_meta_reports_orientation(client):
    pytest.importorskip("naif_de440")
    data = client.get("/api/meta").get_json()
    assert data["moon_orientation"].startswith(("IAU 2015", "NAIF DE440"))
