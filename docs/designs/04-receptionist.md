# Document 4 of 8: THE RECEPTIONIST
## Haiku — Smart Routing + Dispatch Logic

**Purpose:** The receptionist reads the lobby's classification, checks the rate limit board, and decides: which department, which model, what priority. Haiku is already running, already paid for, already reliable. It stays.

---

## WHY HAIKU, NOT ANOTHER GROQ MODEL

| Factor | Haiku | Groq Alternative |
|--------|-------|-----------------|
| Already in stack | ✅ Yes | ❌ New integration |
| Paid/reliable | ✅ Consistent | ⚠️ Free tier limits |
| Routing accuracy | ✅ Strong | ⚠️ 8B too dumb, K2 overkill |
| Cost | Low (already paying) | Free but rate-limited |
| Speed | Fast | Fast |

Haiku is the receptionist because it's **already employed.** Don't fire someone who works to hire someone free who might not show up.

**Buffer:** Groq Kimi K2 0905 — only activates when Haiku is throttled.

---

## RECEPTIONIST'S VIEW

Haiku receives the envelope from the lobby + cache layer. It sees:

```json
{
  "message": "the import error in dna-matrix is back again",
  "classification": {
    "intent": "fix_error",
    "complexity": "high",
    "project": "betapp",
    "department": "tess"
  },
  "cache_result": {
    "hit": false,
    "partial_context": "Last import fix: PYTHONPATH issue. 127 test failures."
  },
  "rate_limit_state": {
    "kimi_2_5": "green",
    "groq_gpt_oss_120b": "green",
    "groq_kimi_k2": "green",
    "groq_qwen3_32b": "green"
  }
}
```

~200 tokens of context. Enough to make a smart routing decision.

---

## SYSTEM PROMPT (HAIKU RECEPTIONIST)

```
You are a ROUTING DISPATCHER. You receive a classified request envelope and decide WHERE it goes next.

You output ONLY valid JSON:

{
  "destination": "<model_id>",
  "department": "<ralph|ira|tess|general>",
  "priority": "<low|normal|high|critical>",
  "fallback": "<model_id>",
  "reason": "<one sentence: why this destination>",
  "context_injection": "<optional: key context to prepend to department prompt>"
}

ROUTING RULES:

1. CHECK RATE LIMITS FIRST:
   - If primary (kimi_2_5) is "green" → route to kimi_2_5
   - If primary is "yellow" → route to kimi_2_5 but set fallback to department buffer
   - If primary is "red" → route DIRECTLY to department's Groq buffer

2. DEPARTMENT BUFFER ASSIGNMENTS:
   - ralph → groq_gpt_oss_120b (reasoning for planning)
   - ira → groq_kimi_k2_0905 (versatile for infra)
   - tess → groq_qwen3_32b (structured output for tests)
   - general → groq_llama_70b (general purpose)

3. PRIORITY:
   - critical: system down, data loss, security issue
   - high: blocking work, errors in production, failing deploys
   - normal: standard tasks, feature work, questions
   - low: nice-to-have, cleanup, documentation

4. CONTEXT INJECTION:
   - If cache provided partial_context, include relevant parts
   - Keep under 200 tokens — summarize if needed
   - This gets prepended to the department head's prompt

5. ESCALATION:
   - If complexity=high AND intent=fix_error AND cache shows previous failed attempts
     → set priority=critical, add note in reason
   - If complexity=high AND rate limits are yellow/red on multiple providers
     → consider routing to Claude CLI directly (destination: "claude_opus")

OUTPUT ONLY THE JSON. NO EXPLANATION.
```

---

## DISPATCH TABLE

The receptionist's routing decisions mapped out:

### By Intent + Complexity → Destination

| Intent | Low | Medium | High |
|--------|-----|--------|------|
| trivial | Direct reply (no API) | Direct reply | — |
| status_check | Cache → Haiku self | Kimi 2.5 | Kimi 2.5 |
| how_to | Cache → Haiku self | Kimi 2.5 | Kimi 2.5 |
| fix_error | Haiku self | Kimi 2.5 (Tess) | Claude CLI |
| code_task | Kimi 2.5 | Kimi 2.5 | Claude CLI |
| deploy | Kimi 2.5 (Ira) | Kimi 2.5 (Ira) | Kimi 2.5 (Ira) |
| test | Kimi 2.5 (Tess) | Kimi 2.5 (Tess) | Claude CLI |
| planning | Kimi 2.5 (Ralph) | Kimi 2.5 (Ralph) | Kimi 2.5 (Boss) |
| conversation | Kimi 2.5 | Kimi 2.5 | Kimi 2.5 |

