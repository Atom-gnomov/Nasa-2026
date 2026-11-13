"""Налаштування застосунку."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


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


class TestConfig(Config):
    TESTING = True
    # Модульні тести не залежать від завантажених DEM (гладка сфера); рельєф перевіряє
    # tests/test_dem_validation.py, вмикаючи справжній DEM_DIR явно.
    DEM_DIR = BASE_DIR.parent / "tests" / "_no_dem"
    TEMP_DIR = BASE_DIR.parent / "tests" / "_no_temp"
