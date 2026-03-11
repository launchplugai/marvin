#!/usr/bin/env python3
"""
Rate Limit Header Parser
Phase 1 Day 4

Normalizes rate limit headers from Groq, Anthropic, OpenAI, and Moonshot
into a standard format. Called on EVERY API response — zero extra cost.
"""

import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


def parse_rate_limit_headers(headers: Dict[str, str], provider: str) -> Dict[str, Any]:
    """
    Normalize rate limit headers from any provider into standard format.

    Args:
        headers: HTTP response headers (case-insensitive dict)
        provider: One of "groq", "anthropic", "openai", "moonshot"

    Returns:
        Normalized dict with remaining_requests, remaining_tokens,
        health (green/yellow/red), bottleneck, etc.
    """
    # Normalize header keys to lowercase for consistent access
    h = {k.lower(): v for k, v in headers.items()}

    if provider in ("groq", "openai", "moonshot"):
        remaining_requests = _safe_int(h.get("x-ratelimit-remaining-requests"))
        limit_requests = _safe_int(h.get("x-ratelimit-limit-requests"))
        remaining_tokens = _safe_int(h.get("x-ratelimit-remaining-tokens"))
        limit_tokens = _safe_int(h.get("x-ratelimit-limit-tokens"))
        reset_requests = parse_reset_time(h.get("x-ratelimit-reset-requests", ""))
        reset_tokens = parse_reset_time(h.get("x-ratelimit-reset-tokens", ""))

    elif provider == "anthropic":
        remaining_requests = _safe_int(h.get("anthropic-ratelimit-requests-remaining"))
        limit_requests = _safe_int(h.get("anthropic-ratelimit-requests-limit"))
        remaining_tokens = _safe_int(h.get("anthropic-ratelimit-tokens-remaining"))
        limit_tokens = _safe_int(h.get("anthropic-ratelimit-tokens-limit"))
        reset_requests = h.get("anthropic-ratelimit-requests-reset", "")
        reset_tokens = h.get("anthropic-ratelimit-tokens-reset", "")

    else:
        logger.warning(f"Unknown provider: {provider}")
        return {"health": "unknown", "provider": provider}

    # Calculate percentages
    request_pct = (remaining_requests / limit_requests * 100) if limit_requests and limit_requests > 0 else 100.0
    token_pct = (remaining_tokens / limit_tokens * 100) if limit_tokens and limit_tokens > 0 else 100.0

    # Health is determined by the LOWER of the two
    lowest_pct = min(request_pct, token_pct)

    if lowest_pct > 20:
        health = "green"
    elif lowest_pct > 5:
        health = "yellow"
    else:
        health = "red"

    return {
        "provider": provider,
        "remaining_requests": remaining_requests,
        "limit_requests": limit_requests,
        "remaining_tokens": remaining_tokens,
        "limit_tokens": limit_tokens,
        "request_pct": round(request_pct, 1),
        "token_pct": round(token_pct, 1),
        "reset_requests": reset_requests,
        "reset_tokens": reset_tokens,
        "health": health,
        "bottleneck": "requests" if request_pct < token_pct else "tokens",
        "updated_at": _iso_now(),
    }


def parse_reset_time(raw: str) -> str:
    """
    Parse various reset time formats into ISO datetime string.

    Handles:
    - ISO format: "2026-03-01T14:30:00Z" -> passed through
    - Groq duration: "2m59.56s" -> converted to ISO
    - Seconds only: "7.66s" -> converted to ISO
    """
    if not raw:
        return ""

    # Already ISO format
    if "T" in raw:
        return raw

    # Groq duration format: "2m59.56s" or "7.66s" or "1h2m3s"
    total_seconds = 0.0

    h_match = re.search(r"(\d+)h", raw)
    m_match = re.search(r"(\d+)m", raw)
    s_match = re.search(r"([\d.]+)s", raw)

    if h_match:
        total_seconds += int(h_match.group(1)) * 3600
    if m_match:
        total_seconds += int(m_match.group(1)) * 60
    if s_match:
        total_seconds += float(s_match.group(1))

    if total_seconds > 0:
        reset_time = datetime.now(timezone.utc) + timedelta(seconds=total_seconds)
        return reset_time.isoformat()

    return raw  # Return as-is if unparseable


def _safe_int(val) -> int:
    """Safely convert header value to int, defaulting to -1."""
    if val is None:
        return -1
    try:
        return int(val)
    except (ValueError, TypeError):
        return -1


def _iso_now() -> str:
    """Current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()
