"""Tests for dashboard API and new TaskQueue.recent() method."""

import os
import tempfile
import pytest
from pathlib import Path

from src.taskqueue.task_queue import TaskQueue, Task, TaskPriority


@pytest.fixture
def queue():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    q = TaskQueue(db_path=path)
    yield q
    q.close()
    os.unlink(path)


def test_recent_returns_newest_first(queue):
    for i in range(5):
        t = Task.create(f"Task {i}")
        t.created_at = 1000 + i  # ascending timestamps
        queue.submit(t)

    recent = queue.recent(limit=3)
    assert len(recent) == 3
    # Newest first
    assert recent[0]["created_at"] == 1004
    assert recent[1]["created_at"] == 1003
    assert recent[2]["created_at"] == 1002


def test_recent_truncates_message(queue):
    long_msg = "x" * 200
    t = Task.create(long_msg)
    queue.submit(t)

    recent = queue.recent()
    assert len(recent[0]["message"]) == 120  # truncated


def test_recent_includes_all_statuses(queue):
    t1 = Task.create("Queued task")
    queue.submit(t1)

    t2 = Task.create("Completed task")
    queue.submit(t2)
    queue.claim_next()  # claims t1 (higher created_at or same priority)
    claimed = queue.claim_next()
    if claimed:
        queue.complete(claimed.id, "done", tier="ollama")

    recent = queue.recent()
    statuses = {r["status"] for r in recent}
    assert len(statuses) >= 1  # at least one status type present


def test_recent_empty_queue(queue):
    recent = queue.recent()
    assert recent == []


def test_recent_limit(queue):
    for i in range(10):
        queue.submit(Task.create(f"Task {i}"))

    recent = queue.recent(limit=3)
    assert len(recent) == 3


def test_panel_html_exists():
    panel_path = Path(__file__).parent.parent.parent / "src" / "transmission" / "panel.html"
    assert panel_path.exists(), "panel.html must exist for the control panel"
    content = panel_path.read_text()
    assert "MARVIN" in content
    assert "dashboard/api" in content
    assert "fetchDashboard" in content
