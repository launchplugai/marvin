"""
Transmission — HTTP API gateway for Marvin.

Single entry point for all work. Accepts tasks via POST,
returns task IDs, and serves status/results.

Endpoints:
  POST /task          -- Submit a new task
  GET  /task/{id}     -- Get task status and result
  GET  /queue         -- Queue stats
  GET  /health        -- System health check
  GET  /audit         -- Recent action audit log
  GET  /dashboard/api -- All dashboard data in one call
  GET  /              -- Control panel UI
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

from src.taskqueue.task_queue import TaskQueue, Task, TaskPriority
from src.lobby.classifier import LobbyClassifier
from src.cache.cache import CacheLayer
from src.router.llm_router import LLMRouter, TIER_MAP, ESCALATION
from src.dispatcher.dispatcher import Dispatcher
from src.constitution.constitution import Constitution

logger = logging.getLogger(__name__)

# Globals initialized on startup
queue: TaskQueue = None
classifier: LobbyClassifier = None
cache: CacheLayer = None
router: LLMRouter = None
dispatcher: Dispatcher = None
constitution: Constitution = None
_start_time: float = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue, classifier, cache, router, dispatcher, constitution, _start_time
    queue = TaskQueue()
    classifier = LobbyClassifier()
    cache = CacheLayer()
    router = LLMRouter()
    dispatcher = Dispatcher()
    constitution = Constitution(session_id="transmission")
    _start_time = time.time()
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
    classification = classifier.classify(req.message)

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


@app.get("/dashboard/api")
def dashboard_data():
    """All dashboard data in a single call for the control panel."""
    uptime = int(time.time() - _start_time) if _start_time else 0
    return {
        "system": {
            "status": "online",
            "uptime_seconds": uptime,
            "version": "0.1.0",
        },
        "queue": queue.stats(),
        "recent_tasks": queue.recent(limit=25),
        "cache": cache.get_stats(),
        "classifier": classifier.get_stats(),
        "router": {
            "tier_map": TIER_MAP,
            "escalation": ESCALATION,
            "backends": list(router.backends.keys()),
        },
        "constitution": constitution.get_check_log(limit=25),
        "audit": dispatcher.get_audit_log(limit=25),
    }


@app.get("/", response_class=HTMLResponse)
def control_panel():
    """Serve the Marvin control panel."""
    panel_path = Path(__file__).parent / "panel.html"
    if not panel_path.exists():
        raise HTTPException(status_code=500, detail="Control panel not found")
    return HTMLResponse(content=panel_path.read_text(), status_code=200)
