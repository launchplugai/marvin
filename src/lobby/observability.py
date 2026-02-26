"""Decision log schema enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from jsonschema import Draft7Validator

DECISION_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": [
        "request_id",
        "received_at",
        "user_id",
        "layer",
        "intent",
        "confidence",
        "reason",
        "keyword_hit",
        "ollama_ok",
        "openai_ok",
        "latency_ms_total",
        "estimated_cost_usd",
        "health_checked_at",
    ],
    "properties": {
        "request_id": {"type": "string"},
        "received_at": {"type": "string", "format": "date-time"},
        "user_id": {"type": "string"},
        "layer": {"type": "string", "enum": ["keyword", "ollama", "openai", "fallback"]},
        "intent": {
            "type": "string",
            "enum": [
                "status",
                "howto",
                "trivial",
                "unknown",
                "code_debug",
                "code_review",
                "feature_design",
                "architecture",
                "security",
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "keyword_hit": {"type": ["string", "null"]},
        "ollama_ok": {"type": "boolean"},
        "openai_ok": {"type": "boolean"},
        "latency_ms_total": {"type": "number", "minimum": 0},
        "latency_ms_per_layer": {
            "type": "object",
            "additionalProperties": {"type": "number", "minimum": 0},
        },
        "estimated_cost_usd": {"type": "number", "minimum": 0},
        "health_checked_at": {"type": "string", "format": "date-time"},
        "brownout_active": {"type": "boolean"},
        "circuit_breakers": {
            "type": "object",
            "properties": {
                "ollama": {"type": "string"},
                "openai": {"type": "string"},
            },
        },
    },
}

_validator = Draft7Validator(DECISION_SCHEMA)


def validate_decision(payload: Dict[str, Any]) -> None:
    errors = sorted(_validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        messages = ", ".join(error.message for error in errors)
        raise ValueError(f"decision log validation failed: {messages}")


@dataclass
class DecisionLogRecord:
    request_id: str
    user_id: str
    layer: str
    intent: str
    confidence: float
    reason: str
    keyword_hit: Optional[str]
    ollama_ok: bool
    openai_ok: bool
    latency_ms_total: float
    estimated_cost_usd: float
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    health_checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    latency_ms_per_layer: Optional[Dict[str, float]] = None
    brownout_active: bool = False
    circuit_breakers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "request_id": self.request_id,
            "received_at": self.received_at,
            "user_id": self.user_id,
            "layer": self.layer,
            "intent": self.intent,
            "confidence": self.confidence,
            "reason": self.reason,
            "keyword_hit": self.keyword_hit,
            "ollama_ok": self.ollama_ok,
            "openai_ok": self.openai_ok,
            "latency_ms_total": self.latency_ms_total,
            "latency_ms_per_layer": self.latency_ms_per_layer or {},
            "estimated_cost_usd": self.estimated_cost_usd,
            "health_checked_at": self.health_checked_at,
            "brownout_active": self.brownout_active,
            "circuit_breakers": self.circuit_breakers or {},
        }
        validate_decision(payload)
        return payload
