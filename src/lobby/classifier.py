#!/usr/bin/env python3
"""
Lobby Router — Intent Classifier

OpenAI for real work. Ollama (local) for cheap stuff.

Routing logic:
1. Keywords — instant, no API call
2. Ollama (local) — heartbeats, status, trivial, how-to
3. OpenAI — code review, debugging, feature work, anything Ollama can't handle
4. Hardcoded fallback — if everything fails
"""

import json
import logging
import requests
import os
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Valid intent classifications."""
    STATUS_CHECK = "status_check"
    HOW_TO = "how_to"
    CODE_REVIEW = "code_review"
    DEBUGGING = "debugging"
    FEATURE_WORK = "feature_work"
    TRIVIAL = "trivial"
    UNKNOWN = "unknown"


# Intents cheap enough for Ollama to handle
OLLAMA_INTENTS = {
    IntentType.STATUS_CHECK,
    IntentType.HOW_TO,
    IntentType.TRIVIAL,
    IntentType.UNKNOWN,
}

# Intents that need OpenAI quality
OPENAI_INTENTS = {
    IntentType.CODE_REVIEW,
    IntentType.DEBUGGING,
    IntentType.FEATURE_WORK,
}


@dataclass
class Classification:
    """Result of intent classification."""
    intent: str
    confidence: float
    method: str  # "keyword", "ollama", "openai", "fallback"
    cacheable: bool
    ttl: int
    reason: str


class LobbyClassifier:
    """
    Message intent classifier.

    Ollama handles cheap/fast classification locally.
    OpenAI handles complex work that needs quality.

    Flow:
    1. Keyword match (free, instant)
    2. Ollama classify (free, local, fast)
    3. If intent needs OpenAI quality -> re-classify with OpenAI
    4. Hardcoded fallback if all else fails
    """

    def __init__(
        self,
        openai_api_key: str = None,
        openai_model: str = "gpt-4o-mini",
        ollama_url: str = None,
        ollama_model: str = None,
    ):
        # OpenAI config
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self.openai_model = openai_model
        self.openai_url = "https://api.openai.com/v1/chat/completions"

        # Ollama config (local, no auth needed)
        self.ollama_url = ollama_url or os.environ.get(
            "OLLAMA_URL", "http://127.0.0.1:11434"
        )
        self.ollama_model = ollama_model or os.environ.get(
            "OLLAMA_MODEL", "llama3.2"
        )
        self.ollama_available = None  # checked on first use

        # Intent configuration
        self.intents = {
            IntentType.STATUS_CHECK: {
                "keywords": [
                    "status", "running", "health", "uptime", "working",
                    "how is", "is the", "health check", "alive",
                ],
                "cacheable": True,
                "ttl": 60,
            },
            IntentType.HOW_TO: {
                "keywords": [
                    "how do i", "how to", "what's the command", "how can i",
                    "guide", "tutorial", "documentation", "help with",
                ],
                "cacheable": True,
                "ttl": 3600,
            },
            IntentType.CODE_REVIEW: {
                "keywords": [
                    "review", "check this", "look at", "pull request", "pr",
                    "code review", "audit", "feedback on code",
                ],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.DEBUGGING: {
                "keywords": [
                    "error", "broken", "fix", "debug", "why", "not working",
                    "issue", "bug", "failed", "crash", "exception",
                ],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.FEATURE_WORK: {
                "keywords": [
                    "build", "add", "create", "implement", "develop",
                    "new feature", "task", "epic", "story",
                ],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.TRIVIAL: {
                "keywords": [
                    "thanks", "thank you", "ok", "cool", "nice", "good job",
                    "got it", "understood", "acknowledged",
                ],
                "cacheable": True,
                "ttl": 86400,
            },
            IntentType.UNKNOWN: {
                "keywords": [],
                "cacheable": False,
                "ttl": None,
            },
        }

    def classify(self, message: str) -> Classification:
        """
        Classify a message. Ollama first, OpenAI only when needed.

        1. Keywords (free)
        2. Ollama (free, local)
        3. OpenAI (only for complex intents or if Ollama is down)
        4. Fallback (hardcoded)
        """
        # Phase 1: Keywords
        keyword_result = self._classify_by_keywords(message)
        if keyword_result:
            return keyword_result

        # Phase 2: Try Ollama first (free, local)
        ollama_result = self._classify_by_ollama(message)
        if ollama_result:
            intent = IntentType(ollama_result.intent)
            # If Ollama says it's complex work, confirm with OpenAI
            if intent in OPENAI_INTENTS:
                openai_result = self._classify_by_openai(message)
                if openai_result:
                    return openai_result
            # Ollama's answer is good enough for simple stuff
            return ollama_result

        # Phase 3: Ollama unavailable — use OpenAI
        openai_result = self._classify_by_openai(message)
        if openai_result:
            return openai_result

        # Phase 4: Everything failed
        return self._fallback_classification(message)

    def _classify_by_keywords(self, message: str) -> Optional[Classification]:
        """Keyword matching. Free, instant."""
        msg_lower = message.lower()

        for intent, config in self.intents.items():
            if intent == IntentType.UNKNOWN:
                continue
            for keyword in config["keywords"]:
                if keyword in msg_lower:
                    return Classification(
                        intent=intent.value,
                        confidence=0.95,
                        method="keyword",
                        cacheable=config["cacheable"],
                        ttl=config["ttl"],
                        reason=f"Matched keyword: '{keyword}'",
                    )
        return None

    def _check_ollama(self) -> bool:
        """Check if Ollama is reachable. Cached after first check."""
        if self.ollama_available is not None:
            return self.ollama_available
        try:
            r = requests.get(
                f"{self.ollama_url}/api/version", timeout=2
            )
            self.ollama_available = r.status_code == 200
        except Exception:
            self.ollama_available = False
        if not self.ollama_available:
            logger.warning("Ollama not reachable at %s", self.ollama_url)
        return self.ollama_available

    def _classify_by_ollama(self, message: str) -> Optional[Classification]:
        """Classify using local Ollama. Free, no API cost."""
        if not self._check_ollama():
            return None

        prompt = self._classification_prompt(message)

        try:
            response = requests.post(
                f"{self.ollama_url}/v1/chat/completions",
                json={
                    "model": self.ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                    "temperature": 0.1,
                },
                timeout=10,
            )

            if response.status_code != 200:
                logger.warning("Ollama API error: %s", response.status_code)
                return None

            data = response.json()
            intent_str = data["choices"][0]["message"]["content"].strip().lower()

            valid_intents = [i.value for i in IntentType]
            if intent_str not in valid_intents:
                logger.warning("Invalid intent from Ollama: %s", intent_str)
                return None

            intent = IntentType(intent_str)
            config = self.intents[intent]

            return Classification(
                intent=intent.value,
                confidence=0.80,
                method="ollama",
                cacheable=config["cacheable"],
                ttl=config["ttl"],
                reason=f"Ollama {self.ollama_model} (local)",
            )

        except requests.Timeout:
            logger.warning("Ollama timeout")
            return None
        except Exception as e:
            logger.error("Ollama classification error: %s", e)
            return None

    def _classify_by_openai(self, message: str) -> Optional[Classification]:
        """Classify using OpenAI. Only for complex work or Ollama fallback."""
        if not self.openai_api_key:
            logger.warning("No OpenAI API key, skipping")
            return None

        prompt = self._classification_prompt(message)

        try:
            response = requests.post(
                self.openai_url,
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.openai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                    "temperature": 0.1,
                },
                timeout=15,
            )

            if response.status_code != 200:
                logger.warning("OpenAI API error: %s", response.status_code)
                return None

            data = response.json()
            intent_str = data["choices"][0]["message"]["content"].strip().lower()

            valid_intents = [i.value for i in IntentType]
            if intent_str not in valid_intents:
                logger.warning("Invalid intent from OpenAI: %s", intent_str)
                return None

            intent = IntentType(intent_str)
            config = self.intents[intent]

            return Classification(
                intent=intent.value,
                confidence=0.90,
                method="openai",
                cacheable=config["cacheable"],
                ttl=config["ttl"],
                reason=f"OpenAI {self.openai_model}",
            )

        except requests.Timeout:
            logger.warning("OpenAI timeout")
            return None
        except Exception as e:
            logger.error("OpenAI classification error: %s", e)
            return None

    def _classification_prompt(self, message: str) -> str:
        """Shared prompt for both Ollama and OpenAI."""
        return f"""You are a message classifier. Classify this message into ONE category ONLY.

