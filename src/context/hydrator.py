#!/usr/bin/env python3
"""
Context Hydrator — Session Context Injection
Phase 1.5

Loads relevant context from the context store and formats it for
injection into new sessions. Supports two modes:

- PULL: Returns formatted context string for programmatic injection
- PUSH: Generates a CONTEXT.md file that can be auto-loaded

Design:
- Reads from context_threads (synthesized) and context_synthesis (per-session)
- Formats into a structured document with high-level and low-level sections
- Token-budget aware: trims to fit within injection limits
- Recency-weighted: most recent sessions get more detail
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Default token budget for injected context
DEFAULT_TOKEN_BUDGET = 4000
# Max age of context to include (7 days)
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600


class ContextHydrator:
    """
    Loads and formats stored context for injection into new sessions.

    Usage:
        hydrator = ContextHydrator(db_path)
        context = hydrator.hydrate()  # pull mode
        hydrator.generate_context_md("/path/to/CONTEXT.md")  # push mode
    """

    def __init__(
        self,
        db_path: str = None,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    ):
        """Initialize hydrator with SQLite backend."""
        if db_path is None:
            db_path = str(
                Path.home() / ".openclaw" / "workspace" / "cache" / "responses.db"
            )

        self.db_path = db_path
        self.token_budget = token_budget
        self.max_age_seconds = max_age_seconds

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row

        logger.info(f"ContextHydrator initialized (budget={token_budget} tokens)")

    def hydrate(
        self,
        include_high: bool = True,
        include_low: bool = True,
        session_filter: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Load and format context for injection (pull mode).

        Args:
            include_high: Include high-level thread
            include_low: Include low-level thread
            session_filter: Only include context from these sessions

        Returns:
            {
                "formatted": str,       # ready-to-inject text
                "high_level": str,      # high-level content
                "low_level": str,       # low-level content
                "sessions_covered": [],  # session IDs included
                "token_estimate": int,   # estimated tokens
                "generated_at": int,     # timestamp
            }
        """
        high_content = ""
        low_content = ""
        sessions_covered = set()

        # Load from threads first (synthesized cross-session)
        threads = self._load_threads()

        for thread in threads:
            if thread["thread_type"] == "high_level" and include_high:
                high_content = thread["content"]
                sessions_covered.update(thread["session_ids"])
            elif thread["thread_type"] == "low_level" and include_low:
                low_content = thread["content"]
                sessions_covered.update(thread["session_ids"])

        # If no threads, fall back to per-session syntheses
        if not high_content and include_high:
            high_content = self._load_recent_syntheses(
                "high", session_filter
            )
        if not low_content and include_low:
            low_content = self._load_recent_syntheses(
                "low", session_filter
            )

        # If still no syntheses, load recent raw blocks
        if not high_content and not low_content:
            raw_context = self._load_recent_blocks(session_filter)
            if raw_context:
                high_content = raw_context

        # Format the output
        formatted = self._format_context(high_content, low_content)

        # Trim to budget
        formatted = self._trim_to_budget(formatted)

        token_estimate = max(1, len(formatted) // 4)

        return {
            "formatted": formatted,
            "high_level": high_content,
            "low_level": low_content,
            "sessions_covered": sorted(sessions_covered),
            "token_estimate": token_estimate,
            "generated_at": int(time.time()),
        }

    def generate_context_md(self, output_path: str = None) -> str:
        """
        Generate a CONTEXT.md file (push mode).

        Args:
            output_path: Where to write the file. Defaults to repo root.

        Returns:
            Path to the generated file
        """
        if output_path is None:
            output_path = str(Path.cwd() / "CONTEXT.md")

        context = self.hydrate()

        md_content = (
            "# Conversation Context (Auto-Generated)\n\n"
            f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(context['generated_at']))}\n"
            f"Sessions covered: {len(context['sessions_covered'])}\n"
            f"Estimated tokens: {context['token_estimate']}\n\n"
            "---\n\n"
            f"{context['formatted']}\n"
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(md_content)

        logger.info(f"Generated CONTEXT.md at {output_path}")
        return output_path

    def _load_threads(self) -> List[Dict[str, Any]]:
        """Load synthesized threads, most recent first."""
        try:
            cursor = self.conn.execute("""
                SELECT thread_type, content, session_ids, updated_at
                FROM context_threads
                ORDER BY updated_at DESC
            """)
            return [
                {
                    "thread_type": row["thread_type"],
                    "content": row["content"],
                    "session_ids": json.loads(row["session_ids"]),
                    "updated_at": row["updated_at"],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.warning(f"Error loading threads: {e}")
            return []

    def _load_recent_syntheses(
        self, level: str, session_filter: Optional[List[str]] = None
    ) -> str:
        """Load recent per-session syntheses as fallback."""
        cutoff = int(time.time()) - self.max_age_seconds

        query = """
            SELECT summary FROM context_synthesis
            WHERE context_level = ? AND created_at > ?
        """
        params: list = [level, cutoff]

        if session_filter:
            placeholders = ",".join("?" * len(session_filter))
            query += f" AND session_id IN ({placeholders})"
            params.extend(session_filter)

        query += " ORDER BY created_at DESC LIMIT 10"

        try:
            cursor = self.conn.execute(query, params)
            summaries = [row["summary"] for row in cursor.fetchall()]
            return "\n\n".join(summaries)
        except Exception as e:
            logger.warning(f"Error loading syntheses: {e}")
            return ""

    def _load_recent_blocks(
        self, session_filter: Optional[List[str]] = None
    ) -> str:
        """Load recent raw blocks as last-resort fallback."""
        cutoff = int(time.time()) - self.max_age_seconds

        query = """
            SELECT role, raw_content FROM context_blocks
            WHERE timestamp > ?
        """
        params: list = [cutoff]

        if session_filter:
            placeholders = ",".join("?" * len(session_filter))
            query += f" AND session_id IN ({placeholders})"
            params.extend(session_filter)

        query += " ORDER BY timestamp DESC LIMIT 20"

        try:
            cursor = self.conn.execute(query, params)
            lines = [
                f"[{row['role'].upper()}]: {row['raw_content'][:500]}"
                for row in cursor.fetchall()
            ]
            return "\n".join(reversed(lines))
        except Exception as e:
            logger.warning(f"Error loading blocks: {e}")
            return ""

    def _format_context(self, high_content: str, low_content: str) -> str:
        """Format high and low content into injection-ready text."""
        parts = []

        if high_content:
            parts.append(
                "## High-Level Context\n"
                "Goals, decisions, project state, and accomplishments.\n\n"
                f"{high_content}"
            )

        if low_content:
            parts.append(
                "## Low-Level Context\n"
                "Code changes, technical details, commands, and configurations.\n\n"
                f"{low_content}"
            )

        if not parts:
            return "(No conversation context available)"

        return "\n\n---\n\n".join(parts)

    def _trim_to_budget(self, text: str) -> str:
        """Trim text to fit within token budget."""
        estimated_tokens = len(text) // 4
        if estimated_tokens <= self.token_budget:
            return text

        # Trim to approximate character count
        max_chars = self.token_budget * 4
        trimmed = text[:max_chars]

        # Try to end at a clean line boundary
        last_newline = trimmed.rfind("\n")
        if last_newline > max_chars * 0.8:
            trimmed = trimmed[:last_newline]

        return trimmed + "\n\n[Context trimmed to fit token budget]"

    def get_stats(self) -> Dict[str, Any]:
        """Get hydrator statistics."""
        try:
            blocks_count = self.conn.execute(
                "SELECT COUNT(*) as c FROM context_blocks"
            ).fetchone()["c"]
        except Exception:
            blocks_count = 0

        try:
            synth_count = self.conn.execute(
                "SELECT COUNT(*) as c FROM context_synthesis"
            ).fetchone()["c"]
        except Exception:
            synth_count = 0

        try:
            threads_count = self.conn.execute(
                "SELECT COUNT(*) as c FROM context_threads"
            ).fetchone()["c"]
        except Exception:
            threads_count = 0

        return {
            "blocks_stored": blocks_count,
            "syntheses_stored": synth_count,
            "threads_stored": threads_count,
            "token_budget": self.token_budget,
            "max_age_seconds": self.max_age_seconds,
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("ContextHydrator closed")
