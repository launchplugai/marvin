#!/usr/bin/env python3
"""
Rate Limit Tracker — Provider Health Monitor

Reads rate limit headers from API responses. Tracks provider health.
Triggers automatic buffer switching when providers are stressed.

No polling. No extra API calls. Purely reactive — parses headers we already get.

Health states:
  GREEN  (>20% remaining) — use normally
  YELLOW (5-20%)          — divert low-priority to buffer
  RED    (<5% or 429)     — all traffic to buffer
"""

import re
import time
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import os

logger = logging.getLogger(__name__)


def _now_epoch() -> int:
    return int(time.time())


def _parse_reset_duration(raw: str) -> int:
    """Parse reset time strings into seconds from now.

    Handles:
      - Groq/OpenAI: "2m59.56s", "7.66s", "1h2m3s"
      - ISO datetime: "2026-02-26T12:00:00Z"
      - Plain seconds: "60"
    """
    if not raw:
        return 60  # safe default

    # ISO datetime
    if "T" in raw:
        try:
            reset_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            delta = reset_dt - datetime.now(reset_dt.tzinfo)
            return max(int(delta.total_seconds()), 1)
        except (ValueError, TypeError):
            return 60

    # Duration format: "2m59.56s", "7.66s", "1h2m3s"
    total = 0.0
    h = re.search(r"(\d+)h", raw)
    m = re.search(r"(\d+)m", raw)
    s = re.search(r"([\d.]+)s", raw)
    if h:
        total += int(h.group(1)) * 3600
    if m:
        total += int(m.group(1)) * 60
    if s:
        total += float(s.group(1))
    if total > 0:
        return max(int(total), 1)

    # Plain number
    try:
        return max(int(float(raw)), 1)
    except (ValueError, TypeError):
        return 60


