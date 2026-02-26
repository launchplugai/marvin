import os
from pathlib import Path

from lobby.config import LobbyConfig, load_config


def test_load_config_defaults(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("lobby_mode: safe", encoding="utf-8")

    cfg = load_config(path)

    assert isinstance(cfg, LobbyConfig)
    assert cfg.lobby_mode == "safe"
    assert cfg.cb_ollama.fails == 3


def test_env_overrides(monkeypatch, tmp_path):
    source = tmp_path / "config.yml"
    source.write_text("lobby_mode: normal", encoding="utf-8")

    monkeypatch.setenv("CB_OLLAMA_FAILS", "5")
    monkeypatch.setenv("OPENAI_MAX_DAILY_USD", "123.4")

    cfg = load_config(source)

    assert cfg.cb_ollama.fails == 5
    assert cfg.openai_max_daily_usd == 123.4
    assert cfg.lobby_mode == "normal"
