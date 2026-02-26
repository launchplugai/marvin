#!/usr/bin/env python3
"""
Unit tests for Marvin Gateway
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lobby.gateway import MarvinGateway, TRIVIAL_RESPONSES


class TestTrivialResponses:
    """Test that trivial messages get instant canned responses."""

    @pytest.fixture
    def gw(self):
        return MarvinGateway()

    def test_hello(self, gw):
        result = gw.handle_message("test_user", "Hello")
        assert result and len(result) > 0
        assert "rate limit" not in result.lower()

    def test_thanks(self, gw):
        result = gw.handle_message("test_user", "Thanks!")
        assert "welcome" in result.lower()

    def test_ok(self, gw):
        result = gw.handle_message("test_user", "ok")
        assert result and len(result) > 0

    def test_hey(self, gw):
        result = gw.handle_message("test_user", "hey")
        assert "help" in result.lower()


class TestSessionManagement:
    """Test session management."""

    @pytest.fixture
    def gw(self):
        return MarvinGateway()

    def test_new_session(self, gw):
        result = gw.new_session("test_user")
        assert "New session started" in result
        assert "Providers:" in result

    def test_new_session_clears_history(self, gw):
        gw.sessions["test_user"] = [{"role": "user", "content": "old"}]
        gw.new_session("test_user")
        assert "test_user" not in gw.sessions

    def test_status(self, gw):
        result = gw.get_status()
        assert "Marvin Status" in result
        assert "Ollama" in result
        assert "OpenAI" in result


class TestNeverFails:
    """The gateway must NEVER return empty or throw."""

    @pytest.fixture
    def gw(self):
        return MarvinGateway()

    def test_empty_string(self, gw):
        result = gw.handle_message("test_user", "")
        assert result and len(result) > 0

    def test_gibberish(self, gw):
        result = gw.handle_message("test_user", "xkcd qqq zzz bbb nnn")
        assert result and len(result) > 0

    def test_long_message(self, gw):
        result = gw.handle_message("test_user", "a" * 5000)
        assert result and len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
