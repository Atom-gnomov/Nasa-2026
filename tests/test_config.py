"""Тестова конфігурація не залежить від даних, зібраних на машині розробника (задача I6)."""

from app.config import Config, TestConfig


def test_test_config_uses_empty_data_directories():
    for name in ("CACHE_DIR", "DEM_DIR", "TEMP_DIR"):
        path = getattr(TestConfig, name)
        assert path != getattr(Config, name), name
        assert not path.exists(), f"{name}: {path} має бути відсутнім, щоб тести не бачили локальних даних"


def test_models_manifest_ignores_locally_built_assets(client):
    """Раніше цей запит бачив справжній data_cache/ і тест падав на машині з готовими 3D-ресурсами."""
    data = client.get("/api/models").get_json()
    assert data["all_available"] is False
    assert len(data["missing"]) == 5
