"""Автоматична підготовка даних (app/services/bootstrap.py, I7): стан, запуск у фоні, блокування, помилки.

Справжні скрипти збирання не запускаються й нічого не завантажують: замість них — підставна команда,
що пише потрібні файли в тимчасовий каталог.
"""

import sys
import time

import pytest

from app.config import TestConfig
from app.services import bootstrap
from tests.test_contracts import api_validator, assert_valid

FAKE = bootstrap.Dataset("fake", "Підставний набір", "tools/none.py", "0 Б", ("a.txt", "b.txt"), "CACHE_DIR", "fake")


def _config(tmp_path):
    return {"CACHE_DIR": tmp_path, "TEMP_DIR": tmp_path / "temp"}


def _writer(code: str):
    return lambda d: [sys.executable, "-c", code]


def _wait(prep, dataset, states, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        st = prep.status_of(dataset)
        if st["state"] in states:
            return st
        time.sleep(0.05)
    raise AssertionError(f"не дочекались {states}: {prep.status_of(dataset)}")


def _ok_command(tmp_path):
    out = tmp_path / "fake"
    code = ("import pathlib; d=pathlib.Path(%r); d.mkdir(parents=True, exist_ok=True); "
            "print('крок 1', flush=True); (d/'a.txt').write_text('1'); (d/'b.txt').write_text('2'); print('готово')"
            % str(out))
    return _writer(code)


def test_missing_then_ready_after_background_run(tmp_path):
    prep = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE], command=_ok_command(tmp_path))
    assert prep.status_of(FAKE)["state"] == "missing"
    assert prep.start(["fake"]) == ["fake"]
    st = _wait(prep, FAKE, {"ready"})
    assert st["state"] == "ready" and st["message"] is None
    assert not (tmp_path / "prepare" / "fake.lock").exists()  # блокування знято
    assert prep.start(["fake"]) == []  # уже готове — повторно не запускається


def test_running_state_shows_last_line(tmp_path):
    out = tmp_path / "fake"
    code = ("import pathlib,time; d=pathlib.Path(%r); d.mkdir(parents=True, exist_ok=True); "
            "print('завантаження частини 3', flush=True); time.sleep(1.5); "
            "(d/'a.txt').write_text('1'); (d/'b.txt').write_text('2')" % str(out))
    prep = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE], command=_writer(code))
    prep.start(["fake"])
    st = _wait(prep, FAKE, {"running"})
    assert st["state"] == "running"
    end = time.time() + 5
    while time.time() < end and prep.status_of(FAKE)["message"] in (None, "запуск…"):
        time.sleep(0.05)
    assert prep.status_of(FAKE)["message"] == "завантаження частини 3"
    assert prep.start(["fake"]) == []  # поки йде — другий запуск не створюється
    _wait(prep, FAKE, {"ready"})


def test_failure_keeps_reason_and_does_not_retry_by_itself(tmp_path):
    code = "import sys; print('немає мережі', flush=True); sys.exit(3)"
    prep = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE], command=_writer(code))
    prep.start(["fake"])
    st = _wait(prep, FAKE, {"failed"})
    assert st["message"] == "немає мережі"
    assert "помилкою" in prep.hint("fake") and "немає мережі" in prep.hint("fake")
    # новий Preparer (інший процес) бачить збережену помилку з диска
    other = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE])
    assert other.status_of(FAKE)["state"] == "failed"


def test_script_that_exits_ok_without_files_is_a_failure(tmp_path):
    prep = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE], command=_writer("print('нічого не зробив')"))
    prep.start(["fake"])
    st = _wait(prep, FAKE, {"failed"})
    assert "файлів набору немає" in st["message"]


def test_missing_script_binary_is_reported(tmp_path):
    prep = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE],
                              command=lambda d: ["/no/such/interpreter-xyz"])
    prep.start(["fake"])
    st = _wait(prep, FAKE, {"failed"})
    assert "не вдалося запустити" in st["message"]


def test_second_process_sees_lock_and_does_not_duplicate(tmp_path):
    import os

    prep = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE], command=_ok_command(tmp_path))
    (tmp_path / "prepare").mkdir()
    (tmp_path / "prepare" / "fake.lock").write_text(str(os.getpid()))  # «інший» живий процес
    assert prep.status_of(FAKE)["state"] == "running"
    assert prep.start(["fake"]) == []


