"""Tests for the LLM router (tier mapping and escalation logic)."""

from src.router.llm_router import TIER_MAP, ESCALATION, LLMRouter


def test_tier_mapping():
    assert TIER_MAP["trivial"] == "ollama"
    assert TIER_MAP["status_check"] == "ollama"
    assert TIER_MAP["how_to"] == "ollama"
    assert TIER_MAP["debugging"] == "groq"
    assert TIER_MAP["feature_work"] == "groq"


def test_escalation_chain():
    assert ESCALATION["ollama"] == "groq"
    assert ESCALATION["groq"] == "claude"
    assert ESCALATION["claude"] is None


def test_router_has_all_backends():
    router = LLMRouter()
    assert "ollama" in router.backends
    assert "groq" in router.backends
    assert "claude" in router.backends