### By Rate Limit State → Model Selection

| Kimi 2.5 Health | Action |
|----------------|--------|
| Green (>20%) | Use Kimi 2.5 as normal |
| Yellow (5-20%) | Use Kimi 2.5, set Groq buffer as fallback |
| Red (<5%) | Route directly to department's Groq buffer |
| All buffers red | Escalate to OpenAI API |
| Everything red | Claude CLI emergency |

---

## DISPATCHER CODE

```python
import json

# Department → buffer model mapping
DEPARTMENT_BUFFERS = {
    "ralph": "groq_gpt_oss_120b",
    "ira": "groq_kimi_k2_0905",
    "tess": "groq_qwen3_32b",
    "general": "groq_llama_70b"
}

# Intent + complexity → can receptionist handle it directly?
SELF_HANDLEABLE = {
    ("trivial", "low"), ("trivial", "medium"),
    ("status_check", "low"),
    ("how_to", "low"),
    ("fix_error", "low"),
}

# Intent + complexity → needs heavy model (Claude CLI)
NEEDS_HEAVY = {
    ("fix_error", "high"),
    ("code_task", "high"),
    ("test", "high"),
}


def receptionist_route(envelope: dict) -> dict:
    """
    Core routing logic. Reads envelope, decides destination.
    Returns routing block to add to envelope.
    """
    classification = envelope["classification"]
    intent = classification["intent"]
    complexity = classification["complexity"]
    department = classification["department"]
    rate_limits = envelope["rate_limit_state"]
    cache_context = ""
    
    if envelope.get("cache_result") and envelope["cache_result"].get("partial_context"):
        cache_context = envelope["cache_result"]["partial_context"]
    
    # 1. Can receptionist handle it directly?
    if (intent, complexity) in SELF_HANDLEABLE:
        return {
            "routed_by": "haiku",
            "destination": "haiku_self",
            "department": department,
            "priority": "low",
            "fallback": None,
            "reason": f"Simple {intent}, handled at receptionist level",
            "context_injection": cache_context[:200] if cache_context else None,
            "timestamp": iso_now()
        }
    
    # 2. Needs heavy model?
    if (intent, complexity) in NEEDS_HEAVY:
        return {
            "routed_by": "haiku",
            "destination": "claude_cli",
            "department": department,
            "priority": "high",
            "fallback": select_primary_or_buffer(department, rate_limits),
            "reason": f"High complexity {intent} — needs Claude CLI",
            "context_injection": cache_context[:400] if cache_context else None,
            "timestamp": iso_now()
        }
    
    # 3. Standard routing — check rate limits
    destination = select_primary_or_buffer(department, rate_limits)
    priority = determine_priority(intent, complexity, envelope)
    
    return {
        "routed_by": "haiku",
        "destination": destination,
        "department": department,
        "priority": priority,
        "fallback": DEPARTMENT_BUFFERS.get(department, "groq_llama_70b"),
        "reason": f"{intent}/{complexity} → {department} via {destination}",
        "context_injection": cache_context[:300] if cache_context else None,
        "timestamp": iso_now()
    }


def select_primary_or_buffer(department: str, rate_limits: dict) -> str:
    """Pick Kimi 2.5 if healthy, else department's Groq buffer"""
    kimi_health = rate_limits.get("kimi_2_5", "green")
    
    if kimi_health == "green":
        return "kimi_2_5"
    
    if kimi_health == "yellow":
        return "kimi_2_5"  # still usable, fallback is set separately
    
    # Kimi is red — go to buffer
    buffer = DEPARTMENT_BUFFERS.get(department, "groq_llama_70b")
    buffer_health = rate_limits.get(buffer, "green")
    
    if buffer_health != "red":
        return buffer
    
    # Buffer also red — cascade
    for alt_buffer in DEPARTMENT_BUFFERS.values():
        if rate_limits.get(alt_buffer, "green") != "red":
            return alt_buffer
    
    # Everything red — emergency
    if rate_limits.get("openai", "green") != "red":
        return "openai_gpt4o"
    
    return "claude_cli"  # last resort


def determine_priority(intent: str, complexity: str, envelope: dict) -> str:
    """Assign priority based on intent, complexity, and context"""
    # Critical: production issues
    if intent == "deploy" and complexity == "high":
        return "critical"
    if intent == "fix_error" and "production" in envelope["original_message"]["text"].lower():
        return "critical"
    
    # High: blocking work
    if complexity == "high":
        return "high"
    if intent in ("fix_error", "test") and complexity == "medium":
        return "high"
    
    # Low: trivial or informational
    if intent in ("trivial", "conversation"):
        return "low"
    if complexity == "low":
        return "low"
    
    return "normal"
```