Categories and examples:
- status_check: "What's the status?" "Is it running?" "Health check?" "Uptime?" "How is X?"
- how_to: "How do I run tests?" "What's the command?" "Guide to X?" "Documentation?"
- code_review: "Review my code" "Check this PR" "Feedback on this"
- debugging: "Fix this error" "Why is it broken?" "Debug this issue"
- feature_work: "Build X feature" "Add Y" "Implement Z" "Task: do X"
- trivial: "Thanks!" "Got it" "Cool" "Nice job"
- unknown: Doesn't fit above

Message: "{message}"

Respond with ONLY the category name in lowercase (status_check, how_to, etc), no explanation."""

    def _fallback_classification(self, message: str) -> Classification:
        """Hardcoded fallback when both Ollama and OpenAI fail."""
        logger.warning("Falling back to hardcoded classification")

        msg_lower = message.lower()

        if len(message.split()) < 5:
            return Classification(
                intent=IntentType.TRIVIAL.value,
                confidence=0.5,
                method="fallback",
                cacheable=True,
                ttl=86400,
                reason="Short message (fallback)",
            )

        if any(word in msg_lower for word in ["error", "fix", "broken"]):
            return Classification(
                intent=IntentType.DEBUGGING.value,
                confidence=0.6,
                method="fallback",
                cacheable=False,
                ttl=None,
                reason="Contains error keywords (fallback)",
            )

        return Classification(
            intent=IntentType.UNKNOWN.value,
            confidence=0.0,
            method="fallback",
            cacheable=False,
            ttl=None,
            reason="Could not classify (fallback)",
        )

    def get_stats(self) -> dict:
        """Get classifier statistics."""
        return {
            "openai_model": self.openai_model,
            "openai_key_configured": bool(self.openai_api_key),
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "ollama_available": self.ollama_available,
            "intents_available": len(self.intents),
        }


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    classifier = LobbyClassifier()

    test_messages = [
        "What's the status of BetApp?",
        "How do I run the test suite?",
        "Review my code in this PR",
        "The app keeps crashing with error 500",
        "Build the dashboard feature",
        "Thanks!",
        "Blah blah random stuff",
    ]

    print("\nLOBBY CLASSIFIER TEST\n")
    print(f"Stats: {json.dumps(classifier.get_stats(), indent=2)}\n")
    for msg in test_messages:
        result = classifier.classify(msg)
        print(f"Message: {msg}")
        print(f"  Intent: {result.intent} (confidence: {result.confidence}, method: {result.method})")
        print(f"  Cacheable: {result.cacheable} (TTL: {result.ttl})")
        print(f"  Reason: {result.reason}\n")
