#!/usr/bin/env python3
"""
Conversation Capture — Block Extraction and Storage
Phase 1.5

Captures conversation blocks into structured JSON envelopes and
persists them to SQLite. Each block represents a single message
(user, assistant, or system) within a session.

Design:
- Deterministic content hashing (SHA256) for deduplication
- Session-scoped block indexing for ordering
- Token estimation for budget tracking
- Tags for downstream filtering (intent, project, priority)
"""

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationBlock:
    """A single captured conversation block."""
    session_id: str
    block_index: int
    timestamp: int
    role: str               # user, assistant, system
    content_hash: str
    raw_content: str
    token_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage."""
        d = asdict(self)
        d["tags"] = json.dumps(d["tags"])
        d["metadata"] = json.dumps(d["metadata"])
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ConversationBlock":
        """Deserialize from SQLite row."""
        return cls(
            session_id=row["session_id"],
            block_index=row["block_index"],
            timestamp=row["timestamp"],
            role=row["role"],
            content_hash=row["content_hash"],
            raw_content=row["raw_content"],
            token_count=row["token_count"],
            tags=json.loads(row["tags"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
        )


def _content_hash(content: str) -> str:
    """Generate SHA256 hash of content for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


class ConversationCapture:
    """
    Captures conversation blocks and stores them in SQLite.

    Usage:
        cap = ConversationCapture(db_path)
        cap.capture("sess_123", "user", "How do I deploy?", tags=["how_to"])
        blocks = cap.get_session_blocks("sess_123")
    """

    def __init__(self, db_path: str = None):
        """Initialize with SQLite backend."""
        if db_path is None:
            db_path = Path.home() / ".openclaw" / "workspace" / "cache" / "responses.db"
            db_path = str(db_path)

        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()

        logger.info(f"ConversationCapture initialized at {db_path}")

    def _ensure_tables(self):
        """Create context_blocks table if it doesn't exist."""
        self.conn.executescript("""
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
            CREATE INDEX IF NOT EXISTS idx_ctx_blocks_session
                ON context_blocks(session_id);
            CREATE INDEX IF NOT EXISTS idx_ctx_blocks_timestamp
                ON context_blocks(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ctx_blocks_hash
                ON context_blocks(content_hash);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ctx_blocks_session_index
                ON context_blocks(session_id, block_index);
        """)
        self.conn.commit()

    def new_session_id(self) -> str:
        """Generate a new session ID."""
        return f"sess_{uuid.uuid4().hex[:12]}"

    def capture(
        self,
        session_id: str,
        role: str,
        content: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationBlock:
        """
        Capture a single conversation block.

        Args:
            session_id: Session this block belongs to
            role: Message role (user, assistant, system)
            content: Raw message content
            tags: Optional tags for filtering
            metadata: Optional extra data

        Returns:
            The created ConversationBlock
        """
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid role: {role}. Must be user, assistant, or system.")

        now = int(time.time())
        block_index = self._next_block_index(session_id)
        chash = _content_hash(content)
        tokens = _estimate_tokens(content)

        block = ConversationBlock(
            session_id=session_id,
            block_index=block_index,
            timestamp=now,
            role=role,
            content_hash=chash,
            raw_content=content,
            token_count=tokens,
            tags=tags or [],
            metadata=metadata or {},
        )

        try:
            self.conn.execute("""
                INSERT INTO context_blocks
                (session_id, block_index, timestamp, role, content_hash,
                 raw_content, token_count, tags, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                block.session_id,
                block.block_index,
                block.timestamp,
                block.role,
                block.content_hash,
                block.raw_content,
                block.token_count,
                json.dumps(block.tags),
                json.dumps(block.metadata),
                now,
            ))
            self.conn.commit()
            logger.debug(
                f"Captured block {block_index} in session {session_id} "
                f"(role={role}, tokens={tokens})"
            )
        except sqlite3.IntegrityError:
            logger.warning(
                f"Duplicate block {block_index} in session {session_id}, skipping"
            )
        except Exception as e:
            logger.error(f"Capture error: {e}")
            raise

        return block

    def get_session_blocks(
        self, session_id: str, limit: int = 0
    ) -> List[ConversationBlock]:
        """
        Retrieve all blocks for a session, ordered by block_index.

        Args:
            session_id: Session to retrieve
            limit: Max blocks to return (0 = all)

        Returns:
            List of ConversationBlock ordered by block_index
        """
        query = """
            SELECT * FROM context_blocks
            WHERE session_id = ?
            ORDER BY block_index ASC
        """
        params: list = [session_id]
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)

        cursor = self.conn.execute(query, params)
        return [ConversationBlock.from_row(row) for row in cursor.fetchall()]

    def get_recent_sessions(self, limit: int = 10) -> List[str]:
        """
        Get the most recent session IDs.

        Args:
            limit: Max sessions to return

        Returns:
            List of session IDs ordered by most recent first
        """
        cursor = self.conn.execute("""
            SELECT session_id, MAX(timestamp) as last_ts
            FROM context_blocks
            GROUP BY session_id
            ORDER BY last_ts DESC
            LIMIT ?
        """, (limit,))
        return [row["session_id"] for row in cursor.fetchall()]

    def get_session_token_count(self, session_id: str) -> int:
        """Total estimated tokens for a session."""
        cursor = self.conn.execute("""
            SELECT COALESCE(SUM(token_count), 0) as total
            FROM context_blocks WHERE session_id = ?
        """, (session_id,))
        return cursor.fetchone()["total"]

    def _next_block_index(self, session_id: str) -> int:
        """Get the next block index for a session."""
        cursor = self.conn.execute("""
            SELECT COALESCE(MAX(block_index), -1) + 1 as next_idx
            FROM context_blocks WHERE session_id = ?
        """, (session_id,))
        return cursor.fetchone()["next_idx"]

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("ConversationCapture closed")
