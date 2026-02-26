"""Health probes with cached snapshots."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests


@dataclass
class HealthSnapshot:
    checked_at: float
    ollama_ok: bool
    openai_ok: bool
    ollama_error: Optional[str] = None
    openai_error: Optional[str] = None




def default_openai_probe(model_name: str) -> Callable[[], bool]:
    """Return a lightweight OpenAI probe function."""
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("openai package is required for default probe") from exc

    client = OpenAI()

    def _probe() -> bool:
        response = client.responses.create(
            model=model_name,
            input="health-check",
            max_output_tokens=1,
        )
        return bool(response)

    return _probe


class HealthMonitor:
    def __init__(
        self,
        ollama_url: str,
        openai_probe: Callable[[], bool],
        cache_ttl: int = 8,
    ) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._openai_probe = openai_probe
        self._cache_ttl = cache_ttl
        self._snapshot: Optional[HealthSnapshot] = None

    def _probe_ollama(self) -> tuple[bool, Optional[str]]:
        try:
            resp = requests.get(f"{self._ollama_url}/api/version", timeout=2)
            resp.raise_for_status()
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _probe_openai(self) -> tuple[bool, Optional[str]]:
        try:
            alive = self._openai_probe()
            return bool(alive), None if alive else "probe returned false"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def refresh_snapshot(self) -> HealthSnapshot:
        ollama_ok, ollama_err = self._probe_ollama()
        openai_ok, openai_err = self._probe_openai()
        self._snapshot = HealthSnapshot(
            checked_at=time.time(),
            ollama_ok=ollama_ok,
            openai_ok=openai_ok,
            ollama_error=ollama_err,
            openai_error=openai_err,
        )
        return self._snapshot

    def get_snapshot(self) -> HealthSnapshot:
        if self._snapshot is None:
            return self.refresh_snapshot()
        if time.time() - self._snapshot.checked_at > self._cache_ttl:
            return self.refresh_snapshot()
        return self._snapshot
