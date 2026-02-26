#!/usr/bin/env python3
"""
Unit tests for Marvin Lobby (Intent Classifier)
Phase 1 Day 3
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lobby.classifier import LobbyClassifier, IntentType


class TestLobbyClassifier:
    """Test intent classification with keyword and LLM methods."""
    
    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return LobbyClassifier()
    
    def test_keyword_classification_status_check(self, classifier):
        """Test: keyword matching detects status checks."""
        messages = [
            "What's the status?",
            "Is the app running?",
            "Health check",
            "Uptime?",
            "How is BetApp?",
        ]
        
        for msg in messages:
            result = classifier.classify(msg)
            assert result.intent == IntentType.STATUS_CHECK.value
            assert result.method == "keyword"
            assert result.confidence >= 0.9
    
    def test_keyword_classification_how_to(self, classifier):
        """Test: keyword matching detects how-to questions."""
        messages = [
            "How do I run tests?",
            "What's the command?",
            "How to deploy?",
            "Guide to X?",
        ]
        
        for msg in messages:
            result = classifier.classify(msg)
            assert result.intent == IntentType.HOW_TO.value
            assert result.method == "keyword"
            assert result.cacheable is True
    
    def test_keyword_classification_debugging(self, classifier):
        """Test: keyword matching detects debugging requests."""
        messages = [
            "Fix this error",
            "Why is it broken?",
            "Debug this issue",
            "App crashed",
        ]
        
        for msg in messages:
            result = classifier.classify(msg)
            assert result.intent == IntentType.DEBUGGING.value
            assert result.cacheable is False
    
    def test_keyword_classification_trivial(self, classifier):
        """Test: keyword matching detects trivial messages."""
        messages = [
            "Thanks!",
            "Got it",
            "Cool!",
            "Nice job",
        ]
        
        for msg in messages:
            result = classifier.classify(msg)
            assert result.intent == IntentType.TRIVIAL.value
            assert result.cacheable is True
    
    def test_cacheability_correct(self, classifier):
        """Test: cacheable flag set correctly per intent."""
        cacheable_intents = {
            IntentType.STATUS_CHECK: 60,
            IntentType.HOW_TO: 3600,
            IntentType.TRIVIAL: 86400,
        }
        
        non_cacheable = {
            IntentType.CODE_REVIEW: "Review my PR",
            IntentType.DEBUGGING: "Fix this error",
            IntentType.FEATURE_WORK: "Build X feature",
        }
        
        # Test cacheable
        for intent, ttl in cacheable_intents.items():
            config = classifier.intents[intent]
            assert config["cacheable"] is True
            assert config["ttl"] == ttl
        
        # Test non-cacheable
        for intent, msg in non_cacheable.items():
            config = classifier.intents[intent]
            assert config["cacheable"] is False
            assert config["ttl"] is None
    
    def test_fallback_classification(self, classifier):
        """Test: fallback works for unknown messages."""
        # Message that won't match keywords or be classified correctly
        result = classifier.classify("xyzzy qwerty asdf jkl zxcv bnm")
        
        assert result.method == "fallback"
        assert result.confidence <= 0.6
    
    def test_stats(self, classifier):
        """Test: stats reflect classifier configuration."""
        stats = classifier.get_stats()

        assert "openai_model" in stats
        assert "ollama_url" in stats
        assert "ollama_model" in stats
        assert "intents_available" in stats
        assert stats["intents_available"] == len(IntentType)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
