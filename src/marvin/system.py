"""Runnable Marvin orchestration loop."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from cache.cache import CacheLayer
from cache.key_generator import CacheKeyGenerator
from lobby.classifier import LobbyClassifier
from marvin.transmission import EnvelopeFactory, append_execution_step
from marvin.vps import HostingerVPSClient


class MarvinSystem:
    def __init__(
        self,
        classifier: LobbyClassifier | None = None,
        cache: CacheLayer | None = None,
        keygen: CacheKeyGenerator | None = None,
        vps_client: HostingerVPSClient | None = None,
    ):
        self.classifier = classifier or LobbyClassifier()
        self.cache = cache or CacheLayer()
        self.keygen = keygen or CacheKeyGenerator()
        self.vps_client = vps_client or HostingerVPSClient.from_env()

    def handle(self, message: str, project: str = ".") -> Dict[str, Any]:
        classification = self.classifier.classify(message)
        envelope = EnvelopeFactory.build(
            user_message=message,
            project=project,
            intent=classification.intent,
            cacheable=classification.cacheable,
        )
        append_execution_step(envelope, "classification", "ok", classification.reason)

        state_sig = self.keygen.get_project_state_sig(project)
        cached = self.cache.get(classification.intent, project=project, state_sig=state_sig)
        if cached:
            append_execution_step(envelope, "cache", "hit", "served from cache")
            return {
                "envelope": asdict(envelope),
                "classification": asdict(classification),
                "cache": {"hit": True, "hit_count": cached["hit_count"]},
                "response": cached["value"],
            }

        append_execution_step(envelope, "cache", "miss", "no cached response")

        response_payload = self._dispatch(envelope.department, classification.intent, message)
        append_execution_step(envelope, "dispatch", "ok", f"department={envelope.department}")

        if classification.cacheable:
            self.cache.put(
                intent=classification.intent,
                project=project,
                state_sig=state_sig,
                response=response_payload,
                tokens_saved=max(1, len(message.split()) * 2),
            )
            append_execution_step(envelope, "cache_write", "ok", "response cached")

        return {
            "envelope": asdict(envelope),
            "classification": asdict(classification),
            "cache": {"hit": False},
            "response": response_payload,
        }

    def close(self) -> None:
        self.cache.close()

    def _dispatch(self, department: str, intent: str, message: str) -> Dict[str, Any]:
        if intent == "status_check":
            vps_hint = self._maybe_attach_vps_status(message)
            return {
                "summary": "System operational.",
                "department": department,
                "intent": intent,
                "next_action": "Continue monitoring.",
                "vps": vps_hint,
            }
        if intent == "how_to":
            return {
                "summary": "Use `pytest -q` for tests and `python -m marvin.main \"<msg>\"` to run orchestration.",
                "department": department,
                "intent": intent,
                "next_action": "Follow the command sequence.",
            }
        return {
            "summary": f"Routed to {department} for {intent}.",
            "department": department,
            "intent": intent,
            "next_action": f"Analyze request: {message[:120]}",
        }

    def _maybe_attach_vps_status(self, message: str) -> Dict[str, Any]:
        if not self.vps_client:
            return {"configured": False, "note": "Set HOSTINGER_API_TOKEN to enable VPS status checks."}

        lowered = message.lower()
        if not any(k in lowered for k in ("vps", "hostinger", "server", "container", "status")):
            return {"configured": True, "queried": False}

        snapshot = self.vps_client.get_status_snapshot()
        if snapshot.get("ok"):
            return {"configured": True, "queried": True, "ok": True, "data": snapshot.get("data")}

        return {
            "configured": True,
            "queried": True,
            "ok": False,
            "error": snapshot.get("error"),
            "details": snapshot.get("details"),
        }
