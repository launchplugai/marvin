"""Escalation trigger detection for OpenAI routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

CODE_MARKERS = [
    "```",
    "traceback",
    "exception",
    "docker",
    "npm",
    "pip",
    "railway",
    "systemd",
    "python",
    "def ",
]

WORKFLOW_TERMS = [
    "bug",
    "fix",
    "review",
    "refactor",
    "pr",
    "pull request",
    "test failing",
    "deploy",
    "ci",
    "pipeline",
]

ARCHITECTURE_TERMS = [
    "system design",
    "module",
    "interface",
    "api contract",
    "schema",
    "routing",
]

SECURITY_TERMS = [
    "key",
    "token",
    "leak",
    "exposed",
    "cve",
    "auth",
]

ENGINEERING_MARKERS = CODE_MARKERS + WORKFLOW_TERMS + ARCHITECTURE_TERMS + SECURITY_TERMS

LONG_REQUEST_THRESHOLD = 400


@dataclass
class EscalationResult:
    triggered: bool
    reasons: List[str]


def contains_any(text: str, needles: List[str]) -> List[str]:
    lowered = text.lower()
    hits = []
    for needle in needles:
        if needle in lowered:
            hits.append(needle)
    return hits


def detect_escalation(text: str) -> EscalationResult:
    reasons: List[str] = []
    lowered = text.lower()

    code_hits = contains_any(lowered, CODE_MARKERS)
    if code_hits:
        reasons.append(f"code markers: {', '.join(code_hits)}")

    workflow_hits = contains_any(lowered, WORKFLOW_TERMS)
    if workflow_hits:
        reasons.append(f"workflow: {', '.join(workflow_hits)}")

    arch_hits = contains_any(lowered, ARCHITECTURE_TERMS)
    if arch_hits:
        reasons.append(f"architecture: {', '.join(arch_hits)}")

    security_hits = contains_any(lowered, SECURITY_TERMS)
    if security_hits:
        reasons.append(f"security: {', '.join(security_hits)}")

    if len(text) >= LONG_REQUEST_THRESHOLD:
        long_hits = contains_any(lowered, ENGINEERING_MARKERS)
        if long_hits:
            reasons.append("long+technical request")

    return EscalationResult(triggered=bool(reasons), reasons=reasons)


def derive_intent(text: str, keyword: str | None = None) -> str:
    if keyword:
        if keyword == "status":
            return "status"
        if keyword in {"help", "commands", "what can you do"}:
            return "howto"
        if keyword in {"health", "version", "router status", "budget"}:
            return "status"
    lowered = text.lower()
    if "roadmap" in lowered:
        return "unknown"
    if contains_any(lowered, SECURITY_TERMS):
        return "security"
    if contains_any(lowered, ARCHITECTURE_TERMS):
        return "architecture"
    if contains_any(lowered, CODE_MARKERS):
        return "code_debug"
    if contains_any(lowered, WORKFLOW_TERMS):
        return "code_review"
    if "how" in lowered or "instructions" in lowered:
        return "howto"
    if len(text) < 80:
        return "trivial"
    return "unknown"
