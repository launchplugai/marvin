#!/usr/bin/env python3
"""
Context Sync — VPS Synchronization
Phase 1.5

Handles syncing the local context store to the VPS via the
marvin-skills HTTP endpoint. Designed for periodic push of
context data so the Oracle always has the latest context.

Design:
- Exports context_blocks, context_synthesis, context_threads as JSON
- POSTs to marvin-skills endpoint on VPS
- Tracks last sync timestamp to send only deltas
- Graceful degradation: sync failures don't block local operations
"""

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

# Default sync endpoint (marvin-skills on VPS)
DEFAULT_SYNC_URL = "http://187.77.211.80:19800/context/sync"


class ContextSync:
    """
    Syncs local context store to VPS marvin-skills endpoint.

    Usage:
        sync = ContextSync(db_path)
        result = sync.push()  # push delta to VPS
        result = sync.push_full()  # push everything
    """

    def __init__(
        self,
        db_path: str = None,
        sync_url: str = None,
        auth_token: str = None,
    ):
        """Initialize sync client."""
        if db_path is None:
            db_path = str(
                Path.home() / ".openclaw" / "workspace" / "cache" / "responses.db"
            )

        self.db_path = db_path
        self.sync_url = sync_url or os.environ.get(
            "MARVIN_SYNC_URL", DEFAULT_SYNC_URL
        )
        self.auth_token = auth_token or os.environ.get("MARVIN_SYNC_TOKEN")

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        self._ensure_sync_meta()

        logger.info(f"ContextSync initialized (url={self.sync_url})")

    def _ensure_sync_meta(self):
        """Create sync metadata table for tracking last sync."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS context_sync_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_at INTEGER DEFAULT 0,
                last_sync_status TEXT,
                sync_count INTEGER DEFAULT 0
            )
        """)
        self.conn.execute("""
            INSERT OR IGNORE INTO context_sync_meta (id, last_sync_at, sync_count)
            VALUES (1, 0, 0)
        """)
        self.conn.commit()

    def push(self) -> Dict[str, Any]:
        """
        Push delta (new records since last sync) to VPS.

        Returns:
            {
                "status": "success" | "error" | "no_data",
                "blocks_sent": int,
                "syntheses_sent": int,
                "threads_sent": int,
                "sync_timestamp": int,
            }
        """
        last_sync = self._get_last_sync_at()
        return self._do_push(since=last_sync)

    def push_full(self) -> Dict[str, Any]:
        """Push all records to VPS (full sync)."""
        return self._do_push(since=0)

    def _do_push(self, since: int) -> Dict[str, Any]:
        """Execute the push operation."""
        payload = self._export_since(since)

        total = (
            len(payload.get("blocks", []))
            + len(payload.get("syntheses", []))
            + len(payload.get("threads", []))
        )

        if total == 0:
            logger.debug("No new context data to sync")
            return {
                "status": "no_data",
                "blocks_sent": 0,
                "syntheses_sent": 0,
                "threads_sent": 0,
                "sync_timestamp": int(time.time()),
            }

        try:
            headers = {"Content-Type": "application/json"}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            response = requests.post(
                self.sync_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code in (200, 201):
                now = int(time.time())
                self._update_sync_meta(now, "success")
                result = {
                    "status": "success",
                    "blocks_sent": len(payload.get("blocks", [])),
                    "syntheses_sent": len(payload.get("syntheses", [])),
                    "threads_sent": len(payload.get("threads", [])),
                    "sync_timestamp": now,
                }
                logger.info(
                    f"Context sync success: {result['blocks_sent']} blocks, "
                    f"{result['syntheses_sent']} syntheses, "
                    f"{result['threads_sent']} threads"
                )
                return result
            else:
                logger.warning(
                    f"Context sync failed: HTTP {response.status_code}"
                )
                self._update_sync_meta(int(time.time()), f"error_{response.status_code}")
                return {
                    "status": "error",
                    "blocks_sent": 0,
                    "syntheses_sent": 0,
                    "threads_sent": 0,
                    "sync_timestamp": int(time.time()),
                    "error": f"HTTP {response.status_code}",
                }

        except requests.Timeout:
            logger.warning("Context sync timeout")
            self._update_sync_meta(int(time.time()), "timeout")
            return {
                "status": "error",
                "blocks_sent": 0,
                "syntheses_sent": 0,
                "threads_sent": 0,
                "sync_timestamp": int(time.time()),
                "error": "timeout",
            }
        except requests.ConnectionError:
            logger.warning("Context sync connection error (VPS unreachable)")
            self._update_sync_meta(int(time.time()), "connection_error")
            return {
                "status": "error",
                "blocks_sent": 0,
                "syntheses_sent": 0,
                "threads_sent": 0,
                "sync_timestamp": int(time.time()),
                "error": "connection_error",
            }
        except Exception as e:
            logger.error(f"Context sync error: {e}")
            self._update_sync_meta(int(time.time()), f"error_{e}")
            return {
                "status": "error",
                "blocks_sent": 0,
                "syntheses_sent": 0,
                "threads_sent": 0,
                "sync_timestamp": int(time.time()),
                "error": str(e),
            }

    def _export_since(self, since: int) -> Dict[str, Any]:
        """Export all context records created after `since` timestamp."""
        payload: Dict[str, Any] = {"exported_at": int(time.time())}

        # Blocks
        try:
            cursor = self.conn.execute(
                "SELECT * FROM context_blocks WHERE created_at > ? ORDER BY created_at",
                (since,),
            )
            payload["blocks"] = [dict(row) for row in cursor.fetchall()]
        except Exception:
            payload["blocks"] = []

        # Syntheses
        try:
            cursor = self.conn.execute(
                "SELECT * FROM context_synthesis WHERE created_at > ? ORDER BY created_at",
                (since,),
            )
            payload["syntheses"] = [dict(row) for row in cursor.fetchall()]
        except Exception:
            payload["syntheses"] = []

        # Threads
        try:
            cursor = self.conn.execute(
                "SELECT * FROM context_threads WHERE updated_at > ? ORDER BY updated_at",
                (since,),
            )
            payload["threads"] = [dict(row) for row in cursor.fetchall()]
        except Exception:
            payload["threads"] = []

        return payload

    def _get_last_sync_at(self) -> int:
        """Get timestamp of last successful sync."""
        cursor = self.conn.execute(
            "SELECT last_sync_at FROM context_sync_meta WHERE id = 1"
        )
        row = cursor.fetchone()
        return row["last_sync_at"] if row else 0

    def _update_sync_meta(self, timestamp: int, status: str):
        """Update sync metadata."""
        try:
            self.conn.execute("""
                UPDATE context_sync_meta
                SET last_sync_at = ?, last_sync_status = ?,
                    sync_count = sync_count + 1
                WHERE id = 1
            """, (timestamp, status))
            self.conn.commit()
        except Exception as e:
            logger.warning(f"Error updating sync meta: {e}")

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status."""
        cursor = self.conn.execute(
            "SELECT * FROM context_sync_meta WHERE id = 1"
        )
        row = cursor.fetchone()
        if not row:
            return {"last_sync_at": 0, "last_sync_status": "never", "sync_count": 0}
        return {
            "last_sync_at": row["last_sync_at"],
            "last_sync_status": row["last_sync_status"],
            "sync_count": row["sync_count"],
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("ContextSync closed")
