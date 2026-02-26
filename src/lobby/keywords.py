"""Deterministic keyword registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class KeywordEntry:
    command: str
    response: str
    allows_args: bool
    version: int


class KeywordRegistry:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._registry: Dict[str, KeywordEntry] = {}
        self._load()

    def _load(self) -> None:
        with self._path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        self._registry = {
            entry["command"].strip(): KeywordEntry(
                command=entry["command"].strip(),
                response=entry["response"],
                allows_args=bool(entry.get("allows_args", False)),
                version=int(entry.get("version", 1)),
            )
            for entry in data
        }

    def match(self, text: str) -> Optional[KeywordEntry]:
        normalized = text.strip()
        return self._registry.get(normalized)

    def commands(self) -> Dict[str, KeywordEntry]:
        return dict(self._registry)
