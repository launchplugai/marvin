"""Configuration loader for the lobby dispatcher."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(frozen=True)
class CircuitBreakerConfig:
    fails: int
    ttl_sec: int


@dataclass(frozen=True)
class LobbyConfig:
    lobby_mode: str
    ollama_base_url: str
    openai_model: str
    openai_max_daily_usd: float
    keyword_commands_path: Path
    cb_ollama: CircuitBreakerConfig
    cb_openai: CircuitBreakerConfig
    health_cache_ttl_sec: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LobbyConfig":
        cb_data = data.get("circuit_breakers", {})
        return cls(
            lobby_mode=data.get("lobby_mode", "normal"),
            ollama_base_url=data.get("ollama_base_url", "http://ollama:11434"),
            openai_model=data.get("openai_model", "gpt-4.1-mini"),
            openai_max_daily_usd=float(data.get("openai_max_daily_usd", 50.0)),
            keyword_commands_path=Path(data.get("keyword_commands_path", "config/keywords.json")),
            cb_ollama=CircuitBreakerConfig(
                fails=int(cb_data.get("ollama", {}).get("fails", 3)),
                ttl_sec=int(cb_data.get("ollama", {}).get("ttl_sec", 60)),
            ),
            cb_openai=CircuitBreakerConfig(
                fails=int(cb_data.get("openai", {}).get("fails", 2)),
                ttl_sec=int(cb_data.get("openai", {}).get("ttl_sec", 30)),
            ),
            health_cache_ttl_sec=int(data.get("health_cache_ttl_sec", 8)),
        )


ENV_MAP = {
    "lobby_mode": "LOBBY_MODE",
    "ollama_base_url": "OLLAMA_BASE_URL",
    "openai_model": "OPENAI_MODEL",
    "openai_max_daily_usd": "OPENAI_MAX_DAILY_USD",
    "keyword_commands_path": "KEYWORD_COMMANDS_PATH",
    "health_cache_ttl_sec": "HEALTH_CACHE_TTL_SEC",
    "circuit_breakers.ollama.fails": "CB_OLLAMA_FAILS",
    "circuit_breakers.ollama.ttl_sec": "CB_OLLAMA_TTL_SEC",
    "circuit_breakers.openai.fails": "CB_OPENAI_FAILS",
    "circuit_breakers.openai.ttl_sec": "CB_OPENAI_TTL_SEC",
}


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def merge_env_overrides(config_data: Dict[str, Any]) -> Dict[str, Any]:
    merged = json.loads(json.dumps(config_data))  # deep copy via json

    for dotted_key, env_name in ENV_MAP.items():
        if env_name not in os.environ:
            continue
        value: Any = os.environ[env_name]
        target = merged
        parts = dotted_key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        last = parts[-1]
        if last in {"fails", "ttl_sec", "health_cache_ttl_sec"}:
            value = int(value)
        elif last == "openai_max_daily_usd":
            value = float(value)
        target[last] = value

    return merged


def load_config(config_path: str | Path = "config/lobby.defaults.yml") -> LobbyConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    data = load_yaml(path)
    data = merge_env_overrides(data)
    return LobbyConfig.from_dict(data)
