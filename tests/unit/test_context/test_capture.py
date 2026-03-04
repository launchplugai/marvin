#!/usr/bin/env python3
"""
Unit tests for Conversation Capture
Phase 1.5: Capture format validation and SQLite operations
"""

import pytest
import tempfile
import os

from context.capture import ConversationCapture, ConversationBlock, _content_hash, _estimate_tokens


class TestConversationBlock:
    """Test ConversationBlock dataclass."""

    def test_block_creation(self):
        """Test: create a block with all fields."""
        block = ConversationBlock(
            session_id="sess_abc123",
            block_index=0,
            timestamp=1700000000,
            role="user",
            content_hash="deadbeef",
            raw_content="Hello, world!",
            token_count=3,
            tags=["greeting"],
            metadata={"source": "test"},
        )

        assert block.session_id == "sess_abc123"
        assert block.block_index == 0
        assert block.role == "user"
        assert block.tags == ["greeting"]
        assert block.metadata == {"source": "test"}

    def test_block_to_dict(self):
        """Test: serialization to dict."""
        block = ConversationBlock(
            session_id="sess_1",
            block_index=0,
            timestamp=1700000000,
            role="assistant",
            content_hash="abc",
            raw_content="Hi!",
            tags=["trivial"],
            metadata={"key": "val"},
        )

        d = block.to_dict()
        assert d["session_id"] == "sess_1"
        assert d["role"] == "assistant"
        # tags and metadata are JSON-serialized strings
        assert isinstance(d["tags"], str)
        assert isinstance(d["metadata"], str)
        assert '"trivial"' in d["tags"]

    def test_block_defaults(self):
        """Test: default values for optional fields."""
        block = ConversationBlock(
            session_id="sess_1",
            block_index=0,
            timestamp=1700000000,
            role="user",
            content_hash="abc",
            raw_content="test",
        )

        assert block.token_count == 0
        assert block.tags == []
        assert block.metadata == {}


class TestHelperFunctions:
    """Test module-level helper functions."""

    def test_content_hash_deterministic(self):
        """Test: same content produces same hash."""
        h1 = _content_hash("Hello, world!")
        h2 = _content_hash("Hello, world!")
        assert h1 == h2

    def test_content_hash_different_input(self):
        """Test: different content produces different hash."""
        h1 = _content_hash("Hello")
        h2 = _content_hash("World")
        assert h1 != h2

    def test_content_hash_is_hex(self):
        """Test: hash is a valid hex string."""
        h = _content_hash("test")
        assert len(h) == 64  # SHA256 hex length
        int(h, 16)  # should not raise

    def test_estimate_tokens(self):
        """Test: token estimation is reasonable."""
        # ~4 chars per token
        assert _estimate_tokens("abcd") == 1
        assert _estimate_tokens("a" * 100) == 25
        assert _estimate_tokens("") == 1  # min 1


class TestConversationCapture:
    """Test ConversationCapture SQLite operations."""

    @pytest.fixture
    def capture(self):
        """Create temporary capture instance."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        cap = ConversationCapture(db_path)
        yield cap
        cap.close()

        try:
            os.unlink(db_path)
        except OSError:
            pass

    def test_capture_single_block(self, capture):
        """Test: capture a single message."""
        block = capture.capture("sess_1", "user", "How do I deploy?")

        assert block.session_id == "sess_1"
        assert block.block_index == 0
        assert block.role == "user"
        assert block.raw_content == "How do I deploy?"
        assert block.token_count > 0
        assert len(block.content_hash) == 64

    def test_capture_multiple_blocks_ordered(self, capture):
        """Test: multiple blocks get sequential indices."""
        capture.capture("sess_1", "user", "Question 1")
        capture.capture("sess_1", "assistant", "Answer 1")
        capture.capture("sess_1", "user", "Question 2")

        blocks = capture.get_session_blocks("sess_1")
        assert len(blocks) == 3
        assert blocks[0].block_index == 0
        assert blocks[1].block_index == 1
        assert blocks[2].block_index == 2
        assert blocks[0].role == "user"
        assert blocks[1].role == "assistant"

    def test_capture_with_tags_and_metadata(self, capture):
        """Test: tags and metadata are stored and retrieved."""
        capture.capture(
            "sess_1", "user", "Deploy the app",
            tags=["feature_work", "deploy"],
            metadata={"project": "BetApp"},
        )

        blocks = capture.get_session_blocks("sess_1")
        assert blocks[0].tags == ["feature_work", "deploy"]
        assert blocks[0].metadata == {"project": "BetApp"}

    def test_capture_invalid_role_raises(self, capture):
        """Test: invalid role raises ValueError."""
        with pytest.raises(ValueError, match="Invalid role"):
            capture.capture("sess_1", "invalid_role", "test")

    def test_get_session_blocks_with_limit(self, capture):
        """Test: limit parameter restricts results."""
        for i in range(5):
            capture.capture("sess_1", "user", f"Message {i}")

        blocks = capture.get_session_blocks("sess_1", limit=3)
        assert len(blocks) == 3
        assert blocks[0].block_index == 0

    def test_get_session_blocks_empty(self, capture):
        """Test: empty session returns empty list."""
        blocks = capture.get_session_blocks("nonexistent")
        assert blocks == []

    def test_get_recent_sessions(self, capture):
        """Test: recent sessions are returned in order."""
        capture.capture("sess_old", "user", "Old message")
        capture.capture("sess_new", "user", "New message")

        sessions = capture.get_recent_sessions(limit=5)
        assert len(sessions) == 2
        # Most recent first
        assert sessions[0] == "sess_new"

    def test_get_session_token_count(self, capture):
        """Test: token count sums across blocks."""
        capture.capture("sess_1", "user", "a" * 100)  # ~25 tokens
        capture.capture("sess_1", "assistant", "b" * 200)  # ~50 tokens

        total = capture.get_session_token_count("sess_1")
        assert total == 75

    def test_new_session_id_format(self, capture):
        """Test: generated session IDs have expected format."""
        sid = capture.new_session_id()
        assert sid.startswith("sess_")
        assert len(sid) == 17  # sess_ + 12 hex chars

    def test_multiple_sessions_isolated(self, capture):
        """Test: blocks from different sessions don't mix."""
        capture.capture("sess_a", "user", "Session A")
        capture.capture("sess_b", "user", "Session B")

        blocks_a = capture.get_session_blocks("sess_a")
        blocks_b = capture.get_session_blocks("sess_b")

        assert len(blocks_a) == 1
        assert len(blocks_b) == 1
        assert blocks_a[0].raw_content == "Session A"
        assert blocks_b[0].raw_content == "Session B"

    def test_block_index_per_session(self, capture):
        """Test: block indices are scoped to each session."""
        capture.capture("sess_a", "user", "A1")
        capture.capture("sess_b", "user", "B1")
        capture.capture("sess_a", "user", "A2")

        blocks_a = capture.get_session_blocks("sess_a")
        blocks_b = capture.get_session_blocks("sess_b")

        assert blocks_a[0].block_index == 0
        assert blocks_a[1].block_index == 1
        assert blocks_b[0].block_index == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
