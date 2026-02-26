#!/usr/bin/env python3
"""
Marvin Gateway — Message Handler with Provider Cascade

Takes a user message, classifies it, generates a response through
the rate-limit-aware provider cascade:

  Keywords/trivial → Ollama (free, local)
  Complex work     → OpenAI → Kimi 2.5 (backup)
  Everything fails → hardcoded sorry message

This is what the Telegram bot calls instead of hitting OpenAI raw.
"""

import logging
import os
import requests
from typing import Optional

from lobby.classifier import LobbyClassifier, IntentType, OLLAMA_INTENTS, QUALITY_INTENTS
from lobby.rate_limiter import get_tracker

logger = logging.getLogger(__name__)


# Pre-built responses for trivial intents (no API call needed)
TRIVIAL_RESPONSES = {
    "thanks": "You're welcome!",
    "thank you": "You're welcome!",
    "ok": "Got it.",
    "cool": "Right on.",
    "nice": "Thanks!",
    "good job": "Appreciate it!",
    "got it": "Great.",
    "understood": "Perfect.",
    "acknowledged": "Noted.",
    "hi": "Hey! What can I help you with?",
    "hello": "Hey there! What do you need?",
    "hey": "What's up? How can I help?",
}


class MarvinGateway:
    """
    Full message-to-response pipeline.

    1. Classify the intent
    2. For trivial/greeting → instant local response
    3. For simple intents → Ollama generates response (free)
    4. For complex intents → OpenAI generates response (paid)
    5. If OpenAI rate limited → Kimi 2.5 generates response
    6. If everything fails → sorry message (never leaves user hanging)
    """

    def __init__(self):
        self.classifier = LobbyClassifier()
        self.tracker = get_tracker()

        # OpenAI config
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.openai_model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        self.openai_url = "https://api.openai.com/v1/chat/completions"

        # Kimi config
        self.kimi_api_key = os.environ.get("KIMI_API_KEY")
        self.kimi_model = os.environ.get("KIMI_MODEL", "moonshot-v1-auto")
        self.kimi_url = os.environ.get(
            "KIMI_API_URL", "https://api.moonshot.cn/v1/chat/completions"
        )

        # Ollama config
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")

        # Conversation history per user (simple in-memory, keyed by user_id)
        self.sessions = {}

    def handle_message(self, user_id: str, message: str) -> str:
        """
        Main entry point. Takes a message, returns a response.
        Never throws. Never returns empty. Always gives the user something.
        """
        try:
            # 1. Classify
            classification = self.classifier.classify(message)
            intent = IntentType(classification.intent)
            logger.info(
                "user=%s intent=%s method=%s confidence=%.2f",
                user_id, intent.value, classification.method, classification.confidence,
            )

            # 2. Trivial → instant canned response
            if intent == IntentType.TRIVIAL:
                return self._handle_trivial(message)

            # 3. Get/update conversation history
            history = self._get_history(user_id)
            history.append({"role": "user", "content": message})

            # 4. Route to appropriate provider
            if intent in OLLAMA_INTENTS:
                response = self._generate_ollama(history)
                if response:
                    self._save_response(user_id, history, response)
                    return response

            # 5. Quality provider cascade (OpenAI → Kimi)
            response = self._generate_quality(history)
            if response:
                self._save_response(user_id, history, response)
                return response

            # 6. Last resort: try Ollama for anything
            response = self._generate_ollama(history)
            if response:
                self._save_response(user_id, history, response)
                return response

            # 7. Total failure
            return (
                "All providers are currently rate limited. "
                "I'll be back online shortly — try again in a minute."
            )

        except Exception as e:
            logger.error("Gateway error for user %s: %s", user_id, e)
            return "Something went wrong on my end. Try again in a moment."

    def new_session(self, user_id: str) -> str:
        """Clear conversation history for a user."""
        self.sessions.pop(user_id, None)
        stats = self.classifier.get_stats()
        providers = []
        if self.classifier._check_ollama():
            providers.append(f"ollama/{self.ollama_model}")
        if self.openai_api_key:
            health = self.tracker.get_health("openai", self.openai_model)
            providers.append(f"openai/{self.openai_model} [{health}]")
        if self.kimi_api_key:
            health = self.tracker.get_health("moonshot", self.kimi_model)
            providers.append(f"kimi/{self.kimi_model} [{health}]")
        if not providers:
            providers.append("fallback only")
        return f"New session started. Providers: {', '.join(providers)}"

    def get_status(self) -> str:
        """Health check for all providers."""
        stats = self.classifier.get_stats()
        lines = ["Marvin Status:"]
        lines.append(f"  Ollama: {'UP' if stats.get('ollama_available') else 'DOWN'} ({self.ollama_model})")
        lines.append(f"  OpenAI: {stats.get('openai_health', 'unknown')} ({self.openai_model})")
        lines.append(f"  Kimi:   {stats.get('kimi_health', 'unknown')} ({self.kimi_model})")

        rate_limits = stats.get("rate_limits", {})
        if rate_limits:
            lines.append(f"  Rate limits: {rate_limits}")

        return "\n".join(lines)

    # ── Private methods ──

    def _handle_trivial(self, message: str) -> str:
        """Instant response for trivial messages. No API call."""
        msg_lower = message.lower().strip().rstrip("!?.,")
        for key, response in TRIVIAL_RESPONSES.items():
            if key in msg_lower:
                return response
        return "Got it."

    def _get_history(self, user_id: str) -> list:
        """Get conversation history, capped at last 20 messages."""
        if user_id not in self.sessions:
            self.sessions[user_id] = []
        return self.sessions[user_id][-20:]

    def _save_response(self, user_id: str, history: list, response: str):
        """Save assistant response to history."""
        history.append({"role": "assistant", "content": response})
        # Cap at 20 messages
        self.sessions[user_id] = history[-20:]

    def _generate_ollama(self, messages: list) -> Optional[str]:
        """Generate response using local Ollama."""
        if not self.classifier._check_ollama():
            return None

        system_msg = {
            "role": "system",
            "content": (
                "You are Marvin, a helpful AI assistant. "
                "Be concise and direct. Keep responses short unless detail is needed."
            ),
        }

        try:
            response = requests.post(
                f"{self.ollama_url}/v1/chat/completions",
                json={
                    "model": self.ollama_model,
                    "messages": [system_msg] + messages[-10:],
                    "max_tokens": 1024,
                    "temperature": 0.7,
                },
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            logger.warning("Ollama generate error: %s", response.status_code)
            return None
        except Exception as e:
            logger.error("Ollama generate failed: %s", e)
            return None

    def _generate_quality(self, messages: list) -> Optional[str]:
        """Generate response using OpenAI → Kimi cascade."""
        system_msg = {
            "role": "system",
            "content": (
                "You are Marvin, a helpful AI assistant. "
                "Be concise and direct. Keep responses short unless detail is needed."
            ),
        }
        full_messages = [system_msg] + messages[-10:]

        # Try OpenAI first
        if self.openai_api_key and self.tracker.is_available("openai", self.openai_model):
            result = self._call_chat(
                self.openai_url, self.openai_api_key, self.openai_model,
                full_messages, "openai",
            )
            if result:
                return result

        # Try Kimi
        if self.kimi_api_key and self.tracker.is_available("moonshot", self.kimi_model):
            result = self._call_chat(
                self.kimi_url, self.kimi_api_key, self.kimi_model,
                full_messages, "moonshot",
            )
            if result:
                return result

        return None

    def _call_chat(
        self, url: str, api_key: str, model: str,
        messages: list, provider: str,
    ) -> Optional[str]:
        """Call an OpenAI-compatible chat API with rate limit tracking."""
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 1024,
                    "temperature": 0.7,
                },
                timeout=30,
            )

            if response.status_code == 200:
                self.tracker.update(provider, model, dict(response.headers))
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()

            if response.status_code == 429:
                retry_after = int(response.headers.get("retry-after", 60))
                self.tracker.update_on_429(provider, model, retry_after)
                logger.warning(
                    "%s 429 rate limited — RED for %ds", provider, retry_after
                )
                return None

            if any(
                k.startswith("x-ratelimit") or k.startswith("anthropic-ratelimit")
                for k in response.headers
            ):
                self.tracker.update(provider, model, dict(response.headers))

            logger.warning("%s chat error: %s", provider, response.status_code)
            return None

        except requests.Timeout:
            logger.warning("%s chat timeout", provider)
            return None
        except Exception as e:
            logger.error("%s chat failed: %s", provider, e)
            return None
