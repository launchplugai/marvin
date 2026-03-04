#!/usr/bin/env python3
"""
Context Compressor — Groq 8B Summarization
Phase 1.5

Takes raw conversation blocks and compresses them into concise
summaries via Groq Llama 8B (free tier). Produces two context levels:

- HIGH: Goals, decisions, project state changes, what was accomplished
- LOW: Specific code changes, file paths, commands run, technical details

Design:
- Same Groq integration pattern as lobby/classifier.py
- Batches blocks to stay within context window
- Falls back to extractive summarization if Groq unavailable
- Stores results in context_synthesis table
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

from .capture import ConversationBlock

logger = logging.getLogger(__name__)

# Max tokens per compression request (Groq 8B context is 8192)
MAX_INPUT_TOKENS = 6000
# Max blocks to compress in a single batch
MAX_BATCH_BLOCKS = 20


@dataclass
class SynthesisResult:
    """Result of compressing conversation blocks."""
    session_id: str
    block_range_start: int
    block_range_end: int
    context_level: str      # "high" or "low"
    summary: str
    model_used: str
    tokens_input: int
    tokens_output: int
    tags: List[str]


class ContextCompressor:
    """
    Compresses raw conversation blocks into synthesized summaries
    using Groq Llama 8B (free tier).

    Usage:
        comp = ContextCompressor(db_path)
        results = comp.compress_session("sess_123", blocks)
    """

    def __init__(
        self,
        db_path: str = None,
        groq_api_key: str = None,
        model: str = "llama-3.1-8b-instant",
    ):
        """Initialize compressor with Groq API and SQLite backend."""
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

        logger.info(f"ContextCompressor initialized (model={model})")

    def _ensure_tables(self):
        """Create context_synthesis table if it doesn't exist."""
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
        """)
        self.conn.commit()

    def compress_session(
        self,
        session_id: str,
        blocks: List[ConversationBlock],
    ) -> List[SynthesisResult]:
        """
        Compress a list of conversation blocks into high and low summaries.

        Args:
            session_id: The session these blocks belong to
            blocks: Ordered list of ConversationBlock

        Returns:
            List of SynthesisResult (one high-level, one low-level)
        """
        if not blocks:
            return []

        # Build conversation text from blocks
        conversation_text = self._blocks_to_text(blocks)
        block_start = blocks[0].block_index
        block_end = blocks[-1].block_index

        results = []

        # Generate HIGH-LEVEL summary
        high_summary = self._compress(
            conversation_text, level="high"
        )
        if high_summary:
            result_high = SynthesisResult(
                session_id=session_id,
                block_range_start=block_start,
                block_range_end=block_end,
                context_level="high",
                summary=high_summary["summary"],
                model_used=high_summary["model"],
                tokens_input=high_summary["tokens_input"],
                tokens_output=high_summary["tokens_output"],
                tags=self._extract_tags(blocks),
            )
            self._store_synthesis(result_high)
            results.append(result_high)

        # Generate LOW-LEVEL summary
        low_summary = self._compress(
            conversation_text, level="low"
        )
        if low_summary:
            result_low = SynthesisResult(
                session_id=session_id,
                block_range_start=block_start,
                block_range_end=block_end,
                context_level="low",
                summary=low_summary["summary"],
                model_used=low_summary["model"],
                tokens_input=low_summary["tokens_input"],
                tokens_output=low_summary["tokens_output"],
                tags=self._extract_tags(blocks),
            )
            self._store_synthesis(result_low)
            results.append(result_low)

        return results

    def _compress(
        self, conversation_text: str, level: str
    ) -> Optional[Dict[str, Any]]:
        """
        Send conversation to Groq for compression.

        Args:
            conversation_text: Formatted conversation text
            level: "high" or "low"

        Returns:
            {summary, model, tokens_input, tokens_output} or None
        """
        prompt = self._build_prompt(conversation_text, level)

        # Try LLM first
        llm_result = self._compress_via_llm(prompt)
        if llm_result:
            return llm_result

        # Fallback to extractive summarization
        return self._compress_fallback(conversation_text, level)

    def _build_prompt(self, conversation_text: str, level: str) -> str:
        """Build the compression prompt for Groq."""
        if level == "high":
            return (
                "You are a conversation summarizer. Extract the HIGH-LEVEL context "
                "from this conversation. Focus on:\n"
                "- Goals and objectives discussed\n"
                "- Decisions made\n"
                "- Project state changes\n"
                "- What was accomplished\n"
                "- Open questions or blockers\n\n"
                "Be concise. Use bullet points. No filler.\n\n"
                f"CONVERSATION:\n{conversation_text}\n\n"
                "HIGH-LEVEL SUMMARY:"
            )
        else:
            return (
                "You are a technical conversation summarizer. Extract the LOW-LEVEL "
                "technical details from this conversation. Focus on:\n"
                "- Specific code changes (files, functions, lines)\n"
                "- Commands run and their output\n"
                "- Configuration changes\n"
                "- Error messages and fixes\n"
                "- Technical decisions and rationale\n\n"
                "Be precise. Include file paths and code snippets where relevant.\n\n"
                f"CONVERSATION:\n{conversation_text}\n\n"
                "LOW-LEVEL TECHNICAL SUMMARY:"
            )

    def _compress_via_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call Groq 8B for compression."""
        if not self.api_key:
            logger.warning("No Groq API key, skipping LLM compression")
            return None

        try:
            response = requests.post(
                self.groq_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                    "temperature": 0.3,
                },
                timeout=30,
            )

            if response.status_code != 200:
                logger.warning(f"Groq API error: {response.status_code}")
                return None

            data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})

            return {
                "summary": summary,
                "model": self.model,
                "tokens_input": usage.get("prompt_tokens", 0),
                "tokens_output": usage.get("completion_tokens", 0),
            }

        except requests.Timeout:
            logger.warning("Groq API timeout during compression")
            return None
        except Exception as e:
            logger.error(f"LLM compression error: {e}")
            return None

    def _compress_fallback(
        self, conversation_text: str, level: str
    ) -> Dict[str, Any]:
        """
        Extractive fallback when Groq is unavailable.
        Picks key sentences based on simple heuristics.
        """
        lines = conversation_text.strip().split("\n")

        if level == "high":
            # Keep lines that look like decisions/goals/state changes
            keywords = [
                "decided", "goal", "plan", "built", "deployed", "completed",
                "changed", "updated", "created", "fixed", "resolved",
                "blocked", "question", "todo", "next",
            ]
            filtered = [
                line for line in lines
                if any(kw in line.lower() for kw in keywords)
            ]
        else:
            # Keep lines with technical markers
            keywords = [
                "/", ".", "error", "command", "run", "output", "file",
                "function", "class", "import", "config", "```",
                "git", "pip", "npm", "docker",
            ]
            filtered = [
                line for line in lines
                if any(kw in line.lower() for kw in keywords)
            ]

        # Take up to 20 lines, or all lines if conversation is short
        if not filtered:
            filtered = lines[:10]
        else:
            filtered = filtered[:20]

        summary = "\n".join(filtered)
        return {
            "summary": summary,
            "model": "fallback_extractive",
            "tokens_input": len(conversation_text) // 4,
            "tokens_output": len(summary) // 4,
        }

    def _blocks_to_text(self, blocks: List[ConversationBlock]) -> str:
        """Format blocks into readable conversation text."""
        lines = []
        for block in blocks:
            role_label = block.role.upper()
            # Truncate very long messages for compression
            content = block.raw_content
            if len(content) > 2000:
                content = content[:2000] + "... [truncated]"
            lines.append(f"[{role_label}]: {content}")
        return "\n".join(lines)

    def _extract_tags(self, blocks: List[ConversationBlock]) -> List[str]:
        """Collect unique tags from all blocks."""
        tags = set()
        for block in blocks:
            tags.update(block.tags)
        return sorted(tags)

    def _store_synthesis(self, result: SynthesisResult):
        """Persist synthesis result to SQLite."""
        now = int(time.time())
        try:
            self.conn.execute("""
                INSERT INTO context_synthesis
                (session_id, block_range_start, block_range_end, context_level,
                 summary, model_used, tokens_input, tokens_output, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.session_id,
                result.block_range_start,
                result.block_range_end,
                result.context_level,
                result.summary,
                result.model_used,
                result.tokens_input,
                result.tokens_output,
                json.dumps(result.tags),
                now,
            ))
            self.conn.commit()
            logger.debug(
                f"Stored {result.context_level} synthesis for "
                f"session {result.session_id}"
            )
        except Exception as e:
            logger.error(f"Synthesis storage error: {e}")

    def get_session_syntheses(
        self, session_id: str, level: str = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve syntheses for a session.

        Args:
            session_id: Session to query
            level: Optional filter by 'high' or 'low'

        Returns:
            List of synthesis dicts
        """
        query = "SELECT * FROM context_synthesis WHERE session_id = ?"
        params: list = [session_id]
        if level:
            query += " AND context_level = ?"
            params.append(level)
        query += " ORDER BY created_at DESC"

        cursor = self.conn.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "session_id": row["session_id"],
                "block_range_start": row["block_range_start"],
                "block_range_end": row["block_range_end"],
                "context_level": row["context_level"],
                "summary": row["summary"],
                "model_used": row["model_used"],
                "tokens_input": row["tokens_input"],
                "tokens_output": row["tokens_output"],
                "tags": json.loads(row["tags"] or "[]"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("ContextCompressor closed")
