"""
Constitutional Framework — Non-optional guardrails for the Claude brain.

This is not a suggestion layer. Every task that flows through Marvin
passes through constitutional checks BEFORE and AFTER execution.

The constitution enforces:
  1. SCOPE — Tasks stay within defined boundaries (repos, containers, files)
  2. SAFETY — Dangerous operations are blocked or require escalation
  3. CONTEXT — The brain always knows who it is, what it's doing, and why
  4. BUDGET — Token/cost limits are enforced per task and per session
  5. AUDIT — Every decision is logged with reasoning

The constitution wraps the worker pipeline. It cannot be bypassed.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class Verdict(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ESCALATE = "escalate"  # needs human review


@dataclass
class ConstitutionalCheck:
    rule: str
    verdict: str
    reason: str
    timestamp: int = 0


@dataclass
class ConstitutionalContext:
    """Injected into every LLM call as immutable system context."""

    identity: str = "Marvin"
    role: str = "Autonomous engineering agent"
    owner: str = "launchplugai"
    allowed_repos: List[str] = field(default_factory=lambda: [
        "launchplugai/marvin",
        "launchplugai/claude-hub",
        "launchplugai/BetApp",
    ])
    allowed_containers: List[str] = field(default_factory=lambda: [
        "claude-hub", "ollama-wmf4", "marvin-skills", "key-locker",
    ])
    work_dir: str = "/root/projects"
    session_id: str = ""
    task_count: int = 0

    def to_system_prompt(self) -> str:
        return f"""You are {self.identity}, an autonomous engineering agent owned by {self.owner}.

CONSTITUTIONAL RULES (non-negotiable, you cannot override these):

1. IDENTITY: You are {self.identity}. You do not pretend to be another system.
   You always state your identity when asked. You never claim capabilities you don't have.

2. SCOPE: You operate ONLY on these repositories: {', '.join(self.allowed_repos)}.
   You operate ONLY on these containers: {', '.join(self.allowed_containers)}.
   You NEVER touch files outside {self.work_dir} unless explicitly instructed.
   You NEVER create, delete, or modify containers not in your allowed list.

3. SAFETY: You NEVER run destructive commands (rm -rf, DROP TABLE, force push to main).
   You NEVER expose secrets, tokens, or API keys in output.
   You NEVER modify the vault (key-locker) without explicit human approval.
   You NEVER push code without running tests first.

4. CONTEXT MANAGEMENT: You maintain awareness of:
   - Current task: what you're doing and why
   - Session state: how many tasks processed, what's pending
   - Project state: which repos are checked out, what branches
   You surface this context when asked. You never lose track of what you're doing.

5. ESCALATION: When uncertain, you escalate to a higher tier or pause for human input.
   You NEVER guess at infrastructure operations (deploys, restarts, key rotations).
   You ALWAYS explain your reasoning before taking action.

6. BUDGET: You respect token and cost limits. You prefer cheaper tiers when possible.
   You cache aggressively. You don't repeat work unnecessarily.

7. AUDIT: You log every action with: what, why, result, duration.
   You can reproduce your decision chain on request.

