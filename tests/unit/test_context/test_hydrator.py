#!/usr/bin/env python3
"""
Unit tests for Context Hydrator
Phase 1.5: Hydration output format and context loading
"""

import pytest
import tempfile
import os
import json
import time

from context.hydrator import ContextHydrator


class TestContextHydrator:
    """Test context hydration and formatting."""

    @pytest.fixture
    def hydrator(self):
        """Create temporary hydrator instance."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        h = ContextHydrator(db_path=db_path)
        self._init_tables(h)
        yield h
        h.close()

        try:
            os.unlink(db_path)
        except OSError:
            pass

    def _init_tables(self, h):
        """Create all required tables."""
        h.conn.executescript("""
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
        h.conn.commit()

    def _seed_threads(self, h):
        """Insert test threads."""
        now = int(time.time())
        h.conn.execute("""
            INSERT INTO context_threads
            (thread_id, thread_type, session_ids, content,
             synthesis_count, model_used, tokens_used, created_at, updated_at)
            VALUES ('tid_high', 'high_level', '["sess_1"]',
                    'Goal: deploy app. Status: in progress.',
                    1, 'test', 0, ?, ?)
        """, (now, now))

        h.conn.execute("""
            INSERT INTO context_threads
            (thread_id, thread_type, session_ids, content,
             synthesis_count, model_used, tokens_used, created_at, updated_at)
            VALUES ('tid_low', 'low_level', '["sess_1"]',
                    'Changed docker-compose.yml. Added Dockerfile.',
                    1, 'test', 0, ?, ?)
        """, (now, now))
        h.conn.commit()

    def _seed_syntheses(self, h):
        """Insert test syntheses."""
        now = int(time.time())
        h.conn.execute("""
            INSERT INTO context_synthesis
            (session_id, block_range_start, block_range_end, context_level,
             summary, model_used, tags, created_at)
            VALUES ('sess_1', 0, 5, 'high', 'Deployed Docker containers.',
                    'test', '[]', ?)
        """, (now,))

        h.conn.execute("""
            INSERT INTO context_synthesis
            (session_id, block_range_start, block_range_end, context_level,
             summary, model_used, tags, created_at)
            VALUES ('sess_1', 0, 5, 'low', 'Edited config/settings.py.',
                    'test', '[]', ?)
        """, (now,))
        h.conn.commit()

    def _seed_blocks(self, h):
        """Insert test blocks."""
        now = int(time.time())
        h.conn.execute("""
            INSERT INTO context_blocks
            (session_id, block_index, timestamp, role, content_hash,
             raw_content, token_count, tags, metadata, created_at)
            VALUES ('sess_1', 0, ?, 'user', 'abc', 'Deploy the app',
                    4, '[]', '{}', ?)
        """, (now, now))
        h.conn.commit()

    def test_hydrate_empty_database(self, hydrator):
        """Test: empty database returns no-context message."""
        result = hydrator.hydrate()

        assert "formatted" in result
        assert "No conversation context available" in result["formatted"]
        assert result["token_estimate"] >= 1

    def test_hydrate_from_threads(self, hydrator):
        """Test: hydration reads from threads."""
        self._seed_threads(hydrator)

        result = hydrator.hydrate()

        assert "High-Level Context" in result["formatted"]
        assert "Low-Level Context" in result["formatted"]
        assert "deploy app" in result["high_level"]
        assert "docker-compose" in result["low_level"]
        assert "sess_1" in result["sessions_covered"]

    def test_hydrate_high_only(self, hydrator):
        """Test: can request only high-level context."""
        self._seed_threads(hydrator)

        result = hydrator.hydrate(include_high=True, include_low=False)

        assert "High-Level Context" in result["formatted"]
        assert "Low-Level Context" not in result["formatted"]

    def test_hydrate_low_only(self, hydrator):
        """Test: can request only low-level context."""
        self._seed_threads(hydrator)

        result = hydrator.hydrate(include_high=False, include_low=True)

        assert "High-Level Context" not in result["formatted"]
        assert "Low-Level Context" in result["formatted"]

    def test_hydrate_fallback_to_syntheses(self, hydrator):
        """Test: falls back to per-session syntheses if no threads."""
        self._seed_syntheses(hydrator)

        result = hydrator.hydrate()

        assert "Deployed Docker" in result["formatted"] or "Edited config" in result["formatted"]

    def test_hydrate_fallback_to_blocks(self, hydrator):
        """Test: falls back to raw blocks if no threads or syntheses."""
        self._seed_blocks(hydrator)

        result = hydrator.hydrate()

        assert "Deploy the app" in result["formatted"]

    def test_hydrate_token_estimate(self, hydrator):
        """Test: token estimate is reasonable."""
        self._seed_threads(hydrator)

        result = hydrator.hydrate()

        # Should be roughly len(formatted) / 4
        assert result["token_estimate"] > 0
        assert abs(result["token_estimate"] - len(result["formatted"]) // 4) <= 1

    def test_hydrate_generated_at(self, hydrator):
        """Test: generated_at is a recent timestamp."""
        result = hydrator.hydrate()
        now = int(time.time())
        assert abs(result["generated_at"] - now) < 5

    def test_trim_to_budget(self, hydrator):
        """Test: long context is trimmed to budget."""
        hydrator.token_budget = 10  # Very small budget (40 chars)

        self._seed_threads(hydrator)
        result = hydrator.hydrate()

        # Should be trimmed
        assert result["token_estimate"] <= 20  # Some overhead for trim message

    def test_generate_context_md(self, hydrator):
        """Test: CONTEXT.md generation (push mode)."""
        self._seed_threads(hydrator)

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            output_path = f.name

        try:
            result_path = hydrator.generate_context_md(output_path)
            assert os.path.exists(result_path)

            with open(result_path) as f:
                content = f.read()

            assert "# Conversation Context" in content
            assert "High-Level Context" in content
            assert "deploy app" in content
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    def test_get_stats(self, hydrator):
        """Test: stats reflect stored data."""
        self._seed_threads(hydrator)
        self._seed_syntheses(hydrator)
        self._seed_blocks(hydrator)

        stats = hydrator.get_stats()

        assert stats["blocks_stored"] == 1
        assert stats["syntheses_stored"] == 2
        assert stats["threads_stored"] == 2
        assert stats["token_budget"] == 4000

    def test_format_context_structure(self, hydrator):
        """Test: formatted context has expected structure."""
        formatted = hydrator._format_context(
            "Goals: deploy",
            "Changed: settings.py"
        )

        assert "## High-Level Context" in formatted
        assert "## Low-Level Context" in formatted
        assert "---" in formatted
        assert "Goals: deploy" in formatted
        assert "Changed: settings.py" in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
