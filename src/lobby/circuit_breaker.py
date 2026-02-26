"""Simple circuit breaker state store."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class BreakerState:
    failures: int = 0
    tripped_until: float = 0.0
    last_error: Optional[str] = None

    def reset(self) -> None:
        self.failures = 0
        self.tripped_until = 0.0
        self.last_error = None


class CircuitBreakerStore:
    def __init__(self) -> None:
        self._store: Dict[str, BreakerState] = {}

    def _get(self, key: str) -> BreakerState:
        if key not in self._store:
            self._store[key] = BreakerState()
        return self._store[key]

    def can_attempt(self, key: str) -> bool:
        state = self._get(key)
        return time.time() >= state.tripped_until

    def record_success(self, key: str) -> None:
        state = self._get(key)
        state.reset()

    def record_failure(self, key: str, ttl_sec: int, max_failures: int, error: Optional[str] = None) -> None:
        state = self._get(key)
        state.failures += 1
        state.last_error = error
        if state.failures >= max_failures:
            state.tripped_until = time.time() + ttl_sec
            state.failures = 0

    def get_state(self, key: str) -> BreakerState:
        return self._get(key)
