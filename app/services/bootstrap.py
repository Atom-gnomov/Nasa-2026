"""Автоматична підготовка даних NASA (задача I7, PROPOSALS П-11).

Замість ручного `python tools/build_*.py` застосунок сам запускає потрібні скрипти у фоні, показує стан
(`GET /api/data/status`) і продовжує працювати з тим, що вже є. Скрипти збирання вже вміють пропускати
готові завантаження й докачувати перервані (`Range`), тому повторний запуск не починає з нуля.

Принципи:
  • **не блокує сайт** — скрипт іде в окремому процесі, читання його виводу — у потоці-демоні;
  • **один запуск на набір даних** — блокування файлом з pid у `data_cache/prepare/`: другий процес
    сервера (reloader, кілька воркерів) бачить, що робота вже йде, і не дублює завантаження;
  • **чесний стан** — `ready` лише якщо файли справді є; `failed` зберігає останній рядок виводу; прогрес у
    відсотках не вигадуємо (скрипти його не друкують), показуємо останній рядок і час;
  • **без самоповторів** — після помилки автоматичного повтору немає (не довбемо чужий сервер);
    повторити можна `POST /api/data/prepare` або перезапуском.

Керування: `LSE_AUTO_PREPARE=0` вимикає автозапуск (тести й CI); `LSE_AUTO_PREPARE_DATASETS` — які набори
готувати самі (за замовчуванням `temperature,system`; глобус — важчий, вмикається явно).

Режим `LSE_AUTO_PREPARE_MODE` (задача I9): `pack` (за замовчуванням) — спершу готовий пакет оброблених даних із
GitHub Release (`datapack.py`, `app/data/data_packs.json`), `light` — легкий пакет, `full` — лише збірка зі скриптів
із PDS. Якщо пакет ще не опубліковано чи завантаження не вдалось (мережа, контрольна сума), працює збірка зі скрипта.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services import datapack

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Dataset:
    id: str
    label: str
    script: str  # шлях до скрипта від кореня репозиторію
    approx_download: str  # для людини: скільки буде завантажено
    ready_files: tuple[str, ...]  # від каталогу даних набору
    root_key: str  # ключ конфігурації каталогу: CACHE_DIR або TEMP_DIR
    subdir: str = ""  # підкаталог у ньому


DATASETS: tuple[Dataset, ...] = (
    Dataset("temperature", "Температура поверхні (LRO Diviner)", "tools/build_temperature_data.py", "≈ 3,4 ГБ",
            ("temperature.json", "gcp_tbol.npy", "gcp_tbol_filled.npy", "gcp_stats.npz"), "TEMP_DIR"),
    Dataset("system", "3D-ресурси системи Сонце–Земля–Місяць", "tools/build_system_assets.py", "≈ 6 МБ",
            ("system.json", "sun.glb", "earth.jpg"), "CACHE_DIR", "system"),
    Dataset("globe", "Текстури й рельєф глобуса Місяця", "tools/build_globe_textures.py", "≈ 1,3 ГБ і більше",
            ("globe.json", "color.jpg", "height.bin"), "CACHE_DIR", "globe"),
)
BY_ID = {d.id: d for d in DATASETS}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pid_alive(pid: int) -> bool:
    """Чи живий процес із таким pid (для блокування від подвійного запуску).

    POSIX — `os.kill(pid, 0)` лише перевіряє процес. На Windows сигналу 0 немає (`os.kill` кидає `OSError`
    WinError 87/11 замість перевірки), тому там — WinAPI `OpenProcess` + `GetExitCodeProcess`.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_alive_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    error_access_denied = 5
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    if pid > 0xFFFFFFFF:
        return False
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        # процесу немає (ERROR_INVALID_PARAMETER) або він чужий і закритий для нас — тоді він є
        return ctypes.get_last_error() == error_access_denied
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class Preparer:
    """Стан і запуск підготовки даних для однієї конфігурації."""

    def __init__(self, config: dict, datasets: Sequence[Dataset] = DATASETS,
                 command: Callable[[Dataset], list[str]] | None = None,
                 packs: Sequence[dict] | None = None, opener: Callable | None = None) -> None:
        self.config = config
        self.datasets = {d.id: d for d in datasets}
        self.command = command or (lambda d: [sys.executable, str(ROOT / d.script)])
        self.packs = list(packs) if packs is not None else datapack.load_packs()
        self.opener = opener or datapack.urllib.request.urlopen
        self.state_dir = Path(config["CACHE_DIR"]) / "prepare"
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}

    # ---------- стан ----------
    def data_dir(self, d: Dataset) -> Path:
        base = Path(self.config[d.root_key])
        return base / d.subdir if d.subdir else base

    def is_ready(self, d: Dataset) -> bool:
        base = self.data_dir(d)
        return all((base / f).is_file() for f in d.ready_files)

    def _lock_file(self, d: Dataset) -> Path:
        return self.state_dir / f"{d.id}.lock"

    def _status_file(self, d: Dataset) -> Path:
        return self.state_dir / f"{d.id}.json"

    def _running_elsewhere(self, d: Dataset) -> bool:
        lock = self._lock_file(d)
        try:
            pid = int(lock.read_text().strip())
        except (OSError, ValueError):
            return False
        if _pid_alive(pid):
            return True
        lock.unlink(missing_ok=True)  # залишок аварійно завершеного процесу
        return False

    def _saved(self, d: Dataset) -> dict:
        try:
            return json.loads(self._status_file(d).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, d: Dataset, run: dict) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._status_file(d).with_suffix(".tmp")
            tmp.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._status_file(d))
        except OSError:
            pass  # стан лише підказка: помилка запису не має ламати сервер

    def status_of(self, d: Dataset) -> dict:
        info = {"id": d.id, "label": d.label, "approx_download": d.approx_download,
                "command": f"python {d.script}"}
        if self.is_ready(d):
            return {**info, "state": "ready", "message": None, "elapsed_s": None}
        with self._lock:
            run = dict(self._runs.get(d.id) or {})
        if run.get("state") == "running" or (not run and self._running_elsewhere(d)):
            saved = run or self._saved(d)
            elapsed = round(time.time() - saved["started_ts"], 1) if saved.get("started_ts") else None
            return {**info, "state": "running", "message": saved.get("message"), "elapsed_s": elapsed}
        saved = run or self._saved(d)
        if saved.get("state") == "failed":
            return {**info, "state": "failed", "message": saved.get("message"), "elapsed_s": saved.get("elapsed_s")}
        return {**info, "state": "missing", "message": None, "elapsed_s": None}

    @property
    def mode(self) -> str:
        mode = str(self.config.get("AUTO_PREPARE_MODE", "pack")).strip().lower()
        return mode if mode in ("pack", "light", "full") else "pack"

    def status(self, auto_prepare: bool) -> dict:
        return {"auto_prepare": auto_prepare, "mode": self.mode,
                "datasets": [self.status_of(d) for d in self.datasets.values()]}

    def hint(self, dataset_id: str) -> str:
        """Пояснення для відповіді 503: що відбувається з набором даних зараз."""
        d = self.datasets[dataset_id]
        st = self.status_of(d)
        if st["state"] == "running":
            return f"Дані «{d.label}» готуються ({d.approx_download}); спробуйте пізніше"
        if st["state"] == "failed":
            return f"Підготовка даних «{d.label}» завершилась помилкою: {st['message']}; запустіть python {d.script}"
        return f"Немає даних «{d.label}»: запустіть python {d.script}"

    # ---------- запуск ----------
    def start(self, ids: Sequence[str]) -> list[str]:
        """Запускає підготовку відсутніх наборів (по одному фоновому процесу); повертає id запущених."""
        started = []
        for dataset_id in ids:
            d = self.datasets[dataset_id]
            if self.is_ready(d) or self._running_elsewhere(d):
                continue
            with self._lock:
                if (self._runs.get(d.id) or {}).get("state") == "running":
                    continue
                if not self._acquire(d):
                    continue
                run = {"state": "running", "started_ts": time.time(), "started_utc": _now(),
                       "message": "запуск…"}
                self._runs[d.id] = run
            threading.Thread(target=self._worker, args=(d, run), daemon=True, name=f"prepare-{d.id}").start()
            started.append(d.id)
        return started

    def _acquire(self, d: Dataset) -> bool:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._lock_file(d), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError:
            return False
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return True

    def _try_pack(self, d: Dataset, run: dict) -> str | None:
        """Спроба взяти готовий пакет (режими pack/light). Повертає повідомлення про успіх; None — іти зі скрипта.

        Причина відкату (немає опублікованого пакета, мережа, контрольна сума) лишається в `run["message"]`.
        """
        if self.mode == "full":
            return None
        variant = "light" if self.mode == "light" else "full"
        pack = datapack.find(self.packs, d.id, variant)
        if pack is None:
            run["message"] = f"готовий пакет «{variant}» ще не опубліковано — збираю зі скрипта"
            self._save(d, run)
            return None

        def progress(done: int, total: int | None) -> None:
            mb = 1024 * 1024
            run["message"] = (f"завантажую пакет {pack['id']}: {done // mb} МБ" +
                              (f" з {total // mb} МБ" if total else ""))
            self._save(d, run)

        try:
            datapack.install(pack, self.data_dir(d), self.state_dir / "packs", progress, self.opener)
        except datapack.PackError as exc:
            run["message"] = f"{exc}; збираю зі скрипта"
            self._save(d, run)
            return None
        if not self.is_ready(d):
            run["message"] = f"після розпакування пакета {pack['id']} файлів набору немає; збираю зі скрипта"
            self._save(d, run)
            return None
        return f"встановлено з пакета {pack['id']} ({pack.get('version', '?')})"

    def _worker(self, d: Dataset, run: dict) -> None:
        last, code = "", None
        try:
            from_pack = self._try_pack(d, run)
            if from_pack:
                last, code = from_pack, 0
                return
            # Дочірній Python друкує в канал у кодуванні системи (на Windows — cp1251), а читаємо UTF-8:
            # просимо UTF-8 явно, інакше українські повідомлення скриптів стають «����».
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
            proc = subprocess.Popen(self.command(d), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", env=env)
            for line in proc.stdout or ():
                line = line.strip()
                if line:
                    last = line[-300:]
                    run["message"] = last
                    self._save(d, run)
            code = proc.wait()
        except OSError as exc:
            last, code = f"не вдалося запустити скрипт: {exc}", -1
        finally:
            elapsed = round(time.time() - run["started_ts"], 1)
            if code == 0 and self.is_ready(d):
                run.update(state="done", message=last, elapsed_s=elapsed, finished_utc=_now())
                self._status_file(d).unlink(missing_ok=True)
            else:
                reason = last or f"скрипт завершився з кодом {code}"
                if code == 0:
                    reason = f"скрипт завершився, але файлів набору немає ({last})"
                run.update(state="failed", message=reason, elapsed_s=elapsed, finished_utc=_now())
                self._save(d, run)
            self._lock_file(d).unlink(missing_ok=True)


# ---------- Інтеграція з Flask ----------
def preparer(app) -> Preparer:
    """Один Preparer на застосунок (зберігає запущені фонові роботи в `app.extensions`)."""
    if "lse_preparer" not in app.extensions:
        app.extensions["lse_preparer"] = Preparer(app.config)
    return app.extensions["lse_preparer"]


def autostart(app) -> list[str]:
    """Запускає підготовку наборів з `AUTO_PREPARE_DATASETS`, якщо `AUTO_PREPARE` увімкнено."""
    if not app.config.get("AUTO_PREPARE"):
        return []
    ids = [i for i in app.config.get("AUTO_PREPARE_DATASETS", ()) if i in BY_ID]
    return preparer(app).start(ids)
