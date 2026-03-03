#!/usr/bin/env python3
"""
Unit tests for Marvin Rate Limiter
Phase 1 Day 4: Header parsing, health tracking, fallback selection
"""

import pytest
import tempfile
import os

from rate_limiter.headers import parse_rate_limit_headers, parse_reset_time
from rate_limiter.tracker import RateLimitTracker


class TestHeaderParsing:
    """Test rate limit header parsing across providers."""

    def test_groq_headers_green(self):
        """Groq with plenty of capacity -> green."""
        headers = {
            "x-ratelimit-limit-requests": "14400",
            "x-ratelimit-remaining-requests": "14370",
            "x-ratelimit-reset-requests": "2m59.56s",
            "x-ratelimit-limit-tokens": "6000",
            "x-ratelimit-remaining-tokens": "5997",
            "x-ratelimit-reset-tokens": "7.66s",
        }
        result = parse_rate_limit_headers(headers, "groq")

        assert result["health"] == "green"
        assert result["remaining_requests"] == 14370
        assert result["remaining_tokens"] == 5997
        assert result["request_pct"] > 90
        assert result["token_pct"] > 90

    def test_groq_headers_yellow(self):
        """Groq with 10% remaining -> yellow."""
        headers = {
            "x-ratelimit-limit-requests": "14400",
            "x-ratelimit-remaining-requests": "1440",
            "x-ratelimit-limit-tokens": "6000",
            "x-ratelimit-remaining-tokens": "600",
        }
        result = parse_rate_limit_headers(headers, "groq")

        assert result["health"] == "yellow"

    def test_groq_headers_red(self):
        """Groq with <5% remaining -> red."""
        headers = {
            "x-ratelimit-limit-requests": "14400",
            "x-ratelimit-remaining-requests": "100",
            "x-ratelimit-limit-tokens": "6000",
            "x-ratelimit-remaining-tokens": "50",
        }
        result = parse_rate_limit_headers(headers, "groq")

        assert result["health"] == "red"

    def test_anthropic_headers(self):
        """Anthropic uses different header names."""
        headers = {
            "anthropic-ratelimit-requests-limit": "1000",
            "anthropic-ratelimit-requests-remaining": "800",
            "anthropic-ratelimit-tokens-limit": "100000",
            "anthropic-ratelimit-tokens-remaining": "90000",
        }
        result = parse_rate_limit_headers(headers, "anthropic")

        assert result["health"] == "green"
        assert result["remaining_requests"] == 800
        assert result["remaining_tokens"] == 90000

    def test_openai_headers(self):
        """OpenAI uses same format as Groq."""
        headers = {
            "x-ratelimit-limit-requests": "500",
            "x-ratelimit-remaining-requests": "450",
            "x-ratelimit-limit-tokens": "40000",
            "x-ratelimit-remaining-tokens": "35000",
        }
        result = parse_rate_limit_headers(headers, "openai")

        assert result["health"] == "green"

    def test_health_uses_lower_percentage(self):
        """Health should use the LOWER of request% and token%."""
        headers = {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "900",  # 90% -> green
            "x-ratelimit-limit-tokens": "10000",
            "x-ratelimit-remaining-tokens": "100",  # 1% -> red
        }
        result = parse_rate_limit_headers(headers, "groq")

        assert result["health"] == "red"
        assert result["bottleneck"] == "tokens"

    def test_unknown_provider(self):
        """Unknown provider returns unknown health."""
        result = parse_rate_limit_headers({}, "unknown_provider")
        assert result["health"] == "unknown"

    def test_missing_headers_default_green(self):
        """Missing headers default to 100% (green)."""
        result = parse_rate_limit_headers({}, "groq")
        assert result["health"] == "green"

    def test_case_insensitive_headers(self):
        """Header keys should be case-insensitive."""
        headers = {
            "X-RateLimit-Limit-Requests": "1000",
            "X-RateLimit-Remaining-Requests": "500",
            "X-RateLimit-Limit-Tokens": "10000",
            "X-RateLimit-Remaining-Tokens": "5000",
        }
        result = parse_rate_limit_headers(headers, "groq")
        assert result["health"] == "green"
        assert result["remaining_requests"] == 500


class TestResetTimeParsing:
    """Test reset time format parsing."""

    def test_groq_duration_format(self):
        """Parse Groq's "2m59.56s" format."""
        result = parse_reset_time("2m59.56s")
        assert "T" in result  # ISO format

    def test_seconds_only(self):
        """Parse "7.66s" format."""
        result = parse_reset_time("7.66s")
        assert "T" in result

    def test_iso_passthrough(self):
        """ISO datetime should pass through unchanged."""
        iso = "2026-03-01T14:30:00+00:00"
        result = parse_reset_time(iso)
        assert result == iso

    def test_empty_string(self):
        """Empty string returns empty."""
        assert parse_reset_time("") == ""

    def test_hours_minutes_seconds(self):
        """Parse "1h2m3s" format."""
        result = parse_reset_time("1h2m3s")
        assert "T" in result


