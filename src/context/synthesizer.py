#!/usr/bin/env python3
"""
Context Synthesizer — Two-Layer Thread Re-synthesis
Phase 1.5

The "screener" subroutine that periodically re-synthesizes stored
context_synthesis records into coherent high-level and low-level
threads spanning multiple sessions.

HIGH-LEVEL thread: goals, decisions, project state, what changed
LOW-LEVEL thread: specific code changes, technical details, commands run

Design:
- Reads all context_synthesis records
- Groups by context_level
- Re-synthesizes via Groq into a single coherent thread per level
- Stores/updates in context_threads table
- Idempotent: can re-run safely (upserts by thread_id)
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests

logger = logging.getLogger(__name__)


class ContextSynthesizer:
    """
    Re-synthesizes session-level summaries into cross-session threads.

    Usage:
        synth = ContextSynthesizer(db_path)
        synth.synthesize_threads()  # re-synthesize all threads
        threads = synth.get_threads()
    """

    def __init__(
        self,
        db_path: str = None,
        groq_api_key: str = None,
        model: str = "llama-3.1-8b-instant",
    ):
        """Initialize synthesizer."""
        if groq_api_key is None:
            groq_api_key = os.environ.get("GROQ_API_KEY")

        self.api_key = groq_api_key
        self.model = model
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"

        if db_path is None:
            db_path = str(
                Path.home() / ".openclaw" / "workspace" / "cache" / "responses.db"
            )

        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()

        logger.info(f"ContextSynthesizer initialized (model={model})")

    def _ensure_tables(self):
        """Create context_threads and context_synthesis tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS context_synthesis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                block_range_start INTEGER NOT NULL,
                block_range_end INTEGER NOT NULL,
                context_level TEXT NOT NULL,
                summary TEXT NOT NULL,
                model_used TEXT DEFAULT 'llama-3.1-8b-instant',
                tokens_input INTEGER DEFAULT 0,
                tokens_output INTEGER DEFAULT 0,
                tags TEXT,
                metadata TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ctx_synth_session
                ON context_synthesis(session_id);
            CREATE INDEX IF NOT EXISTS idx_ctx_synth_level
                ON context_synthesis(context_level);
            CREATE TABLE IF NOT EXISTS context_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT UNIQUE NOT NULL,
                thread_type TEXT NOT NULL,
                session_ids TEXT NOT NULL,
                content TEXT NOT NULL,
                synthesis_count INTEGER DEFAULT 1,
                model_used TEXT DEFAULT 'llama-3.1-8b-instant',
                tokens_used INTEGER DEFAULT 0,
                metadata TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ctx_threads_type
                ON context_threads(thread_type);
            CREATE INDEX IF NOT EXISTS idx_ctx_threads_updated
                ON context_threads(updated_at);
        """)
        self.conn.commit()

    def synthesize_threads(self) -> Dict[str, Any]:
        """
        Re-synthesize all context into high-level and low-level threads.

        Reads context_synthesis records, groups by level, and produces
        one thread per level. Idempotent via upsert on thread_id.

        Returns:
            {
                "high_level": {thread_id, content, session_count, ...},
                "low_level": {thread_id, content, session_count, ...},
            }
        """
        results = {}

        for level in ("high", "low"):
            thread_type = f"{level}_level"
            summaries = self._load_summaries(level)

            if not summaries:
                logger.debug(f"No {level} summaries to synthesize")
                continue

            # Collect session IDs
            session_ids = sorted(set(s["session_id"] for s in summaries))

            # Build input text from summaries
            input_text = self._summaries_to_text(summaries, level)

            # Synthesize via LLM or fallback
            thread_content = self._synthesize(input_text, level)

            if thread_content:
                thread_id = self._thread_id(thread_type, session_ids)
                self._store_thread(
                    thread_id=thread_id,
                    thread_type=thread_type,
                    session_ids=session_ids,
                    content=thread_content["content"],
                    model_used=thread_content["model"],
                    tokens_used=thread_content["tokens"],
                )
                results[thread_type] = {
                    "thread_id": thread_id,
                    "content": thread_content["content"],
                    "session_count": len(session_ids),
                    "model": thread_content["model"],
                }

        return results

    def _load_summaries(self, level: str) -> List[Dict[str, Any]]:
        """Load all context_synthesis records for a given level."""
        cursor = self.conn.execute("""
            SELECT session_id, summary, created_at, tags
            FROM context_synthesis
            WHERE context_level = ?
            ORDER BY created_at ASC
        """, (level,))

        return [
            {
                "session_id": row["session_id"],
                "summary": row["summary"],
                "created_at": row["created_at"],
                "tags": json.loads(row["tags"] or "[]"),
            }
            for row in cursor.fetchall()
        ]

    def _summaries_to_text(
        self, summaries: List[Dict[str, Any]], level: str
    ) -> str:
        """Format summaries into text for re-synthesis."""
        parts = []
        for s in summaries:
            header = f"[Session: {s['session_id']}]"
            if s["tags"]:
                header += f" (tags: {', '.join(s['tags'])})"
            parts.append(f"{header}\n{s['summary']}")
        return "\n\n---\n\n".join(parts)

    def _synthesize(
        self, input_text: str, level: str
    ) -> Optional[Dict[str, Any]]:
        """Synthesize summaries into a single thread via Groq or fallback."""
        prompt = self._build_synthesis_prompt(input_text, level)

        # Try LLM
        llm_result = self._synthesize_via_llm(prompt)
        if llm_result:
            return llm_result

        # Fallback: concatenate with deduplication
        return self._synthesize_fallback(input_text, level)

    def _build_synthesis_prompt(self, input_text: str, level: str) -> str:
        """Build the re-synthesis prompt."""
        if level == "high":
            return (
                "You are synthesizing multiple conversation summaries into a single "
                "coherent HIGH-LEVEL project context document. Combine, deduplicate, "
                "and organize these summaries into a clear narrative of:\n"
                "- Current project goals and status\n"
                "- Key decisions made\n"
                "- What has been accomplished\n"
                "- Open items and blockers\n\n"
                "Remove redundancy. Keep it concise and actionable.\n\n"
                f"SUMMARIES:\n{input_text}\n\n"
                "SYNTHESIZED HIGH-LEVEL CONTEXT:"
            )
        else:
            return (
                "You are synthesizing multiple technical summaries into a single "
                "coherent LOW-LEVEL technical context document. Combine and organize:\n"
                "- Code changes (files, functions, modules)\n"
                "- Commands and configurations\n"
                "- Error fixes and technical decisions\n"
                "- Architecture and implementation details\n\n"
                "Keep file paths and specifics. Remove redundancy.\n\n"
                f"SUMMARIES:\n{input_text}\n\n"
                "SYNTHESIZED LOW-LEVEL TECHNICAL CONTEXT:"
            )

    def _synthesize_via_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call Groq for thread synthesis."""
        if not self.api_key:
            logger.warning("No Groq API key, skipping LLM synthesis")
            return None

        try:
            response = requests.post(
                self.groq_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.3,
                },
                timeout=30,
            )

            if response.status_code != 200:
                logger.warning(f"Groq API error: {response.status_code}")
                return None

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})

            return {
                "content": content,
                "model": self.model,
                "tokens": usage.get("total_tokens", 0),
            }

        except requests.Timeout:
            logger.warning("Groq API timeout during synthesis")
            return None
        except Exception as e:
            logger.error(f"LLM synthesis error: {e}")
            return None

    def _synthesize_fallback(
        self, input_text: str, level: str
    ) -> Dict[str, Any]:
        """Fallback: deduplicate and concatenate summaries."""
        # Simple dedup by line
        seen = set()
        unique_lines = []
        for line in input_text.split("\n"):
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique_lines.append(line)

        content = "\n".join(unique_lines)
        return {
            "content": content,
            "model": "fallback_concat",
            "tokens": 0,
        }

    def _thread_id(self, thread_type: str, session_ids: List[str]) -> str:
        """Generate a deterministic thread ID from type + sessions."""
        data = f"{thread_type}:{','.join(sorted(session_ids))}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _store_thread(
        self,
        thread_id: str,
        thread_type: str,
        session_ids: List[str],
        content: str,
        model_used: str,
        tokens_used: int,
    ):
        """Upsert thread into context_threads table."""
        now = int(time.time())

        # Check if exists for synthesis_count increment
        cursor = self.conn.execute(
            "SELECT synthesis_count FROM context_threads WHERE thread_id = ?",
            (thread_id,),
        )
        row = cursor.fetchone()

        if row:
            new_count = row["synthesis_count"] + 1
            self.conn.execute("""
                UPDATE context_threads
                SET content = ?, model_used = ?, tokens_used = ?,
                    synthesis_count = ?, session_ids = ?, updated_at = ?
                WHERE thread_id = ?
            """, (
                content, model_used, tokens_used, new_count,
                json.dumps(session_ids), now, thread_id,
            ))
        else:
            self.conn.execute("""
                INSERT INTO context_threads
                (thread_id, thread_type, session_ids, content,
                 synthesis_count, model_used, tokens_used, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (
                thread_id, thread_type, json.dumps(session_ids),
                content, model_used, tokens_used, now, now,
            ))

        self.conn.commit()
        logger.debug(f"Stored/updated thread {thread_id} ({thread_type})")

    def get_threads(
        self, thread_type: str = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve synthesized threads.

        Args:
            thread_type: Optional filter ('high_level' or 'low_level')

        Returns:
            List of thread dicts
        """
        query = "SELECT * FROM context_threads"
        params: list = []
        if thread_type:
            query += " WHERE thread_type = ?"
            params.append(thread_type)
        query += " ORDER BY updated_at DESC"

        cursor = self.conn.execute(query, params)
        return [
            {
                "thread_id": row["thread_id"],
                "thread_type": row["thread_type"],
                "session_ids": json.loads(row["session_ids"]),
                "content": row["content"],
                "synthesis_count": row["synthesis_count"],
                "model_used": row["model_used"],
                "tokens_used": row["tokens_used"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in cursor.fetchall()
        ]

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("ContextSynthesizer closed")
