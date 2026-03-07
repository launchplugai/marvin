"""Envelope creation and execution-chain helpers for orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List
from uuid import uuid4


@dataclass
class Envelope:
    envelope_id: str
    created_at: str
    user_message: str
    project: str
    intent: str
    complexity: str
    department: str
    cacheable: bool
    execution_chain: List[Dict[str, object]] = field(default_factory=list)


def infer_complexity(intent: str, message: str) -> str:
    if intent in {"trivial", "status_check"}:
        return "low"
    if intent in {"debugging", "code_review", "feature_work"}:
        return "high"
    if len(message.split()) > 30:
        return "high"
    return "medium"


def route_department(intent: str) -> str:
    mapping = {
        "status_check": "ira",
        "how_to": "ralph",
        "code_review": "tess",
        "debugging": "ira",
        "feature_work": "ralph",
        "trivial": "lobby",
    }
    return mapping.get(intent, "ralph")


class EnvelopeFactory:
    @staticmethod
    def build(user_message: str, project: str, intent: str, cacheable: bool) -> Envelope:
        complexity = infer_complexity(intent, user_message)
        department = route_department(intent)
        return Envelope(
            envelope_id=str(uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            user_message=user_message,
            project=project,
            intent=intent,
            complexity=complexity,
            department=department,
            cacheable=cacheable,
        )


def append_execution_step(envelope: Envelope, stage: str, status: str, details: str) -> None:
    envelope.execution_chain.append(
        {
            "stage": stage,
            "status": status,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
