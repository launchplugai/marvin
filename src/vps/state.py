#!/usr/bin/env python3
"""
Mission Control State Engine — Persistent Memory for Marvin

SQLite-backed append-only ledger that survives context loss.
Every agent action, decision, and state change gets recorded here.
Any agent can query for recent context to bootstrap itself.

Tables:
- events:      Append-only log of everything that happens
- agent_state:  Current snapshot per agent (last task, status, notes)
- progress:    Task/milestone tracking across the system
- decisions:   ADR-style decision records (why we chose X over Y)
- diagnostics: Model usage stats, error counts, latency

Design principles:
- Append-only events (never delete history)
- Agent state is mutable (latest snapshot)
- All writes are timestamped
- Context primers are generated, not stored (query on demand)
- SQLite = zero infrastructure, portable, backup-friendly
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Default DB location — same pattern as cache layer
DEFAULT_DB_DIR = os.path.expanduser("~/.openclaw/workspace/mission_control")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "state.db")

SCHEMA = """
-- Append-only event log: the source of truth
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    agent TEXT NOT NULL,           -- ralph, ira, tess, system, cli, user
    category TEXT NOT NULL,        -- action, decision, error, context, progress, diagnostic
    action TEXT NOT NULL,          -- deploy, classify, heal, escalate, etc.
    target TEXT DEFAULT '',        -- what was acted on
    success INTEGER DEFAULT 1,    -- 1=ok, 0=fail
    detail TEXT DEFAULT '',        -- human-readable description
    context TEXT DEFAULT '{}',     -- JSON blob of relevant state
    session_id TEXT DEFAULT ''     -- links events within a session
);

CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);

-- Current state per agent (upserted, not appended)
CREATE TABLE IF NOT EXISTS agent_state (
    agent TEXT PRIMARY KEY,
    status TEXT DEFAULT 'idle',    -- idle, working, blocked, offline
    current_task TEXT DEFAULT '',
    last_action TEXT DEFAULT '',
    last_action_at REAL DEFAULT 0,
    energy INTEGER DEFAULT 100,    -- 0-100, for sim layer
    session_count INTEGER DEFAULT 0,
    total_actions INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',         -- freeform agent notes
    updated_at REAL NOT NULL
);

-- Progress tracking: tasks and milestones
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    phase TEXT NOT NULL,           -- phase_1, phase_2, etc.
    task TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, in_progress, done, blocked
    owner TEXT DEFAULT '',         -- which agent owns this
    detail TEXT DEFAULT '',
    completed_at REAL DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_progress_phase ON progress(phase);
CREATE INDEX IF NOT EXISTS idx_progress_status ON progress(status);

-- Decision records: why we chose X over Y
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    agent TEXT NOT NULL,
    title TEXT NOT NULL,
    context TEXT NOT NULL,         -- what was the situation
    choice TEXT NOT NULL,          -- what we decided
    alternatives TEXT DEFAULT '',  -- what we didn't choose
    rationale TEXT DEFAULT '',     -- why
    reversible INTEGER DEFAULT 1  -- can we undo this?
);

-- Model diagnostics: usage stats per model
CREATE TABLE IF NOT EXISTS diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    model TEXT NOT NULL,           -- kimi-2.5, llama-8b, haiku, etc.
    provider TEXT NOT NULL,        -- groq, moonshot, anthropic
    action TEXT DEFAULT '',        -- classify, route, generate, etc.
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    latency_ms REAL DEFAULT 0,
    success INTEGER DEFAULT 1,
    error TEXT DEFAULT '',
    cost_usd REAL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_diag_model ON diagnostics(model);
