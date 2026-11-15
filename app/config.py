"""Налаштування застосунку."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Підвантажує KEY=VALUE з файлу .env (не в git) у змінні середовища; наявні змінні не перезаписує.

    Так налаштування й секрети лежать лише на машині, де запущено сайт, а не в репозиторії.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR.parent / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATA_DIR = BASE_DIR / "data"
    # Каталог для великих файлів (ефемериди SPICE, DEM). Не комітиться.
    CACHE_DIR = Path(os.environ.get("LSE_CACHE_DIR", BASE_DIR.parent / "data_cache"))
    # Офіційні DEM LOLA (PDS .img + .lbl); завантажує tools/build_globe_textures.py
    DEM_DIR = Path(os.environ.get("LSE_DEM_DIR", CACHE_DIR / "globe" / "src"))
    # Температура LRO Diviner (GCP, PRP); готує tools/build_temperature_data.py
    TEMP_DIR = Path(os.environ.get("LSE_TEMP_DIR", CACHE_DIR / "temperature"))
    JSON_SORT_KEYS = False
    # Автоматична підготовка даних NASA у фоні (app/services/bootstrap.py, PROPOSALS П-11);
    # LSE_AUTO_PREPARE=0 вимикає, LSE_AUTO_PREPARE_DATASETS — які набори готувати самі (temperature, system, globe)
    AUTO_PREPARE = os.environ.get("LSE_AUTO_PREPARE", "1").strip().lower() not in ("0", "false", "no", "")
    # Режим підготовки (I9): pack — готовий пакет із GitHub Release (запасний шлях — збірка зі скриптів), light — легкий
    # пакет, full — лише збірка з PDS
    AUTO_PREPARE_MODE = os.environ.get("LSE_AUTO_PREPARE_MODE", "pack").strip().lower()
    AUTO_PREPARE_DATASETS = tuple(
        i.strip() for i in os.environ.get("LSE_AUTO_PREPARE_DATASETS", "temperature,system").split(",") if i.strip())


class TestConfig(Config):
    TESTING = True
    AUTO_PREPARE = False  # тести ніколи не завантажують дані з мережі
    # Модульні тести не залежать від завантажених DEM (гладка сфера); рельєф перевіряє
    # tests/test_dem_validation.py, вмикаючи справжній DEM_DIR явно.
    # Кеш даних теж порожній: тести не бачать локально зібраних 3D-ресурсів і текстур глобуса
    CACHE_DIR = BASE_DIR.parent / "tests" / "_no_cache"
    DEM_DIR = BASE_DIR.parent / "tests" / "_no_dem"
    TEMP_DIR = BASE_DIR.parent / "tests" / "_no_temp"
