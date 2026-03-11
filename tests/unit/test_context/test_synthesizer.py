#!/usr/bin/env python3
"""
Unit tests for Context Synthesizer
Phase 1.5: Thread re-synthesis logic
"""

import pytest
import tempfile
import os
import json
from unittest.mock import patch, MagicMock

from context.synthesizer import ContextSynthesizer


class TestContextSynthesizer:
    """Test thread synthesis logic."""

    @pytest.fixture
    def synthesizer(self):
        """Create temporary synthesizer instance."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        synth = ContextSynthesizer(db_path=db_path, groq_api_key=None)
        yield synth
        synth.close()

        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.fixture
    def synthesizer_with_key(self):
        """Create synthesizer with fake API key."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        synth = ContextSynthesizer(db_path=db_path, groq_api_key="fake_key")
        yield synth
        synth.close()

        try:
            os.unlink(db_path)
        except OSError:
            pass

    def _seed_syntheses(self, synth, session_id="sess_1"):
        """Insert test context_synthesis records."""
        # Need the context_synthesis table
        synth.conn.executescript("""
            CREATE TABLE IF NOT EXISTS context_synthesis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                block_range_start INTEGER NOT NULL,
                block_range_end INTEGER NOT NULL,
                context_level TEXT NOT NULL,
                summary TEXT NOT NULL,
                model_used TEXT,
                tokens_input INTEGER DEFAULT 0,
                tokens_output INTEGER DEFAULT 0,
                tags TEXT,
                metadata TEXT,
                created_at INTEGER NOT NULL
            );
        """)

        synth.conn.execute("""
            INSERT INTO context_synthesis
            (session_id, block_range_start, block_range_end, context_level,
             summary, model_used, tags, created_at)
            VALUES (?, 0, 5, 'high', 'Goal: deploy app. Decision: use Docker.',
                    'fallback', '["deploy"]', 1700000000)
        """, (session_id,))

        synth.conn.execute("""
            INSERT INTO context_synthesis
            (session_id, block_range_start, block_range_end, context_level,
             summary, model_used, tags, created_at)
            VALUES (?, 0, 5, 'low', 'Changed docker-compose.yml. Ran docker build.',
                    'fallback', '["docker"]', 1700000000)
        """, (session_id,))

        synth.conn.commit()

    def test_synthesize_no_data(self, synthesizer):
        """Test: no syntheses returns empty dict."""
        results = synthesizer.synthesize_threads()
        assert results == {}

    def test_synthesize_with_data(self, synthesizer):
        """Test: synthesizes threads from stored syntheses."""
        self._seed_syntheses(synthesizer)

        results = synthesizer.synthesize_threads()

        assert "high_level" in results
        assert "low_level" in results
        assert results["high_level"]["session_count"] == 1
        assert len(results["high_level"]["content"]) > 0

    def test_synthesize_stores_threads(self, synthesizer):
        """Test: threads are persisted to database."""
        self._seed_syntheses(synthesizer)
        synthesizer.synthesize_threads()

        threads = synthesizer.get_threads()
        assert len(threads) == 2

        types = {t["thread_type"] for t in threads}
        assert types == {"high_level", "low_level"}

    def test_synthesize_multiple_sessions(self, synthesizer):
        """Test: threads span multiple sessions."""
        self._seed_syntheses(synthesizer, "sess_1")
        self._seed_syntheses(synthesizer, "sess_2")

        results = synthesizer.synthesize_threads()

        assert results["high_level"]["session_count"] == 2

    def test_synthesize_idempotent(self, synthesizer):
        """Test: re-running synthesis updates (not duplicates) threads."""
        self._seed_syntheses(synthesizer)

        synthesizer.synthesize_threads()
        synthesizer.synthesize_threads()

        threads = synthesizer.get_threads()
        assert len(threads) == 2  # Still 2, not 4

        # synthesis_count should be 2
        for thread in threads:
            assert thread["synthesis_count"] == 2

    def test_get_threads_filtered(self, synthesizer):
        """Test: threads can be filtered by type."""
        self._seed_syntheses(synthesizer)
        synthesizer.synthesize_threads()

        high = synthesizer.get_threads(thread_type="high_level")
        low = synthesizer.get_threads(thread_type="low_level")

        assert len(high) == 1
        assert high[0]["thread_type"] == "high_level"
        assert len(low) == 1
        assert low[0]["thread_type"] == "low_level"

    def test_thread_id_deterministic(self, synthesizer):
        """Test: same inputs produce same thread ID."""
        tid1 = synthesizer._thread_id("high_level", ["sess_1", "sess_2"])
        tid2 = synthesizer._thread_id("high_level", ["sess_1", "sess_2"])
        assert tid1 == tid2

    def test_thread_id_varies_by_type(self, synthesizer):
        """Test: different types produce different IDs."""
        tid_high = synthesizer._thread_id("high_level", ["sess_1"])
        tid_low = synthesizer._thread_id("low_level", ["sess_1"])
        assert tid_high != tid_low

    def test_thread_id_varies_by_sessions(self, synthesizer):
        """Test: different sessions produce different IDs."""
        tid1 = synthesizer._thread_id("high_level", ["sess_1"])
        tid2 = synthesizer._thread_id("high_level", ["sess_1", "sess_2"])
        assert tid1 != tid2

    @patch("context.synthesizer.requests.post")
    def test_synthesize_via_llm(self, mock_post, synthesizer_with_key):
        """Test: LLM synthesis with mocked Groq."""
        self._seed_syntheses(synthesizer_with_key)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Synthesized: deployed app with Docker"}}],
            "usage": {"total_tokens": 150},
        }
        mock_post.return_value = mock_response

        results = synthesizer_with_key.synthesize_threads()

        assert "high_level" in results
        assert results["high_level"]["model"] == "llama-3.1-8b-instant"
        assert mock_post.called

    @patch("context.synthesizer.requests.post")
    def test_synthesize_llm_failure_fallback(self, mock_post, synthesizer_with_key):
        """Test: LLM failure triggers fallback concatenation."""
        self._seed_syntheses(synthesizer_with_key)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        results = synthesizer_with_key.synthesize_threads()

        assert "high_level" in results
        assert results["high_level"]["model"] == "fallback_concat"

    def test_fallback_deduplicates_lines(self, synthesizer):
        """Test: fallback synthesis deduplicates repeated lines."""
        text = "Line A\nLine B\nLine A\nLine C\nLine B"
        result = synthesizer._synthesize_fallback(text, "high")
        lines = result["content"].split("\n")
        # Should have unique lines only
        stripped = [l.strip() for l in lines if l.strip()]
        assert len(stripped) == len(set(stripped))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
