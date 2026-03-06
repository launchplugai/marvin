"""
Transmission — HTTP API gateway for Marvin.

Single entry point for all work. Accepts tasks via POST,
returns task IDs, and serves status/results.

Endpoints:
  POST /task          — Submit a new task
  GET  /task/{id}     — Get task status and result
  GET  /queue         — Queue stats
  GET  /health        — System health check
  GET  /audit         — Recent action audit log
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from src.taskqueue.task_queue import TaskQueue, Task, TaskPriority
from src.lobby.classifier import LobbyClassifier
from src.cache.cache import CacheLayer
from src.router.llm_router import LLMRouter
from src.dispatcher.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

# Globals initialized on startup
queue: TaskQueue = None
classifier: LobbyClassifier = None
cache: CacheLayer = None
router: LLMRouter = None
dispatcher: Dispatcher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue, classifier, cache, router, dispatcher
    queue = TaskQueue()
    classifier = LobbyClassifier()
    cache = CacheLayer()
    router = LLMRouter()
    dispatcher = Dispatcher()
    logger.info("Marvin systems online")
    yield
    queue.close()
    cache.close()
    logger.info("Marvin systems shutdown")


app = FastAPI(title="Marvin", version="0.1.0", lifespan=lifespan)


class TaskRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    project: Optional[str] = None
    priority: Optional[int] = None


class TaskResponse(BaseModel):
    task_id: str
    status: str
    intent: str
    tier: Optional[str] = None
    result: Optional[str] = None
    cached: bool = False


@app.post("/task", response_model=TaskResponse)
def submit_task(req: TaskRequest):
    """Submit a task to Marvin for processing."""
    # 1. Classify intent
    classification = classifier.classify(req.message)

    # 2. Check cache
    cached = cache.get(intent=classification.intent, project=req.project)
    if cached:
        return TaskResponse(
            task_id="cache",
            status="completed",
            intent=classification.intent,
            tier="cache",
            result=str(cached["value"]),
            cached=True,
        )

    # 3. Map intent to priority if not provided
    priority = req.priority
    if priority is None:
        priority_map = {
            "trivial": TaskPriority.LOW.value,
            "status_check": TaskPriority.NORMAL.value,
            "how_to": TaskPriority.NORMAL.value,
            "code_review": TaskPriority.HIGH.value,
            "debugging": TaskPriority.HIGH.value,
            "feature_work": TaskPriority.HIGH.value,
            "unknown": TaskPriority.NORMAL.value,
        }
        priority = priority_map.get(classification.intent, TaskPriority.NORMAL.value)

    # 4. Create and queue task
    task = Task.create(
        message=req.message,
        project=req.project,
        priority=priority,
    )
    task.intent = classification.intent
    queue.submit(task)

    return TaskResponse(
        task_id=task.id,
        status=task.status,
        intent=classification.intent,
    )


@app.get("/task/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    """Get status/result of a submitted task."""
    task = queue.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        task_id=task.id,
        status=task.status,
        intent=task.intent,
        tier=task.tier,
        result=task.result,
    )


@app.get("/queue")
def queue_stats():
    """Get queue statistics."""
    return queue.stats()


@app.get("/health")
def health():
    """System health check."""
    return {
        "status": "ok",
        "queue": queue.stats(),
        "cache": cache.get_stats(),
        "classifier": classifier.get_stats(),
    }


@app.get("/audit")
def audit_log():
    """Recent dispatcher actions."""
    return dispatcher.get_audit_log(limit=50)
