#!/usr/bin/env python3
"""
Unit tests for Rate Limit Tracker
"""

import pytest
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lobby.rate_limiter import RateLimitTracker, _parse_reset_duration


class TestResetDurationParser:
    """Test reset time parsing from various provider formats."""

    def test_groq_seconds(self):
        assert _parse_reset_duration("7.66s") == 7

    def test_groq_minutes_seconds(self):
        result = _parse_reset_duration("2m59.56s")
        assert result == 179  # 2*60 + 59.56 truncated

    def test_plain_seconds(self):
        assert _parse_reset_duration("60") == 60

    def test_empty_string(self):
        assert _parse_reset_duration("") == 60  # safe default

    def test_none(self):
        assert _parse_reset_duration(None) == 60


class TestRateLimitTracker:
    """Test rate limit tracking, health states, and auto-recovery."""

    @pytest.fixture
    def tracker(self, tmp_path):
        """Create tracker with temp DB."""
        db = str(tmp_path / "test_rate.db")
        return RateLimitTracker(db_path=db)

    def test_default_health_is_green(self, tracker):
        """No data = assume healthy."""
        assert tracker.get_health("openai", "gpt-4o-mini") == "green"

    def test_update_green(self, tracker):
        """Healthy headers → green."""
        headers = {
            "x-ratelimit-remaining-requests": "900",
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-tokens": "50000",
            "x-ratelimit-limit-tokens": "60000",
            "x-ratelimit-reset-requests": "30s",
            "x-ratelimit-reset-tokens": "10s",
        }
        tracker.update("openai", "gpt-4o-mini", headers)
        assert tracker.get_health("openai", "gpt-4o-mini") == "green"

    def test_update_yellow(self, tracker):
        """Low remaining → yellow."""
        headers = {
            "x-ratelimit-remaining-requests": "100",
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-tokens": "6000",
            "x-ratelimit-limit-tokens": "60000",
            "x-ratelimit-reset-requests": "30s",
            "x-ratelimit-reset-tokens": "10s",
        }
        tracker.update("openai", "gpt-4o-mini", headers)
        assert tracker.get_health("openai", "gpt-4o-mini") == "yellow"

    def test_update_red(self, tracker):
        """Very low remaining → red."""
        headers = {
            "x-ratelimit-remaining-requests": "10",
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-tokens": "100",
            "x-ratelimit-limit-tokens": "60000",
            "x-ratelimit-reset-requests": "30s",
            "x-ratelimit-reset-tokens": "10s",
        }
        tracker.update("openai", "gpt-4o-mini", headers)
        assert tracker.get_health("openai", "gpt-4o-mini") == "red"

    def test_429_marks_red(self, tracker):
        """429 response → immediate red."""
        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=60)
        assert tracker.get_health("openai", "gpt-4o-mini") == "red"
        assert not tracker.is_available("openai", "gpt-4o-mini")

    def test_429_auto_recovery(self, tracker):
        """After reset time passes, RED → YELLOW."""
        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=1)
        assert tracker.get_health("openai", "gpt-4o-mini") == "red"

        # Wait for reset
        time.sleep(1.1)
        assert tracker.get_health("openai", "gpt-4o-mini") == "yellow"
        assert tracker.is_available("openai", "gpt-4o-mini")

    def test_is_available(self, tracker):
        """Green and yellow are available, red is not."""
        assert tracker.is_available("openai", "gpt-4o-mini")  # default green

        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=300)
        assert not tracker.is_available("openai", "gpt-4o-mini")

    def test_should_divert_green(self, tracker):
        """Green → never divert."""
        assert not tracker.should_divert("openai", "gpt-4o-mini", "low")
        assert not tracker.should_divert("openai", "gpt-4o-mini", "high")

    def test_should_divert_red(self, tracker):
        """Red → always divert."""
        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=300)
        assert tracker.should_divert("openai", "gpt-4o-mini", "low")
        assert tracker.should_divert("openai", "gpt-4o-mini", "high")

    def test_seconds_until_available(self, tracker):
        """Reports seconds until reset."""
        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=120)
        remaining = tracker.seconds_until_available("openai", "gpt-4o-mini")
        assert 118 <= remaining <= 120

    def test_get_all_health(self, tracker):
        """Snapshot of all tracked providers."""
        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=300)
        health = tracker.get_all_health()
        assert "openai_gpt4o_mini" in health
        assert health["openai_gpt4o_mini"] == "red"

    def test_anthropic_headers(self, tracker):
        """Anthropic uses different header format."""
        headers = {
            "anthropic-ratelimit-requests-remaining": "4500",
            "anthropic-ratelimit-requests-limit": "5000",
            "anthropic-ratelimit-tokens-remaining": "40000",
            "anthropic-ratelimit-tokens-limit": "50000",
            "anthropic-ratelimit-requests-reset": "30s",
            "anthropic-ratelimit-tokens-reset": "10s",
        }
        tracker.update("anthropic", "haiku", headers)
        assert tracker.get_health("anthropic", "haiku") == "green"

    def test_persistence(self, tracker):
        """Snapshots are written to SQLite."""
        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=60)
        snapshots = tracker.get_recent_snapshots()
        assert len(snapshots) >= 1
        assert snapshots[0]["status"] == "red"

    def test_stats(self, tracker):
        """Stats reflect tracked state."""
        tracker.update_on_429("openai", "gpt-4o-mini", retry_after=60)
        stats = tracker.get_stats()
        assert stats["providers_tracked"] == 1
        assert stats["providers_red"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
