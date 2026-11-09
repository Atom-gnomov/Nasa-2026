"""Налаштування застосунку."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATA_DIR = BASE_DIR / "data"
    # Каталог для великих файлів (ефемериди SPICE, DEM). Не комітиться.
    CACHE_DIR = Path(os.environ.get("LSE_CACHE_DIR", BASE_DIR.parent / "data_cache"))
    JSON_SORT_KEYS = False


class TestConfig(Config):
    TESTING = True
