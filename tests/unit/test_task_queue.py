"""Tests for the task queue."""

import os
import tempfile
import pytest

from src.taskqueue.task_queue import TaskQueue, Task, TaskStatus, TaskPriority


@pytest.fixture
def queue():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    q = TaskQueue(db_path=path)
    yield q
    q.close()
    os.unlink(path)


def test_submit_and_get(queue):
    task = Task.create("Fix the login bug", project="BetApp")
    task_id = queue.submit(task)
    assert task_id == task.id

    fetched = queue.get(task_id)
    assert fetched is not None
    assert fetched.message == "Fix the login bug"
    assert fetched.project == "BetApp"
    assert fetched.status == TaskStatus.QUEUED.value


def test_claim_next_priority_order(queue):
    low = Task.create("Say thanks", priority=TaskPriority.LOW.value)
    high = Task.create("Fix critical bug", priority=TaskPriority.HIGH.value)
    normal = Task.create("Check status", priority=TaskPriority.NORMAL.value)

    queue.submit(low)
    queue.submit(high)
    queue.submit(normal)

    claimed = queue.claim_next()
    assert claimed.message == "Fix critical bug"
    assert claimed.status == TaskStatus.PROCESSING.value


def test_complete_task(queue):
    task = Task.create("Test task")
    queue.submit(task)
    claimed = queue.claim_next()

    queue.complete(claimed.id, "All done", tier="ollama")

    result = queue.get(claimed.id)
    assert result.status == TaskStatus.COMPLETED.value
    assert result.result == "All done"
    assert result.tier == "ollama"


def test_fail_and_retry(queue):
    task = Task.create("Flaky task")
    task.max_attempts = 3
    queue.submit(task)

    # First attempt fails -> re-queued
    claimed = queue.claim_next()
    queue.fail(claimed.id, "Network error")

    result = queue.get(claimed.id)
    assert result.status == TaskStatus.QUEUED.value  # re-queued for retry

    # Second attempt fails -> re-queued
    claimed = queue.claim_next()
    queue.fail(claimed.id, "Network error again")

    result = queue.get(claimed.id)
    assert result.status == TaskStatus.QUEUED.value

    # Third attempt fails -> permanent failure
    claimed = queue.claim_next()
    queue.fail(claimed.id, "Still broken")

    result = queue.get(claimed.id)
    assert result.status == TaskStatus.FAILED.value


def test_stats(queue):
    for i in range(5):
        queue.submit(Task.create(f"Task {i}"))

    claimed = queue.claim_next()
    queue.complete(claimed.id, "done", tier="ollama")

    stats = queue.stats()
    assert stats["queued"] == 4
    assert stats["completed"] == 1
    assert stats["total"] == 5


def test_pending_count(queue):
    assert queue.pending_count() == 0
    queue.submit(Task.create("Task 1"))
    queue.submit(Task.create("Task 2"))
    assert queue.pending_count() == 2
