"""Налаштування застосунку."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Підвантажує KEY=VALUE з файлу .env (не в git) у змінні середовища; наявні змінні не перезаписує.

    Так секрети (ключ до ШІ-сервісу) лежать лише на машині, де запущено сайт, а не в репозиторії.
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
    # Поради ШІ (POST /api/advice): будь-який сервіс з OpenAI-сумісним API. Задаються лише змінними
    # середовища або файлом .env (див. .env.example); без LSE_LLM_BASE_URL поради вимкнені.
    LLM_BASE_URL = os.environ.get("LSE_LLM_BASE_URL") or None
    LLM_MODEL = os.environ.get("LSE_LLM_MODEL") or None
    LLM_API_KEY = os.environ.get("LSE_LLM_API_KEY") or None
    LLM_TIMEOUT_S = float(os.environ.get("LSE_LLM_TIMEOUT_S", "30"))


class TestConfig(Config):
    TESTING = True
    # Модульні тести не залежать від завантажених DEM (гладка сфера); рельєф перевіряє
    # tests/test_dem_validation.py, вмикаючи справжній DEM_DIR явно.
    # Кеш даних теж порожній: тести не бачать локально зібраних 3D-ресурсів і текстур глобуса
    CACHE_DIR = BASE_DIR.parent / "tests" / "_no_cache"
    DEM_DIR = BASE_DIR.parent / "tests" / "_no_dem"
    TEMP_DIR = BASE_DIR.parent / "tests" / "_no_temp"
    # Тести ніколи не ходять у справжній ШІ-сервіс, навіть якщо в середовищі розробника є ключ
    LLM_BASE_URL = None
    LLM_MODEL = None
    LLM_API_KEY = None