class RateLimitTracker:
    """
    Singleton-style tracker. Updated on every API response.
    Read by routing layer before every request.

    Persists snapshots to SQLite for historical analysis.
    In-memory dict for fast routing decisions.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.expanduser(
                "~/.openclaw/workspace/cache/responses.db"
            )
        self.db_path = db_path
        self._providers = {}  # in-memory: provider_key -> health dict
        self._db = None
        self._ensure_db()

    def _ensure_db(self):
        """Connect to SQLite and ensure table exists."""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=10.0
            )
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tpm_remaining INTEGER,
                    tpm_limit INTEGER,
                    rpm_remaining INTEGER,
                    rpm_limit INTEGER,
                    tokens_remaining INTEGER,
                    tokens_limit INTEGER,
                    time_until_reset INTEGER,
                    metadata TEXT
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ratelimit_timestamp "
                "ON rate_limit_snapshots(timestamp)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ratelimit_provider "
                "ON rate_limit_snapshots(provider)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ratelimit_status "
                "ON rate_limit_snapshots(status)"
            )
            self._db.commit()
        except Exception as e:
            logger.error("RateLimitTracker DB init failed: %s", e)
            self._db = None

    # ── Provider key normalization ──

    def _key(self, provider: str, model: str) -> str:
        key_map = {
            ("openai", "gpt-4o-mini"): "openai_gpt4o_mini",
            ("openai", "gpt-4o"): "openai_gpt4o",
            ("ollama", "llama3.2"): "ollama_llama32",
            ("groq", "llama-3.1-8b-instant"): "groq_llama_8b",
            ("groq", "llama-3.3-70b-versatile"): "groq_llama_70b",
            ("anthropic", "haiku"): "haiku",
            ("anthropic", "opus"): "claude_opus",
            ("moonshot", "kimi-2.5"): "kimi_2_5",
        }
        return key_map.get((provider, model), f"{provider}_{model}")

    # ── Parse headers from any provider ──

    def parse_headers(self, headers: dict, provider: str) -> dict:
        """Normalize rate limit headers from any provider."""
        if provider in ("groq", "openai", "moonshot"):
            remaining_req = int(headers.get("x-ratelimit-remaining-requests", -1))
            limit_req = int(headers.get("x-ratelimit-limit-requests", -1))
            remaining_tok = int(headers.get("x-ratelimit-remaining-tokens", -1))
            limit_tok = int(headers.get("x-ratelimit-limit-tokens", -1))
            reset_req = _parse_reset_duration(
                headers.get("x-ratelimit-reset-requests", "")
            )
            reset_tok = _parse_reset_duration(
                headers.get("x-ratelimit-reset-tokens", "")
            )
        elif provider == "anthropic":
            remaining_req = int(
                headers.get("anthropic-ratelimit-requests-remaining", -1)
            )
            limit_req = int(
                headers.get("anthropic-ratelimit-requests-limit", -1)
            )
            remaining_tok = int(
                headers.get("anthropic-ratelimit-tokens-remaining", -1)
            )
            limit_tok = int(
                headers.get("anthropic-ratelimit-tokens-limit", -1)
            )
            reset_req = _parse_reset_duration(
                headers.get("anthropic-ratelimit-requests-reset", "")
            )
            reset_tok = _parse_reset_duration(
                headers.get("anthropic-ratelimit-tokens-reset", "")
            )
        else:
            return {"health": "unknown"}

        # Health = lowest of request% and token%
        req_pct = (remaining_req / limit_req * 100) if limit_req > 0 else 100
        tok_pct = (remaining_tok / limit_tok * 100) if limit_tok > 0 else 100
        lowest = min(req_pct, tok_pct)

        if lowest > 20:
            health = "green"
        elif lowest > 5:
            health = "yellow"
        else:
            health = "red"

        return {
            "remaining_requests": remaining_req,
            "limit_requests": limit_req,
            "remaining_tokens": remaining_tok,
            "limit_tokens": limit_tok,
            "request_pct": round(req_pct, 1),
            "token_pct": round(tok_pct, 1),
            "reset_seconds": max(reset_req, reset_tok),
            "health": health,
            "bottleneck": "requests" if req_pct < tok_pct else "tokens",
            "updated_at": _now_epoch(),
        }

    # ── Update from API response ──

    def update(self, provider: str, model: str, headers: dict):
        """Called after every successful API response."""
        parsed = self.parse_headers(headers, provider)
        if parsed.get("health") == "unknown":
            return

        key = self._key(provider, model)
        parsed["provider"] = provider
        parsed["model"] = model
        parsed["reset_at"] = _now_epoch() + parsed.get("reset_seconds", 60)
        self._providers[key] = parsed

        self._persist_snapshot(key, model, parsed)
        logger.debug(
            "Rate limit %s: %s (req=%.0f%% tok=%.0f%%)",
            key, parsed["health"], parsed["request_pct"], parsed["token_pct"],
        )

    def update_on_429(self, provider: str, model: str, retry_after: int = 60):
        """Called when we get a 429. Marks provider RED immediately."""
        key = self._key(provider, model)
        reset_at = _now_epoch() + retry_after

        parsed = {
            "remaining_requests": 0,
            "remaining_tokens": 0,
            "limit_requests": 0,
            "limit_tokens": 0,
            "request_pct": 0,
            "token_pct": 0,
            "reset_seconds": retry_after,
            "health": "red",
            "bottleneck": "rate_limited_429",
            "updated_at": _now_epoch(),
            "reset_at": reset_at,
            "provider": provider,
            "model": model,
        }
        self._providers[key] = parsed
        self._persist_snapshot(key, model, parsed)

        logger.warning(
            "429 RATE LIMITED: %s — RED for %ds (resets at %s)",
            key, retry_after,
            datetime.utcfromtimestamp(reset_at).isoformat(),
        )

    # ── Query health ──

    def get_health(self, provider: str, model: str) -> str:
        """Get current health. Auto-upgrades RED→YELLOW if reset time passed."""
        key = self._key(provider, model)
        info = self._providers.get(key)

        if not info:
            return "green"  # no data = assume healthy

        # Auto-recover: if RED and reset time has passed, upgrade to YELLOW
        if info["health"] == "red" and info.get("reset_at"):
            if _now_epoch() >= info["reset_at"]:
                info["health"] = "yellow"
                info["updated_at"] = _now_epoch()
                self._providers[key] = info
                logger.info("Auto-recovered %s: RED → YELLOW", key)

        return info["health"]

    def get_all_health(self) -> dict:
        """Snapshot for envelope. Checks all resets."""
        result = {}
        for key in list(self._providers.keys()):
            info = self._providers[key]
            # Trigger auto-recovery check
            if info["health"] == "red" and info.get("reset_at"):
                if _now_epoch() >= info["reset_at"]:
                    info["health"] = "yellow"
                    info["updated_at"] = _now_epoch()
                    self._providers[key] = info
            result[key] = info["health"]
        return result

    def is_available(self, provider: str, model: str) -> bool:
        """Can we send a request to this provider right now?"""
        health = self.get_health(provider, model)
        return health in ("green", "yellow")

    def should_divert(self, provider: str, model: str, priority: str = "normal") -> bool:
        """Should this request be diverted to a buffer?

        In YELLOW: only low/normal priority diverts.
        In RED: everything diverts.
        """
        health = self.get_health(provider, model)
        if health == "green":
            return False
        if health == "red":
            return True
        # yellow
        return priority in ("low", "normal")

    def seconds_until_available(self, provider: str, model: str) -> int:
        """How long until this provider might be available again?"""
        key = self._key(provider, model)
        info = self._providers.get(key)
        if not info or info["health"] != "red":
            return 0
        reset_at = info.get("reset_at", 0)
        remaining = reset_at - _now_epoch()
        return max(remaining, 0)

    # ── Persistence ──

    def _persist_snapshot(self, key: str, model: str, parsed: dict):
        """Write snapshot to SQLite for historical tracking."""
        if not self._db:
            return
        try:
            self._db.execute(
                """
                INSERT INTO rate_limit_snapshots
                (timestamp, provider, model, status,
                 tpm_remaining, tpm_limit, rpm_remaining, rpm_limit,
                 tokens_remaining, tokens_limit, time_until_reset)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_epoch(),
                    key,
                    model,
                    parsed["health"],
                    parsed.get("remaining_tokens", 0),
                    parsed.get("limit_tokens", 0),
                    parsed.get("remaining_requests", 0),
                    parsed.get("limit_requests", 0),
                    parsed.get("remaining_tokens", 0),
                    parsed.get("limit_tokens", 0),
                    parsed.get("reset_seconds", 0),
                ),
            )
            self._db.commit()
        except Exception as e:
            logger.warning("Rate limit snapshot persistence failed: %s", e)

    # ── Diagnostics ──

    def get_stats(self) -> dict:
        """Full health dashboard."""
        all_health = self.get_all_health()
        red_count = sum(1 for h in all_health.values() if h == "red")
        yellow_count = sum(1 for h in all_health.values() if h == "yellow")

        stats = {
            "providers_tracked": len(self._providers),
            "providers_red": red_count,
            "providers_yellow": yellow_count,
            "providers_green": len(all_health) - red_count - yellow_count,
            "all_health": all_health,
        }

        # Add per-provider detail
        for key, info in self._providers.items():
            if info["health"] == "red":
                stats[f"{key}_resets_in"] = self.seconds_until_available(
                    info.get("provider", ""), info.get("model", "")
                )

        return stats

    def get_recent_snapshots(self, provider_key: str = None, limit: int = 20) -> list:
        """Query historical snapshots from SQLite."""
        if not self._db:
            return []
        try:
            if provider_key:
                cursor = self._db.execute(
                    "SELECT * FROM rate_limit_snapshots WHERE provider = ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (provider_key, limit),
                )
            else:
                cursor = self._db.execute(
                    "SELECT * FROM rate_limit_snapshots "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Snapshot query failed: %s", e)
            return []


# ── Module-level singleton ──
_tracker_instance = None


def get_tracker(db_path: str = None) -> RateLimitTracker:
    """Get or create the singleton tracker."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = RateLimitTracker(db_path)
    return _tracker_instance
