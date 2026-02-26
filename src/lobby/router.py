"""Deterministic routing logic for the lobby."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .circuit_breaker import CircuitBreakerStore
from .config import LobbyConfig
from .escalation import EscalationResult, derive_intent, detect_escalation
from .health import HealthSnapshot
from .keywords import KeywordRegistry
from .observability import DecisionLogRecord


@dataclass
class RequestEnvelope:
    request_id: str
    user_id: str
    text: str
    priority: str = "normal"


@dataclass
class RoutingDecision:
    record: DecisionLogRecord
    cost_guard: dict
    escalation: EscalationResult


class LobbyRouter:
    def __init__(
        self,
        config: LobbyConfig,
        keyword_registry: KeywordRegistry,
        breakers: CircuitBreakerStore,
    ) -> None:
        self._config = config
        self._keywords = keyword_registry
        self._breakers = breakers

    def _brownout_active(self) -> bool:
        return self._config.lobby_mode == "brownout"

    def _layer_available(self, layer: str, snapshot: HealthSnapshot) -> bool:
        if layer == "ollama":
            return snapshot.ollama_ok and self._breakers.can_attempt("ollama")
        if layer == "openai":
            return snapshot.openai_ok and self._breakers.can_attempt("openai")
        return True

    def _cost_for_layer(self, layer: str) -> float:
        if layer == "openai":
            return 0.01  # placeholder estimate
        return 0.0

    def route(
        self,
        request: RequestEnvelope,
        snapshot: HealthSnapshot,
        latency_ms: float = 0.0,
        latency_per_layer: Optional[dict] = None,
    ) -> RoutingDecision:
        text = request.text.strip()
        keyword_entry = self._keywords.match(text)
        intent = derive_intent(text, keyword_entry.command if keyword_entry else None)
        escalation = detect_escalation(text)
        brownout_active = self._brownout_active()
        priority_override = request.priority == "high"

        layer = "fallback"
        reason = "no layer available"
        keyword_hit = None
        openai_guard_allowed = False
        openai_guard_reason = "not evaluated"

        if keyword_entry:
            layer = "keyword"
            reason = "exact keyword command"
            keyword_hit = keyword_entry.command
            openai_guard_reason = "keyword handled"
        else:
            ollama_available = self._layer_available("ollama", snapshot)
            openai_available = self._layer_available("openai", snapshot)

            openai_allowed = escalation.triggered
            openai_reason = ", ".join(escalation.reasons) if escalation.reasons else "no triggers"

            if brownout_active and not priority_override:
                if not escalation.triggered:
                    openai_allowed = False
                    openai_reason = "brownout denies non-trigger request"
            elif priority_override:
                openai_allowed = True
                openai_reason = "priority override"

            openai_guard_allowed = openai_allowed
            openai_guard_reason = openai_reason

            if ollama_available:
                if openai_allowed and openai_available and escalation.triggered:
                    layer = "openai"
                    reason = openai_reason
                else:
                    layer = "ollama"
                    reason = "handled by ollama"
            else:
                # Ollama unavailable
                if openai_available and (openai_allowed or priority_override):
                    layer = "openai"
                    reason = "ollama unavailable, openai escalation"
                    openai_guard_allowed = True
                    openai_guard_reason = reason
                else:
                    layer = "fallback"
                    reason = "models unavailable"
                    openai_guard_allowed = False
                    openai_guard_reason = reason

        health_checked_at = datetime.fromtimestamp(
            snapshot.checked_at or time.time(), tz=timezone.utc
        ).isoformat()

        record = DecisionLogRecord(
            request_id=request.request_id,
            user_id=request.user_id,
            layer=layer,
            intent=intent,
            confidence=0.9 if layer != "fallback" else 0.5,
            reason=reason,
            keyword_hit=keyword_hit,
            ollama_ok=snapshot.ollama_ok,
            openai_ok=snapshot.openai_ok,
            latency_ms_total=latency_ms,
            latency_ms_per_layer=latency_per_layer,
            estimated_cost_usd=self._cost_for_layer(layer),
            brownout_active=brownout_active,
            health_checked_at=health_checked_at,
            circuit_breakers={
                "ollama": "ok" if self._breakers.can_attempt("ollama") else "tripped",
                "openai": "ok" if self._breakers.can_attempt("openai") else "tripped",
            },
        )

        cost_guard = {
            "openai_allowed": openai_guard_allowed,
            "why": openai_guard_reason,
        }

        return RoutingDecision(record=record, cost_guard=cost_guard, escalation=escalation)
