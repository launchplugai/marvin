"""
LLM Router — Tiered model routing with escalation.

Execution waterfall:
  1. Ollama (local, free, fast) — trivial/status/how_to
  2. Groq (free tier, rate-limited) — code_review/debugging
  3. Claude CLI (no API cost, uses claude binary) — complex/ambiguous/multi-step

Each tier returns a result or raises, triggering escalation to the next tier.
The Claude tier uses the `claude` CLI binary (already installed in the container)
instead of the Anthropic API — zero marginal cost.
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    tier: str           # ollama / groq / claude
    model: str          # actual model used
    tokens_used: int
    latency_ms: int
    escalated: bool     # did it escalate from a lower tier?


# Intent -> starting tier mapping
TIER_MAP = {
    "trivial": "ollama",
    "status_check": "ollama",
    "how_to": "ollama",
    "code_review": "groq",
    "debugging": "groq",
    "feature_work": "groq",
    "unknown": "groq",
}

# Escalation chain
ESCALATION = {
    "ollama": "groq",
    "groq": "claude",
    "claude": None,  # no further escalation
}


class OllamaBackend:
    """Local Ollama inference."""

    def __init__(self, host: str = None, model: str = "llama3.1:8b"):
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model

    def generate(self, prompt: str, system: str = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        start = time.time()
        resp = requests.post(
            f"{self.host}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False},
            timeout=60,
        )
        latency = int((time.time() - start) * 1000)
        resp.raise_for_status()

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

        return LLMResponse(
            content=content,
            tier="ollama",
            model=self.model,
            tokens_used=tokens,
            latency_ms=latency,
            escalated=False,
        )


class GroqBackend:
    """Groq cloud inference (free tier)."""

    def __init__(self, api_key: str = None, model: str = "llama-3.1-8b-instant"):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.model = model
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def generate(self, prompt: str, system: str = None) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY not set")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        start = time.time()
        resp = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.3,
            },
            timeout=30,
        )
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("Groq rate limited")
        resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)

        return LLMResponse(
            content=content,
            tier="groq",
            model=self.model,
            tokens_used=tokens,
            latency_ms=latency,
            escalated=False,
        )


class ClaudeCLIBackend:
    """
    Claude Code CLI backend — uses the `claude` binary, not the API.

    On the VPS, `claude` is already installed globally in the container.
    We pipe prompts to it via `claude -p` (print mode, non-interactive).
    This uses the existing Anthropic API key that's already loaded in the
    container environment — zero additional cost beyond the subscription.
    """

    def __init__(self, claude_bin: str = "claude", work_dir: str = None):
        self.claude_bin = claude_bin
        self.work_dir = work_dir or os.path.expanduser("~/projects")

    def generate(self, prompt: str, system: str = None) -> LLMResponse:
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n---\n\n{prompt}"

        start = time.time()
        result = subprocess.run(
            [self.claude_bin, "-p", full_prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.work_dir,
            env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "cli"},
        )
        latency = int((time.time() - start) * 1000)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"claude CLI exited with code {result.returncode}"
            raise RuntimeError(f"Claude CLI error: {error_msg}")

        content = result.stdout.strip()
        if not content:
            raise RuntimeError("Claude CLI returned empty response")

        return LLMResponse(
            content=content,
            tier="claude",
            model="claude-cli",
            tokens_used=0,  # CLI doesn't report token counts
            latency_ms=latency,
            escalated=False,
        )


class LLMRouter:
    """
    Routes requests through the LLM tier waterfall.

    Usage:
        router = LLMRouter()
        response = router.route("How do I run tests?", intent="how_to")
    """

    def __init__(self):
        self.backends = {
            "ollama": OllamaBackend(),
            "groq": GroqBackend(),
            "claude": ClaudeCLIBackend(),
        }

    def route(self, prompt: str, intent: str = "unknown",
              system: str = None, force_tier: str = None) -> LLMResponse:
        """
        Route a prompt through the appropriate LLM tier.

        Starts at the tier mapped to the intent.
        Escalates on failure (timeout, rate limit, error).
        """
        tier = force_tier or TIER_MAP.get(intent, "groq")
        escalated = False

        while tier:
            backend = self.backends.get(tier)
            if not backend:
                logger.error(f"No backend for tier: {tier}")
                tier = ESCALATION.get(tier)
                continue

            try:
                logger.info(f"Routing to {tier} (intent={intent})")
                response = backend.generate(prompt, system=system)
                response.escalated = escalated
                return response

            except Exception as e:
                logger.warning(f"Tier {tier} failed: {e}")
                next_tier = ESCALATION.get(tier)
                if next_tier:
                    logger.info(f"Escalating {tier} -> {next_tier}")
                    tier = next_tier
                    escalated = True
                else:
                    raise RuntimeError(f"All tiers exhausted. Last error: {e}") from e

        raise RuntimeError("No tier available")