class TestRateLimitTracker:
    """Test the RateLimitTracker state machine."""

    @pytest.fixture
    def tracker(self):
        """Create in-memory tracker (no DB)."""
        return RateLimitTracker()

    @pytest.fixture
    def tracker_with_db(self):
        """Create tracker with temp SQLite DB."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        t = RateLimitTracker(db_path)
        yield t
        t.close()
        try:
            os.unlink(db_path)
        except OSError:
            pass

    def test_default_health_is_green(self, tracker):
        """Unknown providers default to green (optimistic)."""
        assert tracker.get_health("kimi_2_5") == "green"

    def test_update_from_headers(self, tracker):
        """Update health from response headers."""
        headers = {
            "x-ratelimit-limit-requests": "14400",
            "x-ratelimit-remaining-requests": "14000",
            "x-ratelimit-limit-tokens": "6000",
            "x-ratelimit-remaining-tokens": "5500",
        }
        tracker.update("groq", "llama-3.1-8b-instant", headers)

        assert tracker.get_health("groq_llama_8b") == "green"

    def test_429_sets_red(self, tracker):
        """429 response immediately sets provider to red."""
        tracker.update_on_429("groq", "llama-3.1-8b-instant", retry_after=60)

        assert tracker.get_health("groq_llama_8b") == "red"
        info = tracker.get_provider_info("groq_llama_8b")
        assert info["remaining_requests"] == 0
        assert info["retry_after"] == 60

    def test_get_all_health(self, tracker):
        """Snapshot of all tracked providers."""
        headers = {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "900",
            "x-ratelimit-limit-tokens": "10000",
            "x-ratelimit-remaining-tokens": "9000",
        }
        tracker.update("groq", "llama-3.1-8b-instant", headers)
        tracker.update_on_429("anthropic", "haiku", 30)

        health = tracker.get_all_health()
        assert health["groq_llama_8b"] == "green"
        assert health["haiku"] == "red"

    def test_get_best_available_prefers_primary(self, tracker):
        """Returns preferred if healthy."""
        headers = {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "900",
            "x-ratelimit-limit-tokens": "10000",
            "x-ratelimit-remaining-tokens": "9000",
        }
        tracker.update("moonshot", "kimi-2.5", headers)

        best = tracker.get_best_available("kimi_2_5", ["groq_llama_70b", "claude_opus"])
        assert best == "kimi_2_5"

    def test_get_best_available_falls_back(self, tracker):
        """Falls back when preferred is red."""
        tracker.update_on_429("moonshot", "kimi-2.5", 60)

        best = tracker.get_best_available("kimi_2_5", ["groq_llama_70b", "claude_opus"])
        assert best == "groq_llama_70b"

    def test_get_best_available_all_red(self, tracker):
        """Returns preferred even when all are red."""
        tracker.update_on_429("moonshot", "kimi-2.5", 60)
        tracker.update_on_429("groq", "llama-3.3-70b-versatile", 60)
        tracker.update_on_429("anthropic", "opus", 60)

        best = tracker.get_best_available("kimi_2_5", ["groq_llama_70b", "claude_opus"])
        assert best == "kimi_2_5"

    def test_should_divert_green(self, tracker):
        """Never divert on green."""
        headers = {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "900",
            "x-ratelimit-limit-tokens": "10000",
            "x-ratelimit-remaining-tokens": "9000",
        }
        tracker.update("moonshot", "kimi-2.5", headers)

        assert tracker.should_divert("low", "kimi_2_5") is False
        assert tracker.should_divert("high", "kimi_2_5") is False

    def test_should_divert_yellow_low_priority(self, tracker):
        """Yellow + low priority -> divert."""
        headers = {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "100",  # 10% -> yellow
            "x-ratelimit-limit-tokens": "10000",
            "x-ratelimit-remaining-tokens": "1000",
        }
        tracker.update("moonshot", "kimi-2.5", headers)

        assert tracker.should_divert("low", "kimi_2_5") is True
        assert tracker.should_divert("normal", "kimi_2_5") is True

    def test_should_divert_yellow_high_priority(self, tracker):
        """Yellow + high priority -> stay on primary."""
        headers = {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "100",  # 10% -> yellow
            "x-ratelimit-limit-tokens": "10000",
            "x-ratelimit-remaining-tokens": "1000",
        }
        tracker.update("moonshot", "kimi-2.5", headers)

        assert tracker.should_divert("high", "kimi_2_5") is False
        assert tracker.should_divert("critical", "kimi_2_5") is False

    def test_should_divert_red_always(self, tracker):
        """Red -> always divert, any priority."""
        tracker.update_on_429("moonshot", "kimi-2.5", 60)

        assert tracker.should_divert("low", "kimi_2_5") is True
        assert tracker.should_divert("high", "kimi_2_5") is True
        assert tracker.should_divert("critical", "kimi_2_5") is True

    def test_provider_key_normalization(self):
        """Known provider+model pairs map to expected keys."""
        assert RateLimitTracker._provider_key("groq", "llama-3.1-8b-instant") == "groq_llama_8b"
        assert RateLimitTracker._provider_key("anthropic", "haiku") == "haiku"
        assert RateLimitTracker._provider_key("anthropic", "opus") == "claude_opus"
        assert RateLimitTracker._provider_key("moonshot", "kimi-2.5") == "kimi_2_5"
        # Unknown falls back to provider_model
        assert RateLimitTracker._provider_key("newco", "v1") == "newco_v1"

    def test_db_persistence(self, tracker_with_db):
        """Snapshots are persisted to SQLite."""
        headers = {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "900",
            "x-ratelimit-limit-tokens": "10000",
            "x-ratelimit-remaining-tokens": "9000",
        }
        tracker_with_db.update("groq", "llama-3.1-8b-instant", headers)

        # Query DB directly
        import sqlite3
        conn = sqlite3.connect(tracker_with_db.db_path)
        rows = conn.execute("SELECT * FROM rate_limit_snapshots").fetchall()
        conn.close()

        assert len(rows) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
