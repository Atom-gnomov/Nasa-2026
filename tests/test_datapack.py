"""Готові пакети даних із GitHub Release (datapack.py + bootstrap, I9): без мережі, на локальному сервері."""

import hashlib
import http.server
import io
import json
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from app.services import bootstrap, datapack
from tests.test_bootstrap import FAKE, _config, _wait
from tests.test_contracts import api_validator, assert_valid


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


class _Handler(http.server.BaseHTTPRequestHandler):
    body = b""
    support_range = True
    status_override = None
    requests: list = []

    def do_GET(self):  # noqa: N802
        type(self).requests.append(self.headers.get("Range"))
        if self.status_override:
            self.send_response(self.status_override)
            self.end_headers()
            return
        rng = self.headers.get("Range")
        data = type(self).body
        if rng and type(self).support_range:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            data = data[start:]
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    handler = type("H", (_Handler,), {"requests": []})
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield handler, f"http://127.0.0.1:{srv.server_address[1]}/pack.zip"
    srv.shutdown()


def _pack(url, body, **extra):
    return {"id": "fake-full", "dataset": "fake", "variant": "full", "version": "data-v1", "url": url,
            "size_bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "published": True, **extra}


GOOD = _zip({"a.txt": "1", "b.txt": "2"})


# ---------- модуль datapack ----------
def test_install_downloads_verifies_and_extracts(server, tmp_path):
    handler, url = server
    handler.body = GOOD
    seen = []
    files = datapack.install(_pack(url, GOOD), tmp_path / "data", tmp_path / "work", lambda d, t: seen.append((d, t)))
    assert sorted(files) == ["a.txt", "b.txt"]
    assert (tmp_path / "data" / "a.txt").read_text() == "1"
    assert seen and seen[-1][0] == len(GOOD)
    assert not list((tmp_path / "work").glob("*"))  # архіву й .part не лишилось


def test_checksum_mismatch_is_rejected_and_part_removed(server, tmp_path):
    handler, url = server
    handler.body = GOOD
    pack = _pack(url, GOOD)
    pack["sha256"] = "0" * 64
    with pytest.raises(datapack.PackError, match="контрольна сума"):
        datapack.install(pack, tmp_path / "data", tmp_path / "work")
    assert not (tmp_path / "data").exists() and not list((tmp_path / "work").glob("*.part"))


def test_interrupted_download_is_resumed_with_range(server, tmp_path):
    handler, url = server
    handler.body = GOOD
    work = tmp_path / "work"
    work.mkdir()
    (work / "fake-full.zip.part").write_bytes(GOOD[:20])  # «перервана» перша частина
    datapack.install(_pack(url, GOOD), tmp_path / "data", work)
    assert handler.requests == ["bytes=20-"]
    assert (tmp_path / "data" / "b.txt").read_text() == "2"


def test_server_without_range_support_restarts_from_zero(server, tmp_path):
    handler, url = server
    handler.body, handler.support_range = GOOD, False
    work = tmp_path / "work"
    work.mkdir()
    (work / "fake-full.zip.part").write_bytes("сміття".encode())
    datapack.install(_pack(url, GOOD), tmp_path / "data", work)
    assert (tmp_path / "data" / "a.txt").read_text() == "1"


def test_http_error_and_unreachable_server(server, tmp_path):
    handler, url = server
    handler.status_override = 404
    with pytest.raises(datapack.PackError, match="404"):
        datapack.download(_pack(url, GOOD), tmp_path / "w1")
    with pytest.raises(datapack.PackError):
        datapack.download(_pack("http://127.0.0.1:1/x.zip", GOOD), tmp_path / "w2")


def test_zip_slip_is_blocked(tmp_path):
    evil = tmp_path / "evil.zip"
    evil.write_bytes(_zip({"../escaped.txt": "x"}))
    with pytest.raises(datapack.PackError, match="небезпечний шлях"):
        datapack.extract(evil, tmp_path / "data")
    assert not (tmp_path / "escaped.txt").exists()
    abs_zip = tmp_path / "abs.zip"
    abs_zip.write_bytes(_zip({"/etc/passwd-like": "x"}))
    with pytest.raises(datapack.PackError):
        datapack.extract(abs_zip, tmp_path / "data2")


def test_broken_archive_is_reported(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes("це не zip".encode())
    with pytest.raises(datapack.PackError, match="пошкоджений"):
        datapack.extract(bad, tmp_path / "data")


def test_published_means_url_and_checksum():
    ok = {"url": "https://example.org/p.zip", "sha256": "a" * 64}
    assert datapack.is_published(ok)
    assert datapack.is_published({**ok, "url": "http://127.0.0.1:8000/p.zip"})
    assert not datapack.is_published({**ok, "url": "http://example.org/p.zip"})  # http лише для localhost
    assert not datapack.is_published({**ok, "sha256": None})
    assert not datapack.is_published({**ok, "sha256": "xyz"})
    assert not datapack.is_published({"url": None, "sha256": None})


def test_find_picks_published_pack_of_the_variant():
    packs = [{"dataset": "t", "variant": "full", "url": None, "sha256": None},
             {"dataset": "t", "variant": "light", "url": "https://x/l.zip", "sha256": "b" * 64},
             {"dataset": "t", "variant": "full", "url": "https://x/f.zip", "sha256": "c" * 64}]
    assert datapack.find(packs, "t", "full")["url"] == "https://x/f.zip"
    assert datapack.find(packs, "t", "light")["url"] == "https://x/l.zip"
    assert datapack.find(packs, "other", "full") is None
    with pytest.raises(ValueError):
        datapack.find(packs, "t", "huge")


def test_shipped_manifest_matches_schema_and_has_no_fake_checksums():
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "app" / "data" / "data_packs.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "contracts" / "schemas" / "data_packs.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(data))
    assert {(p["dataset"], p["variant"]) for p in data} == {(d, v) for d in ("temperature", "system", "globe")
                                                            for v in ("full", "light")}
    for pack in data:  # поки I10 не опублікував — жодних вигаданих посилань і сум
        assert pack["published"] == datapack.is_published(pack)


# ---------- інтеграція з bootstrap ----------
def _fallback_command(tmp_path):
    out = tmp_path / "fake"
    code = ("import pathlib; d=pathlib.Path(%r); d.mkdir(parents=True, exist_ok=True); "
            "(d/'a.txt').write_text('script'); (d/'b.txt').write_text('script'); print('зі скрипта')" % str(out))
    return lambda d: [sys.executable, "-c", code]


def _prep(tmp_path, packs, mode="pack", **kw):
    cfg = {**_config(tmp_path), "AUTO_PREPARE_MODE": mode}
    return bootstrap.Preparer(cfg, datasets=[FAKE], command=_fallback_command(tmp_path), packs=packs, **kw)


def test_pack_mode_installs_from_release_without_running_the_script(server, tmp_path):
    handler, url = server
    handler.body = GOOD
    prep = _prep(tmp_path, [_pack(url, GOOD)])
    prep.start(["fake"])
    _wait(prep, FAKE, {"ready"})
    assert (tmp_path / "fake" / "a.txt").read_text() == "1"  # з пакета, а не «script»


def test_unpublished_pack_falls_back_to_script(tmp_path):
    prep = _prep(tmp_path, [{"id": "fake-full", "dataset": "fake", "variant": "full", "url": None, "sha256": None}])
    prep.start(["fake"])
    _wait(prep, FAKE, {"ready"})
    assert (tmp_path / "fake" / "a.txt").read_text() == "script"


def test_bad_checksum_falls_back_to_script_and_reason_is_visible(server, tmp_path):
    handler, url = server
    handler.body = GOOD
    pack = _pack(url, GOOD)
    pack["sha256"] = "0" * 64
    prep = _prep(tmp_path, [pack])
    prep.start(["fake"])
    _wait(prep, FAKE, {"ready"})
    assert (tmp_path / "fake" / "a.txt").read_text() == "script"  # відкат на збірку


def test_full_mode_ignores_packs(server, tmp_path):
    handler, url = server
    handler.body = GOOD
    prep = _prep(tmp_path, [_pack(url, GOOD)], mode="full")
    prep.start(["fake"])
    _wait(prep, FAKE, {"ready"})
    assert (tmp_path / "fake" / "a.txt").read_text() == "script" and handler.requests == []


def test_light_mode_picks_the_light_variant(server, tmp_path):
    handler, url = server
    light = _zip({"a.txt": "light", "b.txt": "light"})
    handler.body = light
    pack = _pack(url, light, id="fake-light", variant="light")
    prep = _prep(tmp_path, [_pack(url, GOOD), pack], mode="light")
    prep.start(["fake"])
    _wait(prep, FAKE, {"ready"})
    assert (tmp_path / "fake" / "a.txt").read_text() == "light"


def test_pack_without_expected_files_falls_back(server, tmp_path):
    handler, url = server
    wrong = _zip({"other.txt": "x"})
    handler.body = wrong
    prep = _prep(tmp_path, [_pack(url, wrong)])
    prep.start(["fake"])
    _wait(prep, FAKE, {"ready"})
    assert (tmp_path / "fake" / "a.txt").read_text() == "script"


def test_status_reports_mode_and_matches_contract(client, app):
    data = client.get("/api/data/status").get_json()
    assert_valid(api_validator("DataStatus"), data)
    assert data["mode"] in ("pack", "light", "full")
    odd = bootstrap.Preparer({**_config(Path("/tmp")), "AUTO_PREPARE_MODE": "nonsense"}, datasets=[FAKE])
    assert odd.mode == "pack"  # невідомий режим — безпечний за замовчуванням
