#!/usr/bin/env python3
"""
Unit tests for Context Sync
Phase 1.5: VPS sync with mocked HTTP calls
"""

import pytest
import tempfile
import os
import time
from unittest.mock import patch, MagicMock

from context.sync import ContextSync


class TestContextSync:
    """Test context sync to VPS."""

    @pytest.fixture
    def sync(self):
        """Create temporary sync instance."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        s = ContextSync(db_path=db_path, sync_url="http://localhost:19800/context/sync")
        self._init_tables(s)
        yield s
        s.close()

        try:
            os.unlink(db_path)
        except OSError:
            pass

    def _init_tables(self, s):
        """Create all required context tables."""
        s.conn.executescript("""
            CREATE TABLE IF NOT EXISTS context_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                block_index INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                role TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                raw_content TEXT NOT NULL,
                token_count INTEGER DEFAULT 0,
                tags TEXT,
                metadata TEXT,
                created_at INTEGER NOT NULL
            );
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
            CREATE TABLE IF NOT EXISTS context_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT UNIQUE NOT NULL,
                thread_type TEXT NOT NULL,
                session_ids TEXT NOT NULL,
                content TEXT NOT NULL,
                synthesis_count INTEGER DEFAULT 1,
                model_used TEXT,
                tokens_used INTEGER DEFAULT 0,
                metadata TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
        """)
        s.conn.commit()

    def _seed_data(self, s):
        """Insert test data across all tables."""
        now = int(time.time())

        s.conn.execute("""
            INSERT INTO context_blocks
            (session_id, block_index, timestamp, role, content_hash,
             raw_content, token_count, tags, metadata, created_at)
            VALUES ('sess_1', 0, ?, 'user', 'abc', 'Hello', 2, '[]', '{}', ?)
        """, (now, now))

        s.conn.execute("""
            INSERT INTO context_synthesis
            (session_id, block_range_start, block_range_end, context_level,
             summary, model_used, tags, created_at)
            VALUES ('sess_1', 0, 0, 'high', 'Greeted the system.',
                    'test', '[]', ?)
        """, (now,))

        s.conn.execute("""
            INSERT INTO context_threads
            (thread_id, thread_type, session_ids, content,
             model_used, tokens_used, created_at, updated_at)
            VALUES ('tid_1', 'high_level', '["sess_1"]', 'Overview content.',
                    'test', 0, ?, ?)
        """, (now, now))

        s.conn.commit()

    def test_push_no_data(self, sync):
        """Test: push with empty database returns no_data."""
        result = sync.push()
        assert result["status"] == "no_data"
        assert result["blocks_sent"] == 0

    @patch("context.sync.requests.post")
    def test_push_success(self, mock_post, sync):
        """Test: successful push to VPS."""
        self._seed_data(sync)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = sync.push()

        assert result["status"] == "success"
        assert result["blocks_sent"] == 1
        assert result["syntheses_sent"] == 1
        assert result["threads_sent"] == 1
        assert mock_post.called

    @patch("context.sync.requests.post")
    def test_push_http_error(self, mock_post, sync):
        """Test: HTTP error returns error status."""
        self._seed_data(sync)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        result = sync.push()

        assert result["status"] == "error"
        assert "500" in result["error"]

    @patch("context.sync.requests.post")
    def test_push_timeout(self, mock_post, sync):
        """Test: timeout returns error status."""
        import requests as req
        self._seed_data(sync)

        mock_post.side_effect = req.Timeout("timeout")

        result = sync.push()

        assert result["status"] == "error"
        assert result["error"] == "timeout"

    @patch("context.sync.requests.post")
    def test_push_connection_error(self, mock_post, sync):
        """Test: connection error returns error status."""
        import requests as req
        self._seed_data(sync)

        mock_post.side_effect = req.ConnectionError("refused")

        result = sync.push()

        assert result["status"] == "error"
        assert result["error"] == "connection_error"

    @patch("context.sync.requests.post")
    def test_push_delta_only(self, mock_post, sync):
        """Test: delta push only sends new records."""
        self._seed_data(sync)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # First push
        sync.push()

        # Second push (no new data)
        result = sync.push()
        assert result["status"] == "no_data"

    @patch("context.sync.requests.post")
    def test_push_full(self, mock_post, sync):
        """Test: full push sends everything regardless of last sync."""
        self._seed_data(sync)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # First push
        sync.push()

        # Full push still sends all data
        result = sync.push_full()
        assert result["status"] == "success"
        assert result["blocks_sent"] == 1

    @patch("context.sync.requests.post")
    def test_push_with_auth_token(self, mock_post, sync):
        """Test: auth token is included in request headers."""
        self._seed_data(sync)
        sync.auth_token = "test_token_123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        sync.push()

        call_kwargs = mock_post.call_args
        assert "Authorization" in call_kwargs.kwargs["headers"]
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test_token_123"

    def test_get_sync_status(self, sync):
        """Test: sync status reflects current state."""
        status = sync.get_sync_status()

        assert status["last_sync_at"] == 0
        assert status["sync_count"] == 0

    @patch("context.sync.requests.post")
    def test_sync_count_increments(self, mock_post, sync):
        """Test: sync count increments on each push."""
        self._seed_data(sync)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        sync.push()
        status = sync.get_sync_status()
        assert status["sync_count"] == 1
        assert status["last_sync_status"] == "success"

    def test_export_respects_since(self, sync):
        """Test: export only includes records after timestamp."""
        self._seed_data(sync)

        # Export with future timestamp should return empty
        future = int(time.time()) + 1000
        payload = sync._export_since(future)

        assert len(payload["blocks"]) == 0
        assert len(payload["syntheses"]) == 0
        assert len(payload["threads"]) == 0

        # Export from 0 should return all
        payload = sync._export_since(0)
        assert len(payload["blocks"]) == 1
        assert len(payload["syntheses"]) == 1
        assert len(payload["threads"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