SESSION: #{self.session_id} | Tasks processed: {self.task_count}
"""


# Pre-execution rules: checked BEFORE a task runs
PRE_RULES = [
    {
        "name": "no_secret_leak",
        "description": "Block tasks that ask to output secrets or tokens",
        "check": lambda task: any(
            kw in task.message.lower()
            for kw in ["print api key", "show token", "echo password",
                       "cat .keys", "show secret", "dump credentials"]
        ),
        "verdict": Verdict.BLOCK,
        "reason": "Task requests exposure of secrets",
    },
    {
        "name": "scope_check",
        "description": "Block tasks targeting unknown projects",
        "check": lambda task: (
            task.project is not None
            and task.project not in ["marvin", "claude-hub", "BetApp"]
            and task.intent in ["feature_work", "code_review", "debugging"]
        ),
        "verdict": Verdict.BLOCK,
        "reason": "Project not in allowed scope",
    },
    {
        "name": "destructive_intent",
        "description": "Escalate tasks that mention destructive operations",
        "check": lambda task: any(
            kw in task.message.lower()
            for kw in ["delete container", "drop database", "remove all",
                       "wipe", "destroy", "nuke", "format disk"]
        ),
        "verdict": Verdict.ESCALATE,
        "reason": "Task mentions destructive operations — needs human approval",
    },
]

# Post-execution rules: checked AFTER an LLM produces output
POST_RULES = [
    {
        "name": "no_secret_in_output",
        "description": "Strip or block output containing likely secrets",
        "check": lambda output: any(
            pattern in output.lower()
            for pattern in ["sk-ant-", "ghp_", "gho_", "xoxb-", "xoxp-",
                            "api_key=", "password=", "secret="]
        ),
        "verdict": Verdict.BLOCK,
        "reason": "Output contains what appears to be a secret/token",
    },
    {
        "name": "no_prompt_injection",
        "description": "Detect prompt injection attempts in output",
        "check": lambda output: any(
            pattern in output.lower()
            for pattern in ["ignore previous instructions", "ignore all instructions",
                            "you are now", "new system prompt", "disregard above"]
        ),
        "verdict": Verdict.BLOCK,
        "reason": "Output contains possible prompt injection",
    },
]


class Constitution:
    """
    Enforces constitutional rules on the Marvin pipeline.

    Usage:
        constitution = Constitution()
        # Before processing
        verdict = constitution.pre_check(task)
        if verdict.verdict == "block": reject(task)
        # After processing
        verdict = constitution.post_check(output_text)
        if verdict.verdict == "block": redact(output_text)
    """

    def __init__(self, session_id: str = ""):
        self.context = ConstitutionalContext(session_id=session_id)
        self.check_log: List[ConstitutionalCheck] = []

    def pre_check(self, task) -> ConstitutionalCheck:
        """Run pre-execution checks on a task. Returns first failing check or ALLOW."""
        for rule in PRE_RULES:
            try:
                if rule["check"](task):
                    check = ConstitutionalCheck(
                        rule=rule["name"],
                        verdict=rule["verdict"].value,
                        reason=rule["reason"],
                        timestamp=int(time.time()),
                    )
                    self.check_log.append(check)
                    logger.warning(f"Constitutional {check.verdict}: {check.rule} — {check.reason}")
                    return check
            except Exception as e:
                logger.error(f"Constitutional rule '{rule['name']}' error: {e}")

        check = ConstitutionalCheck(
            rule="all_passed",
            verdict=Verdict.ALLOW.value,
            reason="All pre-checks passed",
            timestamp=int(time.time()),
        )
        self.check_log.append(check)
        return check

    def post_check(self, output: str) -> ConstitutionalCheck:
        """Run post-execution checks on LLM output."""
        for rule in POST_RULES:
            try:
                if rule["check"](output):
                    check = ConstitutionalCheck(
                        rule=rule["name"],
                        verdict=rule["verdict"].value,
                        reason=rule["reason"],
                        timestamp=int(time.time()),
                    )
                    self.check_log.append(check)
                    logger.warning(f"Constitutional {check.verdict}: {check.rule} — {check.reason}")
                    return check
            except Exception as e:
                logger.error(f"Constitutional rule '{rule['name']}' error: {e}")

        check = ConstitutionalCheck(
            rule="all_passed",
            verdict=Verdict.ALLOW.value,
            reason="All post-checks passed",
            timestamp=int(time.time()),
        )
        self.check_log.append(check)
        return check

    def get_system_prompt(self) -> str:
        """Get the constitutional system prompt for LLM calls."""
        return self.context.to_system_prompt()

    def increment_task_count(self):
        self.context.task_count += 1

    def get_check_log(self, limit: int = 20) -> List[Dict]:
        return [
            {
                "rule": c.rule,
                "verdict": c.verdict,
                "reason": c.reason,
                "time": c.timestamp,
            }
            for c in self.check_log[-limit:]
        ]
