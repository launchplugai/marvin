#!/usr/bin/env python3
"""
Unit tests for Context Compressor
Phase 1.5: Compression pipeline with mocked Groq calls
"""

import pytest
import tempfile
import os
import json
from unittest.mock import patch, MagicMock

from context.capture import ConversationBlock
from context.compressor import ContextCompressor, SynthesisResult


def _make_block(session_id="sess_1", index=0, role="user", content="test"):
    """Helper to create test blocks."""
    return ConversationBlock(
        session_id=session_id,
        block_index=index,
        timestamp=1700000000 + index,
        role=role,
        content_hash="abc123",
        raw_content=content,
        token_count=len(content) // 4,
        tags=["test"],
        metadata={},
    )


class TestContextCompressor:
    """Test compression pipeline."""

    @pytest.fixture
    def compressor(self):
        """Create temporary compressor instance."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        comp = ContextCompressor(db_path=db_path, groq_api_key=None)
        yield comp
        comp.close()

        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.fixture
    def compressor_with_key(self):
        """Create compressor with a fake API key."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        comp = ContextCompressor(db_path=db_path, groq_api_key="fake_key")
        yield comp
        comp.close()

        try:
            os.unlink(db_path)
        except OSError:
            pass

    def test_compress_empty_blocks(self, compressor):
        """Test: empty block list returns empty results."""
        results = compressor.compress_session("sess_1", [])
        assert results == []

    def test_compress_fallback_produces_results(self, compressor):
        """Test: compression works without API key (fallback mode)."""
        blocks = [
            _make_block(content="I decided to deploy the app to production."),
            _make_block(index=1, role="assistant", content="Deployed. Changed config/settings.py file."),
        ]

        results = compressor.compress_session("sess_1", blocks)

        assert len(results) == 2
        assert results[0].context_level == "high"
        assert results[1].context_level == "low"
        assert results[0].model_used == "fallback_extractive"
        assert results[1].model_used == "fallback_extractive"
        assert len(results[0].summary) > 0
        assert len(results[1].summary) > 0

    def test_compress_stores_to_sqlite(self, compressor):
        """Test: compression results are stored in database."""
        blocks = [
            _make_block(content="Goal: build a new feature"),
            _make_block(index=1, role="assistant", content="Created /src/feature.py"),
        ]

        compressor.compress_session("sess_1", blocks)

        # Verify storage
        syntheses = compressor.get_session_syntheses("sess_1")
        assert len(syntheses) == 2
        assert syntheses[0]["context_level"] in ("high", "low")

    def test_compress_stores_block_range(self, compressor):
        """Test: block range is correctly recorded."""
        blocks = [
            _make_block(index=0, content="First message"),
            _make_block(index=1, content="Second message"),
            _make_block(index=2, content="Third message"),
        ]

        results = compressor.compress_session("sess_1", blocks)

        for result in results:
            assert result.block_range_start == 0
            assert result.block_range_end == 2

    def test_compress_with_level_filter(self, compressor):
        """Test: syntheses can be filtered by level."""
        blocks = [_make_block(content="Decided to refactor the code")]

        compressor.compress_session("sess_1", blocks)

        high = compressor.get_session_syntheses("sess_1", level="high")
        low = compressor.get_session_syntheses("sess_1", level="low")

        assert len(high) == 1
        assert high[0]["context_level"] == "high"
        assert len(low) == 1
        assert low[0]["context_level"] == "low"

    @patch("context.compressor.requests.post")
    def test_compress_via_llm_success(self, mock_post, compressor_with_key):
        """Test: LLM compression with mocked Groq response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "- Goal: deploy app\n- Decision: use Docker"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
        mock_post.return_value = mock_response

        blocks = [
            _make_block(content="Let's deploy the app using Docker"),
            _make_block(index=1, role="assistant", content="I'll set up Docker compose"),
        ]

        results = compressor_with_key.compress_session("sess_1", blocks)

        assert len(results) == 2
        # At least one should use the LLM model
        models = [r.model_used for r in results]
        assert "llama-3.1-8b-instant" in models
        assert mock_post.called

    @patch("context.compressor.requests.post")
    def test_compress_llm_failure_falls_back(self, mock_post, compressor_with_key):
        """Test: LLM failure triggers fallback."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        blocks = [_make_block(content="Deploy the application")]

        results = compressor_with_key.compress_session("sess_1", blocks)

        assert len(results) == 2
        for result in results:
            assert result.model_used == "fallback_extractive"

    @patch("context.compressor.requests.post")
    def test_compress_llm_timeout_falls_back(self, mock_post, compressor_with_key):
        """Test: Groq timeout triggers fallback."""
        import requests as req
        mock_post.side_effect = req.Timeout("timeout")

        blocks = [_make_block(content="Build a new feature")]

        results = compressor_with_key.compress_session("sess_1", blocks)

        assert len(results) == 2
        for result in results:
            assert result.model_used == "fallback_extractive"

    def test_extract_tags_from_blocks(self, compressor):
        """Test: tags are collected from all blocks."""
        blocks = [
            _make_block(content="test"),
            _make_block(index=1, content="test2"),
        ]
        blocks[0].tags = ["deploy", "feature"]
        blocks[1].tags = ["feature", "urgent"]

        tags = compressor._extract_tags(blocks)
        assert tags == ["deploy", "feature", "urgent"]

    def test_blocks_to_text_format(self, compressor):
        """Test: blocks are formatted as [ROLE]: content."""
        blocks = [
            _make_block(role="user", content="Hello"),
            _make_block(index=1, role="assistant", content="Hi there"),
        ]

        text = compressor._blocks_to_text(blocks)
        assert "[USER]: Hello" in text
        assert "[ASSISTANT]: Hi there" in text

    def test_blocks_to_text_truncation(self, compressor):
        """Test: long messages are truncated."""
        blocks = [_make_block(content="x" * 3000)]

        text = compressor._blocks_to_text(blocks)
        assert "... [truncated]" in text
        assert len(text) < 3000


class TestSynthesisResult:
    """Test SynthesisResult dataclass."""

    def test_synthesis_result_creation(self):
        """Test: create a SynthesisResult."""
        result = SynthesisResult(
            session_id="sess_1",
            block_range_start=0,
            block_range_end=5,
            context_level="high",
            summary="Project goals established",
            model_used="llama-3.1-8b-instant",
            tokens_input=100,
            tokens_output=20,
            tags=["goals"],
        )

        assert result.session_id == "sess_1"
        assert result.context_level == "high"
        assert result.summary == "Project goals established"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
