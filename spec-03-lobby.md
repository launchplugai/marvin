# Document 3 of 8: THE LOBBY
## Groq Llama 8B — Stateless Classification Router

**Purpose:** First contact. One job: stamp the ticket. Never holds a conversation, never accumulates context, never tries to help. Classify and hand off.

---

## MODEL CONFIG

```json
{
  "agent_id": "lobby-router",
  "model": "llama-3.1-8b-instant",
  "provider": "groq",
  "temperature": 0.1,
  "maxTokens": 150,
  "maxHistoryMessages": 0,
  "accumulateContext": false,
  "timeout_ms": 5000,
  "retry": {
    "max_attempts": 2,
    "backoff_ms": 500
  },
  "fallback": {
    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
    "provider": "groq",
    "reason": "separate rate pool, 1K RPD backup"
  },
  "rate_limits_free": {
    "rpm": 30,
    "rpd": 14400,
    "tpm": 6000,
    "tpd": 500000
  }
}
```

### Why These Settings

| Setting | Value | Rationale |
|---------|-------|-----------|
| temperature | 0.1 | Near-deterministic. Same input → same classification. |
| maxTokens | 150 | JSON output is ~50-80 tokens. 150 is generous ceiling. |
| maxHistoryMessages | 0 | **Stateless.** Never sees previous messages. Every call is fresh. |
| accumulateContext | false | **No memory.** This is a stamp machine, not a conversationalist. |
| timeout_ms | 5000 | If 8B can't classify in 5 seconds, something is wrong. Fail to fallback. |

---

## SYSTEM PROMPT

```
You are a LOBBY ROUTER. You do NOT solve problems. You do NOT hold conversations.
You do NOT explain anything. You do NOT ask follow-up questions.

On EVERY message, output ONLY valid JSON matching this exact schema:

{
  "intent": "<one of: status_check, how_to, fix_error, code_task, deploy, test, planning, conversation, trivial>",
  "complexity": "<one of: low, medium, high>",
  "project": "<one of: betapp, brand-engine, openclaw, unknown>",
  "department": "<one of: ralph, ira, tess, general>",
  "can_cache": <true or false>
}

CLASSIFICATION RULES:

intent:
- status_check: "what's the state of X", "how's X doing", "where are we on X"
- how_to: "how do I", "what's the command for", "show me how"
- fix_error: mentions error, bug, failure, broken, exception, traceback
- code_task: write code, implement, refactor, add feature, create
- deploy: deploy, push, release, railway, VPS, DNS, production
- test: test, coverage, passing, failing, pytest, suite
- planning: sprint, roadmap, priority, next steps, schedule, phase
- conversation: greeting, opinion, discussion, no clear task
- trivial: one-word, "thanks", "ok", "hey", time/date questions

complexity:
- low: single fact lookup, yes/no, simple command
- medium: requires some context or multi-step but routine
- high: debugging, architecture, multi-file changes, cross-system

project:
- betapp: mentions DNA, BetApp, parlay, heuristic, sports, bets, dna-matrix
- brand-engine: mentions brand, marketing, content, social
- openclaw: mentions openclaw, agent, delegation, routing, this system
- unknown: can't determine from message alone

department:
- ralph: planning, sprints, roadmap, priorities, scheduling
- ira: deploy, infrastructure, VPS, DNS, monitoring, servers
- tess: tests, coverage, failures, quality, pytest, validation
- general: doesn't clearly fit one department

can_cache:
- true: factual question, status check, how-to, reference
- false: conversation, opinion, context-dependent debugging, active coding

OUTPUT ONLY THE JSON. NO PREAMBLE. NO EXPLANATION. NO MARKDOWN FENCES.
```

**Token count:** ~350 tokens for system prompt. User message: ~100-500. Response: ~50-80. **Total per call: ~500-900 tokens.**

At 6,000 TPM: **6-12 classifications per minute.**
At 14,400 RPD: **10 per minute sustained over 24 hours.**

---

## CLASSIFICATION SCHEMA

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class Classification:
    intent: Literal[
        "status_check", "how_to", "fix_error", "code_task",
        "deploy", "test", "planning", "conversation", "trivial"
    ]
    complexity: Literal["low", "medium", "high"]
    project: Literal["betapp", "brand-engine", "openclaw", "unknown"]
    department: Literal["ralph", "ira", "tess", "general"]
    can_cache: bool
```

---

## PARSING THE 8B OUTPUT

The 8B will occasionally break format. Handle it defensively:

```python
import json

