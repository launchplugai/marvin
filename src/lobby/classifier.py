#!/usr/bin/env python3
"""Lobby intent classifier with keyword-first routing and optional LLM fallback."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class IntentType(Enum):
    STATUS_CHECK = "status_check"
    HOW_TO = "how_to"
    CODE_REVIEW = "code_review"
    DEBUGGING = "debugging"
    FEATURE_WORK = "feature_work"
    TRIVIAL = "trivial"
    UNKNOWN = "unknown"


@dataclass
class Classification:
    intent: str
    confidence: float
    method: str
    cacheable: bool
    ttl: Optional[int]
    reason: str


class LobbyClassifier:
    """Classifies incoming messages into routing-friendly intent buckets."""

    def __init__(self, groq_api_key: str | None = None, model: str = "llama-3.1-8b-instant"):
        self.api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.model = model
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"

        self.intents: Dict[IntentType, Dict[str, object]] = {
            IntentType.STATUS_CHECK: {
                "keywords": [
                    "status", "running", "health", "uptime", "working", "alive", "what's the status", "how is", "is the",
                ],
                "cacheable": True,
                "ttl": 60,
            },
            IntentType.HOW_TO: {
                "keywords": ["how do i", "how to", "guide", "tutorial", "command", "documentation"],
                "cacheable": True,
                "ttl": 3600,
            },
            IntentType.CODE_REVIEW: {
                "keywords": ["review", "pull request", "pr", "feedback on code", "audit"],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.DEBUGGING: {
                "keywords": ["error", "broken", "fix", "debug", "issue", "bug", "failed", "crash", "crashed"],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.FEATURE_WORK: {
                "keywords": ["build", "add", "create", "implement", "new feature", "task", "epic"],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.TRIVIAL: {
                "keywords": ["thanks", "thank you", "cool", "nice", "got it", "understood"],
                "cacheable": True,
                "ttl": 86400,
            },
            IntentType.UNKNOWN: {"keywords": [], "cacheable": False, "ttl": None},
        }

    def classify(self, message: str) -> Classification:
        keyword_result = self._classify_by_keywords(message)
        if keyword_result:
            return keyword_result

        llm_result = self._classify_by_llm(message)
        if llm_result:
            return llm_result

        return self._fallback_classification(message)

    def _classify_by_keywords(self, message: str) -> Optional[Classification]:
        msg_lower = message.lower()
        best_match: Optional[Classification] = None
        best_score = 0

        for intent, config in self.intents.items():
            if intent == IntentType.UNKNOWN:
                continue

            score = 0
            matched_keyword = None
            for keyword in config["keywords"]:  # type: ignore[index]
                pattern = rf"\b{re.escape(keyword)}\b"
                if re.search(pattern, msg_lower):
                    score += max(1, len(keyword.split()))
                    matched_keyword = keyword

            if score > best_score and matched_keyword:
                best_score = score
                best_match = Classification(
                    intent=intent.value,
                    confidence=min(0.99, 0.9 + (score * 0.02)),
                    method="keyword",
                    cacheable=bool(config["cacheable"]),
                    ttl=config["ttl"],  # type: ignore[index]
                    reason=f"Matched keyword: '{matched_keyword}'",
                )

        return best_match

    def _classify_by_llm(self, message: str) -> Optional[Classification]:
        if not self.api_key:
            return None

        prompt = (
            "Classify into exactly one intent: status_check, how_to, code_review, debugging, feature_work, trivial, unknown. "
            "Return JSON only: {\"intent\": str, \"confidence\": float, \"reason\": str}."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
        }

        try:
            req = urllib.request.Request(
                self.groq_url,
                method="POST",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("LLM classification failed: %s", exc)
            return None

        intent_value = parsed.get("intent", IntentType.UNKNOWN.value)
        intent_type = next((i for i in IntentType if i.value == intent_value), IntentType.UNKNOWN)
        config = self.intents[intent_type]

        return Classification(
            intent=intent_type.value,
            confidence=float(parsed.get("confidence", 0.6)),
            method="llm",
            cacheable=bool(config["cacheable"]),
            ttl=config["ttl"],  # type: ignore[index]
            reason=str(parsed.get("reason", "LLM classification")),
        )

    def _fallback_classification(self, _message: str) -> Classification:
        return Classification(
            intent=IntentType.UNKNOWN.value,
            confidence=0.5,
            method="fallback",
            cacheable=False,
            ttl=None,
            reason="No keyword match and LLM unavailable",
        )

    def get_stats(self) -> dict:
        return {
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "intents_available": len(IntentType),
        }
