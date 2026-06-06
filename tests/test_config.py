"""
tests/test_config.py
Проверка загрузки конфигурации.
"""
from pathlib import Path
import pytest
from src.core.config import load_config, Config


def test_load_config_defaults():
    """Конфиг загружается без ошибок."""
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.app.version
    assert cfg.llm.provider == "ollama"


def test_load_config_types():
    """Типы полей корректны."""
    cfg = load_config()
    assert isinstance(cfg.camera.device_index, int)
    assert isinstance(cfg.voice.stt, dict)
    assert isinstance(cfg.llm.temperature, float)
    assert isinstance(cfg.dental.enable_humor, bool)


def test_load_config_custom_path(tmp_path, monkeypatch):
    """Конфиг грузится из кастомного пути (без влияния .env/переменных)."""
    import yaml
    # env-переменные и .env перекрывают конфиг — для чистоты теста убираем их
    monkeypatch.setattr("src.core.config.load_dotenv", lambda *a, **k: None)
    for var in ("OLLAMA_MODEL", "OLLAMA_HOST", "DIKIDI_BASE_URL",
                "DIKIDI_TOKEN", "DIKIDI_API_KEY", "DIKIDI_COMPANY_ID"):
        monkeypatch.delenv(var, raising=False)
    data = {
        "app": {"name": "Test", "version": "0.0.1"},
        "llm": {"provider": "ollama", "model": "test-model"},
    }
    cfg_file = tmp_path / "settings.yaml"
    cfg_file.write_text(yaml.dump(data), encoding="utf-8")
    cfg = load_config(str(cfg_file))
    assert cfg.app.name == "Test"
    assert cfg.llm.model == "test-model"