CREATE INDEX IF NOT EXISTS idx_diag_timestamp ON diagnostics(timestamp);
"""


@dataclass
class Event:
    """A single event in the ledger."""
    agent: str
    category: str
    action: str
    target: str = ""
    success: bool = True
    detail: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("id", None)
        return d


@dataclass
class AgentSnapshot:
    """Current state of an agent."""
    agent: str
    status: str = "idle"
    current_task: str = ""
    last_action: str = ""
    last_action_at: float = 0
    energy: int = 100
    session_count: int = 0
    total_actions: int = 0
    total_errors: int = 0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StateEngine:
    """
    Persistent state engine for Mission Control.

    Append-only event log + mutable agent snapshots + progress tracking.
    SQLite-backed, zero infrastructure required.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("MC_STATE_DB", DEFAULT_DB_PATH)

        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

        logger.info(f"StateEngine initialized (db={self.db_path})")

    def _init_schema(self):
        """Create tables if they don't exist."""
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()

    # ── Event Log ────────────────────────────────────────────────

    def log(
        self, agent: str, category: str, action: str,
        target: str = "", success: bool = True, detail: str = "",
        context: Dict[str, Any] = None, session_id: str = "",
    ) -> int:
        """
        Append an event to the ledger. Returns the event ID.

        Categories: action, decision, error, context, progress, diagnostic
        """
        now = time.time()
        ctx_json = json.dumps(context or {})

        cursor = self._conn.execute(
            """INSERT INTO events
               (timestamp, agent, category, action, target, success, detail, context, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, agent, category, action, target, 1 if success else 0,
             detail, ctx_json, session_id),
        )
        self._conn.commit()

        # Update agent state
        self._touch_agent(agent, action, success, now)

        return cursor.lastrowid

    def get_events(
        self, agent: str = None, category: str = None,
        since: float = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query events with optional filters."""
        query = "SELECT * FROM events WHERE 1=1"
        params = []

        if agent:
            query += " AND agent = ?"
            params.append(agent)
        if category:
            query += " AND category = ?"
            params.append(category)
        if since:
            query += " AND timestamp > ?"
            params.append(since)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get the most recent events across all agents."""
        return self.get_events(limit=limit)

    # ── Agent State ──────────────────────────────────────────────

    def _touch_agent(self, agent: str, action: str, success: bool, timestamp: float):
        """Update agent's running state after an event."""
        self._conn.execute(
            """INSERT INTO agent_state (agent, last_action, last_action_at, total_actions,
                   total_errors, updated_at)
               VALUES (?, ?, ?, 1, ?, ?)
               ON CONFLICT(agent) DO UPDATE SET
                   last_action = excluded.last_action,
                   last_action_at = excluded.last_action_at,
                   total_actions = total_actions + 1,
                   total_errors = total_errors + CASE WHEN ? = 0 THEN 1 ELSE 0 END,
                   updated_at = excluded.updated_at""",
            (agent, action, timestamp, 0 if success else 1, timestamp, 1 if success else 0),
        )
        self._conn.commit()

    def set_agent_status(self, agent: str, status: str, current_task: str = "",
                         notes: str = "", energy: int = None):
        """Explicitly update an agent's status."""
        now = time.time()
        fields = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if current_task:
            fields.append("current_task = ?")
            params.append(current_task)
        if notes:
            fields.append("notes = ?")
            params.append(notes)
        if energy is not None:
            fields.append("energy = ?")
            params.append(energy)

        # Ensure agent exists
        self._conn.execute(
            """INSERT INTO agent_state (agent, status, current_task, notes, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(agent) DO UPDATE SET """ + ", ".join(fields),
            [agent, status, current_task, notes, now] + params,
        )
        self._conn.commit()

    def get_agent_state(self, agent: str) -> Optional[Dict[str, Any]]:
        """Get current state of an agent."""
        row = self._conn.execute(
            "SELECT * FROM agent_state WHERE agent = ?", (agent,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_all_agents(self) -> List[Dict[str, Any]]:
        """Get state of all known agents."""
        rows = self._conn.execute(
            "SELECT * FROM agent_state ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Progress Tracking ────────────────────────────────────────

    def add_task(self, phase: str, task: str, owner: str = "", detail: str = "") -> int:
        """Add a task to the progress tracker."""
        now = time.time()
        cursor = self._conn.execute(
            """INSERT INTO progress (created_at, updated_at, phase, task, owner, detail)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, now, phase, task, owner, detail),
        )
        self._conn.commit()
        return cursor.lastrowid

    def update_task(self, task_id: int, status: str, detail: str = ""):
        """Update a task's status."""
        now = time.time()
        completed = now if status == "done" else None
        self._conn.execute(
            """UPDATE progress SET status = ?, detail = ?, updated_at = ?,
               completed_at = COALESCE(?, completed_at)
               WHERE id = ?""",
            (status, detail, now, completed, task_id),
        )
        self._conn.commit()

    def get_progress(self, phase: str = None) -> List[Dict[str, Any]]:
        """Get progress, optionally filtered by phase."""
        if phase:
            rows = self._conn.execute(
                "SELECT * FROM progress WHERE phase = ? ORDER BY id", (phase,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM progress ORDER BY phase, id"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a compact progress summary."""
        rows = self._conn.execute(
            """SELECT phase,
                      COUNT(*) as total,
                      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
                      SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) as active,
                      SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) as blocked
               FROM progress GROUP BY phase ORDER BY phase"""
        ).fetchall()
        return {
            "phases": [dict(r) for r in rows],
            "total_tasks": sum(r["total"] for r in rows) if rows else 0,
            "completed": sum(r["done"] for r in rows) if rows else 0,
        }

    # ── Decisions ────────────────────────────────────────────────

    def record_decision(
        self, agent: str, title: str, context: str,
        choice: str, alternatives: str = "", rationale: str = "",
        reversible: bool = True,
    ) -> int:
        """Record an architectural/design decision."""
        cursor = self._conn.execute(
            """INSERT INTO decisions
               (timestamp, agent, title, context, choice, alternatives, rationale, reversible)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), agent, title, context, choice, alternatives, rationale,
             1 if reversible else 0),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent decisions."""
        rows = self._conn.execute(
            "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Diagnostics ──────────────────────────────────────────────

    def log_model_usage(
        self, model: str, provider: str, action: str = "",
        tokens_in: int = 0, tokens_out: int = 0,
        latency_ms: float = 0, success: bool = True,
        error: str = "", cost_usd: float = 0.0,
    ):
        """Record a model invocation for diagnostics."""
        self._conn.execute(
            """INSERT INTO diagnostics
               (timestamp, model, provider, action, tokens_in, tokens_out,
                latency_ms, success, error, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), model, provider, action, tokens_in, tokens_out,
             latency_ms, 1 if success else 0, error, cost_usd),
        )
        self._conn.commit()

    def get_diagnostics(self, hours: float = 24) -> Dict[str, Any]:
        """Get diagnostic summary for the last N hours."""
        since = time.time() - (hours * 3600)

        # Per-model stats
        rows = self._conn.execute(
            """SELECT model, provider,
                      COUNT(*) as calls,
                      SUM(tokens_in) as total_tokens_in,
                      SUM(tokens_out) as total_tokens_out,
                      AVG(latency_ms) as avg_latency_ms,
                      SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors,
                      SUM(cost_usd) as total_cost
               FROM diagnostics WHERE timestamp > ?
               GROUP BY model, provider ORDER BY calls DESC""",
            (since,)
        ).fetchall()

        # Overall stats
        totals = self._conn.execute(
            """SELECT COUNT(*) as total_calls,
                      SUM(tokens_in + tokens_out) as total_tokens,
                      SUM(cost_usd) as total_cost,
                      SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as total_errors
               FROM diagnostics WHERE timestamp > ?""",
            (since,)
        ).fetchone()

        return {
            "period_hours": hours,
            "models": [dict(r) for r in rows],
            "totals": dict(totals) if totals else {},
        }

    # ── Context Primer Generation ────────────────────────────────

    def get_context_for_agent(self, agent: str, depth: int = 10) -> Dict[str, Any]:
        """
        Generate a context primer for an agent starting a session.

        Returns recent events, current state, progress, and recent decisions
        relevant to that agent. This is what an agent reads to "catch up."
        """
        # Agent's own recent events
        own_events = self.get_events(agent=agent, limit=depth)

        # System-wide recent events (other agents' important actions)
        system_events = self.get_events(category="action", limit=depth)

        # Agent's current state
        state = self.get_agent_state(agent)

        # Active/blocked tasks
        all_progress = self.get_progress()
        relevant_tasks = [
            t for t in all_progress
            if t.get("owner") == agent or t.get("status") in ("in_progress", "blocked")
        ]

        # Recent decisions
        decisions = self.get_decisions(limit=5)

        return {
            "agent": agent,
            "generated_at": time.time(),
            "state": state,
            "own_recent_events": own_events[:depth],
            "system_recent_events": system_events[:depth],
            "active_tasks": relevant_tasks,
            "recent_decisions": decisions,
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _row_to_event(self, row) -> Dict[str, Any]:
        """Convert a DB row to event dict."""
        d = dict(row)
        if "context" in d:
            try:
                d["context"] = json.loads(d["context"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def get_stats(self) -> Dict[str, Any]:
        """Get engine-level statistics."""
        event_count = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        agent_count = self._conn.execute("SELECT COUNT(*) FROM agent_state").fetchone()[0]
        task_count = self._conn.execute("SELECT COUNT(*) FROM progress").fetchone()[0]
        decision_count = self._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        diag_count = self._conn.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0]

        return {
            "db_path": self.db_path,
            "events": event_count,
            "agents": agent_count,
            "tasks": task_count,
            "decisions": decision_count,
            "diagnostic_entries": diag_count,
        }
