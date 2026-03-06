"""
Task Queue — SQLite-backed persistent task queue for Marvin.

Tasks flow: submitted -> queued -> processing -> completed/failed

Each task has:
- A classification (from lobby classifier)
- A routing tier (which LLM handles it)
- A result (once processed)
- Retry logic (max 3 attempts)
"""

import sqlite3
import json
import time
import uuid
import logging
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(Enum):
    LOW = 0       # trivial, how_to
    NORMAL = 1    # status_check, code_review
    HIGH = 2      # debugging, feature_work
    URGENT = 3    # escalation from failed lower tier


@dataclass
class Task:
    id: str
    message: str
    intent: str = "unknown"
    project: Optional[str] = None
    priority: int = TaskPriority.NORMAL.value
    status: str = TaskStatus.QUEUED.value
    tier: Optional[str] = None          # ollama / groq / claude
    result: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: int = 0
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def create(message: str, project: str = None, priority: int = None) -> "Task":
        return Task(
            id=uuid.uuid4().hex[:12],
            message=message,
            project=project,
            priority=priority if priority is not None else TaskPriority.NORMAL.value,
            created_at=int(time.time()),
        )


class TaskQueue:
    """SQLite-backed task queue with priority ordering and retry logic."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".marvin/queue.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                message TEXT NOT NULL,
                intent TEXT DEFAULT 'unknown',
                project TEXT,
                priority INTEGER DEFAULT 1,
                status TEXT DEFAULT 'queued',
                tier TEXT,
                result TEXT,
                error TEXT,
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                created_at INTEGER NOT NULL,
                started_at INTEGER,
                completed_at INTEGER,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status, priority DESC, created_at);
        """)
        self.conn.commit()

    def submit(self, task: Task) -> str:
        """Submit a task to the queue. Returns task ID."""
        self.conn.execute(
            """INSERT INTO tasks
               (id, message, intent, project, priority, status, tier,
                attempts, max_attempts, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.message, task.intent, task.project,
             task.priority, task.status, task.tier,
             task.attempts, task.max_attempts, task.created_at,
             json.dumps(task.metadata)),
        )
        self.conn.commit()
        logger.info(f"Task {task.id} submitted: {task.message[:60]}")
        return task.id

    def claim_next(self) -> Optional[Task]:
        """Claim the highest-priority queued task for processing."""
        cursor = self.conn.execute(
            """SELECT * FROM tasks
               WHERE status = 'queued'
               ORDER BY priority DESC, created_at ASC
               LIMIT 1""",
        )
        row = cursor.fetchone()
        if not row:
            return None

        now = int(time.time())
        self.conn.execute(
            "UPDATE tasks SET status = 'processing', started_at = ?, attempts = attempts + 1 WHERE id = ?",
            (now, row["id"]),
        )
        self.conn.commit()

        return Task(
            id=row["id"],
            message=row["message"],
            intent=row["intent"],
            project=row["project"],
            priority=row["priority"],
            status=TaskStatus.PROCESSING.value,
            tier=row["tier"],
            attempts=row["attempts"] + 1,
            max_attempts=row["max_attempts"],
            created_at=row["created_at"],
            started_at=now,
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def complete(self, task_id: str, result: str, tier: str = None):
        """Mark a task as completed with its result."""
        now = int(time.time())
        self.conn.execute(
            "UPDATE tasks SET status = 'completed', result = ?, tier = ?, completed_at = ? WHERE id = ?",
            (result, tier, now, task_id),
        )
        self.conn.commit()
        logger.info(f"Task {task_id} completed via {tier}")

    def fail(self, task_id: str, error: str):
        """Mark a task as failed. Re-queues if retries remain."""
        row = self.conn.execute(
            "SELECT attempts, max_attempts FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()

        if row and row["attempts"] < row["max_attempts"]:
            # Re-queue for retry
            self.conn.execute(
                "UPDATE tasks SET status = 'queued', error = ? WHERE id = ?",
                (error, task_id),
            )
            logger.warning(f"Task {task_id} failed (attempt {row['attempts']}/{row['max_attempts']}), re-queued")
        else:
            now = int(time.time())
            self.conn.execute(
                "UPDATE tasks SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
                (error, now, task_id),
            )
            logger.error(f"Task {task_id} permanently failed: {error}")

        self.conn.commit()

    def get(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return Task(
            id=row["id"], message=row["message"], intent=row["intent"],
            project=row["project"], priority=row["priority"], status=row["status"],
            tier=row["tier"], result=row["result"], error=row["error"],
            attempts=row["attempts"], max_attempts=row["max_attempts"],
            created_at=row["created_at"], started_at=row["started_at"],
            completed_at=row["completed_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def pending_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status = 'queued'").fetchone()
        return row["c"]

    def stats(self) -> Dict[str, Any]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as c FROM tasks GROUP BY status"
        ).fetchall()
        counts = {r["status"]: r["c"] for r in rows}
        return {
            "queued": counts.get("queued", 0),
            "processing": counts.get("processing", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "total": sum(counts.values()),
        }

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent tasks across all statuses, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "message": r["message"][:120],
                "intent": r["intent"],
                "project": r["project"],
                "priority": r["priority"],
                "status": r["status"],
                "tier": r["tier"],
                "attempts": r["attempts"],
                "error": r["error"],
                "created_at": r["created_at"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
            }
            for r in rows
        ]

    def close(self):
        self.conn.close()