def test_stale_lock_of_dead_process_is_cleared(tmp_path):
    prep = bootstrap.Preparer(_config(tmp_path), datasets=[FAKE], command=_ok_command(tmp_path))
    (tmp_path / "prepare").mkdir()
    (tmp_path / "prepare" / "fake.lock").write_text("2147483646")  # pid, якого немає
    assert prep.status_of(FAKE)["state"] == "missing"
    assert not (tmp_path / "prepare" / "fake.lock").exists()


def test_pid_alive_on_this_platform():
    """Перевірка процесу працює й на Windows, де `os.kill(pid, 0)` кидає OSError (WinError 87)."""
    import os
    import subprocess

    assert bootstrap._pid_alive(os.getpid()) is True
    assert bootstrap._pid_alive(2147483646) is False
    assert bootstrap._pid_alive(0) is False and bootstrap._pid_alive(-5) is False
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    assert bootstrap._pid_alive(finished.pid) is False
    running = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        assert bootstrap._pid_alive(running.pid) is True
    finally:
        running.kill()
        running.wait()


def test_real_datasets_registry_points_to_existing_scripts_and_cache_layout():
    for d in bootstrap.DATASETS:
        assert (bootstrap.ROOT / d.script).is_file(), d.script
        assert d.root_key in ("CACHE_DIR", "TEMP_DIR") and d.ready_files
    assert bootstrap.BY_ID["temperature"].root_key == "TEMP_DIR"
    assert bootstrap.BY_ID["system"].subdir == "system"


# ---------- API ----------
def test_status_endpoint_matches_contract_and_lists_all_datasets(client):
    res = client.get("/api/data/status")
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("DataStatus"), data)
    assert data["auto_prepare"] is False  # у тестах вимкнено
    assert {d["id"] for d in data["datasets"]} == {"temperature", "system", "globe"}
    assert all(d["state"] == "missing" for d in data["datasets"])  # тестовий кеш порожній


def test_prepare_is_refused_when_auto_prepare_is_off(client):
    res = client.post("/api/data/prepare", json={})
    assert res.status_code == 400
    assert_valid(api_validator("Error"), res.get_json())


@pytest.fixture
def enabled_app(tmp_path):
    """Застосунок з увімкненою автопідготовкою, але з підставним Preparer: справжні скрипти не запускаються."""
    from app import create_app

    class Cfg(TestConfig):
        AUTO_PREPARE = False  # create_app не має запускати справжні скрипти
        AUTO_PREPARE_DATASETS = ("system",)
        CACHE_DIR = tmp_path
        TEMP_DIR = tmp_path / "temp"

    app = create_app(Cfg)
    app.extensions["lse_preparer"] = bootstrap.Preparer(
        app.config, datasets=[d for d in bootstrap.DATASETS if d.id == "system"],
        command=_ok_command(tmp_path))
    app.config["AUTO_PREPARE"] = True
    return app


def test_prepare_endpoint_starts_dataset_and_rejects_unknown(enabled_app, tmp_path):
    client = enabled_app.test_client()
    assert client.post("/api/data/prepare", json={"datasets": ["nope"]}).status_code == 400
    assert client.post("/api/data/prepare", json={"surprise": 1}).status_code == 400
    res = client.post("/api/data/prepare", json={"datasets": ["system"]})
    assert res.status_code == 202
    assert_valid(api_validator("DataPrepareResponse"), res.get_json())
    assert res.get_json()["started"] == ["system"]
    prep = enabled_app.extensions["lse_preparer"]
    _wait(prep, prep.datasets["system"], {"failed", "ready"})  # підставна команда файлів system не пише → failed


def test_temperature_503_explains_that_data_is_missing(client):
    res = client.get("/api/temperature?lat=0&lon=0")
    assert res.status_code == 503
    assert "tools/build_temperature_data.py" in res.get_json()["detail"]


def test_autostart_does_nothing_when_disabled(app):
    assert bootstrap.autostart(app) == []


def test_autostart_starts_only_configured_datasets(enabled_app, tmp_path):
    prep = enabled_app.extensions["lse_preparer"]
    assert bootstrap.autostart(enabled_app) == ["system"]
    _wait(prep, prep.datasets["system"], {"failed", "ready"})
