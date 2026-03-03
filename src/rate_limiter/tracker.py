#!/usr/bin/env python3
"""
Rate Limit Tracker
Phase 1 Day 4

Singleton that tracks provider health across all API calls.
Updated on every response. Read by routing layer on every request.
No extra API calls — purely reactive.
"""

import sqlite3
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Any

from .headers import parse_rate_limit_headers

logger = logging.getLogger(__name__)

# Model key normalization
_PROVIDER_KEY_MAP = {
    ("moonshot", "kimi-2.5"): "kimi_2_5",
    ("groq", "moonshotai/kimi-k2-instruct-0905"): "groq_kimi_k2_0905",
    ("groq", "openai/gpt-oss-120b"): "groq_gpt_oss_120b",
    ("groq", "qwen/qwen3-32b"): "groq_qwen3_32b",
    ("groq", "llama-3.1-8b-instant"): "groq_llama_8b",
    ("groq", "llama-3.3-70b-versatile"): "groq_llama_70b",
    ("anthropic", "haiku"): "haiku",
    ("anthropic", "opus"): "claude_opus",
    ("openai", "gpt-4o"): "openai_gpt4o",
}


class RateLimitTracker:
    """
    Tracks rate limit health for all LLM providers.

    Updated on every API response via update().
    Queried by routing layer via get_health() / get_best_available().
    Persists snapshots to SQLite for historical analysis.
    """

    def __init__(self, db_path: str = None):
        """Initialize tracker with optional SQLite persistence."""
        self.providers: Dict[str, Dict[str, Any]] = {}
        self.db_path = db_path
        self._conn = None

        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
            self._ensure_table()

    def _ensure_table(self):
        """Create rate_limit_snapshots table if needed."""
        if not self._conn:
            return
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                remaining_requests INTEGER,
                remaining_tokens INTEGER,
                limit_requests INTEGER,
                limit_tokens INTEGER,
                resets_at TEXT,
                health TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ratelimit_provider_ts
            ON rate_limit_snapshots(provider, timestamp)
        """)
        self._conn.commit()

    def update(self, provider: str, model: str, headers: Dict[str, str]):
        """
        Update health from API response headers.
        Call this after EVERY successful API response.
        """
        parsed = parse_rate_limit_headers(headers, provider)
        key = self._provider_key(provider, model)
        self.providers[key] = parsed

        # Persist snapshot
        if self._conn:
            try:
                self._conn.execute("""
                    INSERT INTO rate_limit_snapshots
                    (timestamp, provider, model, status, remaining_requests,
                     remaining_tokens, limit_requests, limit_tokens, resets_at, health)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    int(time.time()),
                    provider,
                    model,
                    parsed["health"],
                    parsed.get("remaining_requests"),
                    parsed.get("remaining_tokens"),
                    parsed.get("limit_requests"),
                    parsed.get("limit_tokens"),
                    parsed.get("reset_requests", ""),
                    parsed["health"],
                ))
                self._conn.commit()
            except Exception as e:
                logger.warning(f"Failed to persist rate limit snapshot: {e}")

        logger.debug(f"Rate limit updated: {key} -> {parsed['health']}")

    def update_on_429(self, provider: str, model: str, retry_after: int = 60):
        """
        Mark provider as RED on 429 response.
        All traffic should divert immediately.
        """
        key = self._provider_key(provider, model)
        reset_at = (datetime.now(timezone.utc) + timedelta(seconds=retry_after)).isoformat()

        self.providers[key] = {
            "provider": provider,
            "remaining_requests": 0,
            "remaining_tokens": 0,
            "health": "red",
            "bottleneck": "rate_limited",
            "retry_after": retry_after,
            "reset_at": reset_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.warning(f"429 received: {key} -> RED (retry after {retry_after}s)")

        # Persist
        if self._conn:
            try:
                self._conn.execute("""
                    INSERT INTO rate_limit_snapshots
                    (timestamp, provider, model, status, remaining_requests,
                     remaining_tokens, limit_requests, limit_tokens, resets_at, health)
                    VALUES (?, ?, ?, 'red', 0, 0, -1, -1, ?, 'red')
                """, (int(time.time()), provider, model, reset_at))
                self._conn.commit()
            except Exception as e:
                logger.warning(f"Failed to persist 429 snapshot: {e}")

    def get_health(self, provider_key: str) -> str:
        """
        Get current health for a provider key.

        Returns "green" if no data (optimistic default).
        Auto-upgrades from red to yellow if reset time has passed.
        """
        info = self.providers.get(provider_key, {})

        if not info:
            return "green"

        # Check if a previous "red" has expired
        if info.get("health") == "red" and info.get("reset_at"):
            try:
                now = datetime.now(timezone.utc).isoformat()
                if now > info["reset_at"]:
                    info["health"] = "yellow"
                    self.providers[provider_key] = info
                    logger.info(f"{provider_key} reset time passed -> yellow")
            except Exception:
                pass

        return info.get("health", "green")

    def get_all_health(self) -> Dict[str, str]:
        """
        Snapshot of all provider health states.
        Attached to every envelope for routing decisions.
        """
        return {
            key: self.get_health(key)
            for key in self.providers
        }

    def get_best_available(self, preferred: str, fallbacks: list) -> str:
        """
        Find the healthiest provider from preferred + fallback list.

        Args:
            preferred: Primary provider key to try first
            fallbacks: Ordered list of fallback provider keys

        Returns:
            Best available provider key (preferred if healthy)
        """
        if self.get_health(preferred) in ("green", "yellow"):
            return preferred

        for fb in fallbacks:
            if self.get_health(fb) in ("green", "yellow"):
                return fb

        # Everything stressed — return preferred anyway (may get 429, will retry)
        logger.warning(f"All providers stressed, returning preferred: {preferred}")
        return preferred

    def should_divert(self, priority: str, provider_key: str) -> bool:
        """
        In yellow state, only divert low-priority requests.
        Preserves primary capacity for high/critical work.
        """
        health = self.get_health(provider_key)

        if health == "green":
            return False
        if health == "red":
            return True
        # yellow: divert low priority, keep high/critical on primary
        if health == "yellow":
            return priority in ("low", "normal")
        return False

    def get_provider_info(self, provider_key: str) -> Dict[str, Any]:
        """Get full info dict for a provider."""
        return self.providers.get(provider_key, {})

    def close(self):
        """Close SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _provider_key(provider: str, model: str) -> str:
        """Normalize provider + model into a stable key."""
        return _PROVIDER_KEY_MAP.get((provider, model), f"{provider}_{model}")