def parse_lobby_response(raw_text: str) -> Classification | None:
    """
    Parse 8B output into Classification.
    Handles common failure modes:
    - Markdown fences (```json ... ```)
    - Preamble text before JSON
    - Trailing explanation after JSON
    - Complete format failure
    """
    text = raw_text.strip()
    
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    
    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    
    if start == -1 or end == 0:
        return None  # No JSON found — fallback to default routing
    
    try:
        data = json.loads(text[start:end])
        return Classification(
            intent=data.get("intent", "conversation"),
            complexity=data.get("complexity", "medium"),
            project=data.get("project", "unknown"),
            department=data.get("department", "general"),
            can_cache=data.get("can_cache", False)
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None  # Parse failed — fallback to default routing


def fallback_classification() -> Classification:
    """When 8B fails to classify, safe default: send to Kimi via general"""
    return Classification(
        intent="conversation",
        complexity="medium",
        project="unknown",
        department="general",
        can_cache=False
    )
```

---

## LOBBY → ENVELOPE INTEGRATION

```python
def lobby_classify(user_message: str) -> dict:
    """
    Full lobby flow:
    1. Call 8B for classification
    2. Parse response
    3. Start building envelope
    4. Return envelope for next layer (cache check)
    """
    import time
    
    # Call Groq 8B
    raw = call_groq(
        model="llama-3.1-8b-instant",
        system_prompt=LOBBY_SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=150,
        temperature=0.1
    )
    
    # Parse (with fallback)
    classification = parse_lobby_response(raw)
    if classification is None:
        classification = fallback_classification()
    
    # Start envelope
    envelope = {
        "envelope_id": generate_envelope_id(),
        "created_at": iso_now(),
        "updated_at": iso_now(),
        "original_message": {
            "text": user_message,
            "sender": "user",
            "timestamp": iso_now(),
            "medium": detect_medium()
        },
        "classification": {
            "classified_by": "lobby-8b",
            "intent": classification.intent,
            "complexity": classification.complexity,
            "project": classification.project,
            "department": classification.department,
            "can_cache": classification.can_cache,
            "confidence": 0.85,  # static for now, can add calibration later
            "timestamp": iso_now()
        },
        "cache_result": None,     # filled by cache layer
        "routing": None,          # filled by receptionist
        "context_primer": None,   # filled by cache layer
        "execution_chain": [],
        "rate_limit_state": get_current_rate_limits()
    }
    
    return envelope
```

---

## FAILURE MODES + HANDLING

| Failure | Detection | Response |
|---------|-----------|----------|
| 8B returns prose instead of JSON | `parse_lobby_response()` returns None | Use `fallback_classification()` → route to general/Kimi |
| 8B rate limited (429) | HTTP status code | Switch to Llama 4 Scout fallback (separate pool) |
| 8B timeout (>5s) | timeout_ms exceeded | Skip lobby, route directly to Haiku with raw message |
| Groq API down | Connection error | Skip lobby entirely, Haiku classifies + routes (degraded mode) |
| Wrong classification | Downstream model detects mismatch | Department head self-corrects or escalates. Log for accuracy tracking. |

### Degraded Mode (Lobby Unavailable)

```python
def route_message(user_message: str) -> dict:
    """Main entry point with lobby bypass on failure"""
    try:
        envelope = lobby_classify(user_message)
    except (RateLimitError, TimeoutError, ConnectionError) as e:
        # Lobby down — skip to Haiku with minimal envelope
        envelope = create_minimal_envelope(user_message)
        envelope["classification"] = {
            "classified_by": "bypass",
            "intent": "conversation",  # safe default
            "complexity": "medium",
            "project": "unknown",
            "department": "general",
            "can_cache": False,
            "confidence": 0.0,  # signals: this was not classified
            "timestamp": iso_now()
        }
        log_event("lobby_bypass", str(e))
    
    # Continue to cache layer regardless
    return check_cache(envelope)
```

---

## TESTING CHECKLIST

- [ ] Feed 30 real messages from recent chat history
- [ ] Verify JSON output on every single one (no prose, no markdown)
- [ ] Check intent accuracy: target >80% correct
- [ ] Check project detection: target >90% correct  
- [ ] Check department routing: target >75% correct
- [ ] Verify fallback_classification fires on malformed output
- [ ] Simulate Groq 429 → verify Scout fallback activates
- [ ] Simulate Groq down → verify Haiku bypass works
- [ ] Measure total tokens per classification call (target <900)
- [ ] Measure latency (target <2 seconds including network)

---

## ACCURACY IMPROVEMENT (Post-Launch)

If classification accuracy is below target, add few-shot examples to system prompt:

```
EXAMPLES:
User: "what's the status of the bet app"
→ {"intent":"status_check","complexity":"low","project":"betapp","department":"ralph","can_cache":true}

User: "the import error in dna-matrix is back"  
→ {"intent":"fix_error","complexity":"high","project":"betapp","department":"tess","can_cache":false}

User: "deploy the latest to VPS"
→ {"intent":"deploy","complexity":"medium","project":"unknown","department":"ira","can_cache":false}

User: "hey"
→ {"intent":"trivial","complexity":"low","project":"unknown","department":"general","can_cache":true}
```

Each example adds ~50 tokens. 4-6 examples = ~250 tokens. Total system prompt with examples: ~600 tokens. Still well within budget.