---

## HAIKU SELF-HANDLE (Receptionist Answers Directly)

For simple requests, Haiku doesn't route — it answers. This saves a downstream API call entirely.

```python
SELF_HANDLE_RESPONSES = {
    "trivial": {
        "hey": "What's up? What are we working on?",
        "thanks": "👍",
        "ok": "Got it. What's next?",
    }
}

def haiku_self_handle(envelope: dict) -> str | None:
    """
    If the request is simple enough, Haiku answers directly.
    Returns response string or None (if can't self-handle).
    """
    intent = envelope["classification"]["intent"]
    message = envelope["original_message"]["text"].strip().lower()
    
    # Check static responses first
    if intent == "trivial" and message in SELF_HANDLE_RESPONSES.get("trivial", {}):
        return SELF_HANDLE_RESPONSES["trivial"][message]
    
    # For low-complexity status checks with cache context available
    if intent == "status_check" and envelope["classification"]["complexity"] == "low":
        if envelope.get("cache_result", {}).get("partial_context"):
            return envelope["cache_result"]["partial_context"]
    
    return None  # Can't self-handle, continue routing
```

---

## RECEPTIONIST → ENVELOPE UPDATE

```python
def receptionist_process(envelope: dict) -> dict:
    """
    Full receptionist flow:
    1. Try self-handle
    2. If can't, route via dispatch logic
    3. Update envelope with routing block
    4. Pass to next layer
    """
    # Try self-handle
    direct_response = haiku_self_handle(envelope)
    if direct_response:
        envelope["routing"] = {
            "routed_by": "haiku",
            "destination": "haiku_self",
            "department": envelope["classification"]["department"],
            "priority": "low",
            "fallback": None,
            "reason": "Self-handled at receptionist level",
            "context_injection": None,
            "timestamp": iso_now()
        }
        envelope["execution_chain"].append({
            "model": "haiku",
            "action": "self_handle",
            "response": direct_response,
            "tokens_used": 0,
            "timestamp": iso_now()
        })
        # Cache the self-handled response
        cache_response(envelope, direct_response, "haiku_self")
        return envelope
    
    # Route to department
    routing = receptionist_route(envelope)
    envelope["routing"] = routing
    envelope["updated_at"] = iso_now()
    
    # Log
    log_event("receptionist_route", {
        "destination": routing["destination"],
        "department": routing["department"],
        "priority": routing["priority"],
        "reason": routing["reason"]
    })
    
    return envelope
```

---

## BUFFER ACTIVATION (Haiku → Groq K2 0905)

When Haiku itself is throttled:

```python
def call_receptionist(envelope: dict) -> dict:
    """Call Haiku for routing. Fall back to Groq K2 if Haiku throttled."""
    try:
        return call_haiku(envelope)
    except RateLimitError:
        log_event("haiku_throttled", "falling back to groq_kimi_k2_0905")
        update_rate_limit("haiku", "red")
        return call_groq_kimi_k2(envelope)  # same prompt, different model
    except TimeoutError:
        log_event("haiku_timeout", "falling back to groq_kimi_k2_0905")
        return call_groq_kimi_k2(envelope)
```

---

## TESTING CHECKLIST

- [ ] 30 real messages: verify routing destination matches expected department
- [ ] Verify self-handle triggers on trivial messages (no downstream call)
- [ ] Verify status_check with cache context returns cached answer directly
- [ ] Simulate Kimi green → verify routes to kimi_2_5
- [ ] Simulate Kimi yellow → verify routes to kimi_2_5 with buffer fallback set
- [ ] Simulate Kimi red → verify routes to department Groq buffer
- [ ] Simulate all red → verify routes to Claude CLI
- [ ] Simulate Haiku throttled → verify Groq K2 0905 activates as receptionist
- [ ] Verify priority assignment: production error = critical, trivial = low
- [ ] Verify context_injection stays under 400 tokens
- [ ] Verify envelope.routing block is properly populated after every route
- [ ] Measure: receptionist adds <100ms to total request latency
