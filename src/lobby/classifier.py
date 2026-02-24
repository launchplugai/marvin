#!/usr/bin/env python3
"""
Lobby Router — Intent Classifier
Phase 1 Day 3

Uses Groq Llama 8B to classify messages into intent types.

Fast, cheap, accurate enough for routing decisions.
Fallback to keyword-based classification if LLM fails.
"""

import json
import logging
import requests
import os
from typing import Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Valid intent classifications."""
    STATUS_CHECK = "status_check"      # What's the current state?
    HOW_TO = "how_to"                   # How do I do X?
    CODE_REVIEW = "code_review"         # Review my code
    DEBUGGING = "debugging"             # Fix this error
    FEATURE_WORK = "feature_work"       # Build X feature
    TRIVIAL = "trivial"                 # Simple acknowledgement
    UNKNOWN = "unknown"                 # Doesn't fit


@dataclass
class Classification:
    """Result of intent classification."""
    intent: str  # One of IntentType values
    confidence: float  # 0.0-1.0
    method: str  # "keyword" or "llm"
    cacheable: bool
    ttl: int  # seconds
    reason: str


class LobbyClassifier:
    """
    Message intent classifier using Groq 8B.
    
    Design:
    1. Fast path: keyword matching (no API call)
    2. Slow path: LLM classification (if no keyword match)
    3. Fallback: hardcoded rules (if LLM fails)
    4. Result: JSON envelope with intent + metadata
    """
    
    def __init__(self, groq_api_key: str = None, model: str = "llama-3.1-8b-instant"):
        """Initialize classifier with Groq API."""
        if groq_api_key is None:
            groq_api_key = os.environ.get("GROQ_API_KEY")
        
        self.api_key = groq_api_key
        self.model = model
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        
        # Intent configuration
        self.intents = {
            IntentType.STATUS_CHECK: {
                "keywords": [
                    "status", "running", "health", "uptime", "working", "ok",
                    "how is", "what's the", "is the", "health check", "alive"
                ],
                "cacheable": True,
                "ttl": 60,
            },
            IntentType.HOW_TO: {
                "keywords": [
                    "how do i", "how to", "what's the command", "how can i",
                    "guide", "tutorial", "documentation", "help with"
                ],
                "cacheable": True,
                "ttl": 3600,
            },
            IntentType.CODE_REVIEW: {
                "keywords": [
                    "review", "check this", "look at", "pull request", "pr",
                    "code review", "audit", "feedback on code"
                ],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.DEBUGGING: {
                "keywords": [
                    "error", "broken", "fix", "debug", "why", "not working",
                    "issue", "bug", "failed", "crash", "exception"
                ],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.FEATURE_WORK: {
                "keywords": [
                    "build", "add", "create", "implement", "develop",
                    "new feature", "task", "epic", "story"
                ],
                "cacheable": False,
                "ttl": None,
            },
            IntentType.TRIVIAL: {
                "keywords": [
                    "thanks", "thank you", "ok", "cool", "nice", "good job",
                    "got it", "understood", "acknowledged"
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
        Classify a message into an intent type.
        
        Args:
            message: The user message
        
        Returns:
            Classification with intent, confidence, method, cacheable, ttl
        """
        # Phase 1: Fast keyword matching
        keyword_result = self._classify_by_keywords(message)
        if keyword_result:
            return keyword_result
        
        # Phase 2: LLM classification (if no keyword match)
        llm_result = self._classify_by_llm(message)
        if llm_result:
            return llm_result
        
        # Phase 3: Fallback
        return self._fallback_classification(message)
    
    def _classify_by_keywords(self, message: str) -> Optional[Classification]:
        """Try to classify using keyword matching (fast, no API)."""
        msg_lower = message.lower()
        
        for intent, config in self.intents.items():
            if intent == IntentType.UNKNOWN:
                continue
            
            # Check if any keyword matches
            for keyword in config["keywords"]:
                if keyword in msg_lower:
                    return Classification(
                        intent=intent.value,
                        confidence=0.95,  # High confidence for keyword matches
                        method="keyword",
                        cacheable=config["cacheable"],
                        ttl=config["ttl"],
                        reason=f"Matched keyword: '{keyword}'",
                    )
        
        return None
    
    def _classify_by_llm(self, message: str) -> Optional[Classification]:
        """Use Groq 8B for semantic classification."""
        if not self.api_key:
            logger.warning("No Groq API key, skipping LLM classification")
            return None
        
        prompt = f"""You are a message classifier. Classify this message into ONE category ONLY.

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

        try:
            response = requests.post(
                self.groq_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                    "temperature": 0.1,  # Low temp for consistency
                },
                timeout=10,
            )
            
            if response.status_code != 200:
                logger.warning(f"Groq API error: {response.status_code}")
                return None
            
            data = response.json()
            intent_str = data["choices"][0]["message"]["content"].strip().lower()
            
            # Validate intent
            valid_intents = [i.value for i in IntentType]
            if intent_str not in valid_intents:
                logger.warning(f"Invalid intent from LLM: {intent_str}")
                return None
            
            intent = IntentType(intent_str)
            config = self.intents[intent]
            
            return Classification(
                intent=intent.value,
                confidence=0.85,  # LLM classification
                method="llm",
                cacheable=config["cacheable"],
                ttl=config["ttl"],
                reason="Groq 8B semantic classification",
            )
            
        except requests.Timeout:
            logger.warning("Groq API timeout")
            return None
        except Exception as e:
            logger.error(f"LLM classification error: {e}")
            return None
    
    def _fallback_classification(self, message: str) -> Classification:
        """Fallback when both keyword and LLM fail."""
        logger.warning("Falling back to hardcoded classification")
        
        # Very simple heuristics
        msg_lower = message.lower()
        
        if len(message.split()) < 5:
            # Short messages → likely trivial
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
        
        # Default
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
            "model": self.model,
            "api_key_configured": bool(self.api_key),
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
    
    print("\n🎯 LOBBY CLASSIFIER TEST\n")
    for msg in test_messages:
        result = classifier.classify(msg)
        print(f"Message: {msg}")
        print(f"  Intent: {result.intent} (confidence: {result.confidence}, method: {result.method})")
        print(f"  Cacheable: {result.cacheable} (TTL: {result.ttl})")
        print(f"  Reason: {result.reason}\n")
