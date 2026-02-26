# Document 3 of 8: THE LOBBY
## Ollama Buffer + OpenAI Escalation — Stateless Classification Router

**Purpose:** First contact. One job: stamp the ticket. Never holds a conversation, never accumulates context, never tries to help. Classify and hand off.

**Architecture:** Ollama runs locally on the VPS for free. It handles all the cheap classification work — heartbeats, status checks, trivial messages, how-to lookups. OpenAI only gets called when the work actually needs it — code review, debugging, feature implementation. This eliminates constant API spend on work that a local model handles fine.

---

## THE RULE

**Ollama is the buffer. OpenAI is the brain.**

If a local model can answer it, a local model SHOULD answer it. Every OpenAI API call costs money. Every Ollama call is free. The system's job is to protect OpenAI from work that doesn't need it.

---

## ROUTING FLOW

```
Message arrives
    |
    v
[1] KEYWORD MATCH (free, instant, no model call)
    |-- Match found? --> classify, stamp envelope, done
    |-- No match? --> continue
    v
[2] OLLAMA (local, free, ~100-500ms)
    |-- Ollama available?
    |     |-- YES --> classify with llama
    |     |     |-- Simple intent? (status, how_to, trivial, unknown)
    |     |     |     --> Ollama's answer is final. Done.
    |     |     |-- Complex intent? (code_review, debugging, feature_work)
    |     |           --> Escalate to OpenAI for confirmation
    |     |-- NO --> skip to OpenAI
    v
[3] OPENAI (paid, ~500-2000ms)
    |-- API key configured?
    |     |-- YES --> classify, stamp envelope, done
    |     |-- NO --> skip to fallback
    v
[4] HARDCODED FALLBACK (free, instant, low confidence)
    |-- Short message? --> trivial
    |-- Contains error words? --> debugging
    |-- Default --> unknown
```

---

## WHAT GOES WHERE

### Ollama Handles (Free, Local)

| Intent | Examples | Why Local |
|--------|----------|-----------|
| `status_check` | "What's the status?" "Is it running?" | Simple lookup. No reasoning needed. |
| `how_to` | "How do I run tests?" "What's the command?" | Pattern match. Any 3B+ model gets this right. |
| `trivial` | "Thanks!" "Got it" "Cool" | Waste of money to send this to OpenAI. |
| `unknown` | Random gibberish, off-topic | Not worth an API call to classify noise. |

### OpenAI Handles (Paid, Quality Matters)

| Intent | Examples | Why OpenAI |
|--------|----------|------------|
| `code_review` | "Review my PR" "Check this code" | Needs real comprehension. Quality matters. |
| `debugging` | "Fix this error" "Why is it broken?" | Root cause analysis. Can't afford a bad classification. |
| `feature_work` | "Build the dashboard" "Add auth" | Scope matters. Misclassification wastes agent time. |

### Keywords Handle (Free, Instant)

Any message that hits a keyword match skips both models entirely. Zero latency, zero cost.

---

## MODEL CONFIG

```json
{
  "agent_id": "lobby-router",
  "stateless": true,
  "temperature": 0.1,
  "maxTokens": 20,
  "maxHistoryMessages": 0,
  "accumulateContext": false,

  "ollama": {
    "url": "http://127.0.0.1:11434",
    "model": "llama3.2",
    "timeout_ms": 10000,
    "cost": "free",
    "handles": ["status_check", "how_to", "trivial", "unknown"]
  },

  "openai": {
    "model": "gpt-4o-mini",
    "timeout_ms": 15000,
    "cost": "paid",
    "handles": ["code_review", "debugging", "feature_work"]
  },

  "fallback": {
    "method": "hardcoded",
    "cost": "free",
    "confidence": "low"
  }
}
```

### Why These Settings

| Setting | Value | Rationale |
|---------|-------|-----------|
| temperature | 0.1 | Near-deterministic. Same input = same classification. |
| maxTokens | 20 | Response is a single word. 20 is generous. |
| maxHistoryMessages | 0 | **Stateless.** Every call is fresh. |
| accumulateContext | false | **No memory.** Stamp machine, not a conversationalist. |
| ollama timeout | 10s | Local model, generous for cold start. |
| openai timeout | 15s | Network + inference. Standard for API calls. |

---

## SHARED CLASSIFICATION PROMPT

Both Ollama and OpenAI receive the same prompt. One prompt, two models, consistent behavior.

```
You are a message classifier. Classify this message into ONE category ONLY.

Categories and examples:
- status_check: "What's the status?" "Is it running?" "Health check?" "Uptime?" "How is X?"
- how_to: "How do I run tests?" "What's the command?" "Guide to X?" "Documentation?"
- code_review: "Review my code" "Check this PR" "Feedback on this"
- debugging: "Fix this error" "Why is it broken?" "Debug this issue"
- feature_work: "Build X feature" "Add Y" "Implement Z" "Task: do X"
- trivial: "Thanks!" "Got it" "Cool" "Nice job"
- unknown: Doesn't fit above

Message: "{message}"

Respond with ONLY the category name in lowercase (status_check, how_to, etc), no explanation.
```

**Token count:** ~150 tokens system + ~50-200 user message + 1-2 response tokens. **~200-350 tokens per call.**

---

## CLASSIFICATION SCHEMA

```python
from dataclasses import dataclass

@dataclass
class Classification:
    intent: str        # status_check, how_to, code_review, debugging, feature_work, trivial, unknown
    confidence: float  # 0.0-1.0
    method: str        # "keyword", "ollama", "openai", "fallback"
    cacheable: bool
    ttl: int           # seconds, or None
    reason: str        # human-readable explanation
```

**Confidence by method:**

| Method | Confidence | Rationale |
|--------|-----------|-----------|
| keyword | 0.95 | Exact string match. Almost certain. |
| ollama | 0.80 | Good model, but smaller. Conservative score. |
| openai | 0.90 | Best classifier. High but not perfect. |
| fallback | 0.0-0.6 | Heuristics. Low confidence by design. |

---

## LOBBY → ENVELOPE INTEGRATION

```python
def lobby_classify(user_message: str) -> dict:
    """
    Full lobby flow:
    1. Keywords (free)
    2. Ollama (free, local)
    3. OpenAI (paid, only if needed)
    4. Fallback (hardcoded)
    5. Stamp envelope for next layer
    """
    classifier = LobbyClassifier()
    result = classifier.classify(user_message)

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
            "classified_by": f"lobby-{result.method}",
            "intent": result.intent,
            "complexity": infer_complexity(result.intent),
            "project": "unknown",
            "department": infer_department(result.intent),
            "can_cache": result.cacheable,
            "confidence": result.confidence,
            "method": result.method,
            "reason": result.reason,
            "timestamp": iso_now()
        },
        "cache_result": None,
        "routing": None,
        "context_primer": None,
        "execution_chain": [],
        "rate_limit_state": get_current_rate_limits()
    }

    return envelope
```

---

## FAILURE MODES + HANDLING

| Failure | Detection | Response | Cost |
|---------|-----------|----------|------|
| Ollama down | Health check fails | Skip to OpenAI | Now costs money |
| Ollama slow (>10s) | Timeout | Skip to OpenAI | Now costs money |
| Ollama bad output | Invalid intent string | Skip to OpenAI | Now costs money |
| OpenAI rate limited | 429 response | Use fallback | Free, low quality |
| OpenAI down | Connection error | Use fallback | Free, low quality |
| Both down | Both fail | Hardcoded fallback | Free, lowest quality |
| Wrong classification | Downstream mismatch | Department self-corrects | Already routed |

### Key Insight

When Ollama is healthy, OpenAI never gets called for simple stuff. The system runs at zero classification cost for 60-70% of messages (heartbeats, status, trivial, how-to).

When Ollama goes down, OpenAI picks up ALL classification — the system degrades to fully-paid mode but stays functional. No outage, just higher cost.

### Degraded Mode

```python
def route_message(user_message: str) -> dict:
    """Main entry point — always returns an envelope"""
    try:
        envelope = lobby_classify(user_message)
    except Exception as e:
        # Everything failed — minimal envelope
        envelope = create_minimal_envelope(user_message)
        envelope["classification"] = {
            "classified_by": "bypass",
            "intent": "unknown",
            "complexity": "medium",
            "project": "unknown",
            "department": "general",
            "can_cache": False,
            "confidence": 0.0,
            "method": "bypass",
            "reason": f"Lobby failure: {e}",
            "timestamp": iso_now()
        }
        log_event("lobby_bypass", str(e))

    return check_cache(envelope)
```

---

## VPS SETUP

Ollama runs on the same VPS as Marvin. No external calls. No auth needed.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull llama3.2

# Verify it's running
curl http://127.0.0.1:11434/api/version
```

Environment variables (in `.env`):

```bash
# Ollama (local buffer — free)
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2

# OpenAI (escalation — paid)
OPENAI_API_KEY=sk-...
```

---

## COST ANALYSIS

Assume 1,000 messages/day with typical distribution:

| Intent | % of Traffic | Handled By | Cost Per Call |
|--------|-------------|------------|---------------|
| trivial | 25% | keyword/ollama | $0 |
| status_check | 20% | keyword/ollama | $0 |
| how_to | 15% | keyword/ollama | $0 |
| unknown | 5% | ollama/fallback | $0 |
| debugging | 15% | openai | ~$0.0003 |
| feature_work | 10% | openai | ~$0.0003 |
| code_review | 10% | openai | ~$0.0003 |

**Before (all OpenAI):** ~1,000 calls/day x $0.0003 = ~$0.30/day = ~$9/month
**After (Ollama buffer):** ~350 calls/day x $0.0003 = ~$0.10/day = ~$3/month

**65% cost reduction on classification alone.** And that's just the lobby — the real savings are upstream when agents don't hit OpenAI for heartbeat/status responses.

---

## TESTING CHECKLIST

- [ ] Ollama running and reachable at configured URL
- [ ] `ollama pull llama3.2` completed successfully
- [ ] Keyword matching catches common patterns (status, error, thanks)
- [ ] Ollama classifies correctly for simple intents
- [ ] Complex intents escalate to OpenAI
- [ ] Ollama down → graceful fallback to OpenAI
- [ ] OpenAI down → graceful fallback to hardcoded
- [ ] Both down → hardcoded returns valid envelope
- [ ] Classification confidence scores are correct per method
- [ ] Envelope structure valid for downstream consumers
- [ ] No "ok" substring false positives (removed from keywords)
- [ ] Feed 30 real messages → target >80% accuracy

---

## MONITORING

Track these to know if the buffer is working:

```python
# In get_stats()
{
    "openai_model": "gpt-4o-mini",
    "openai_key_configured": true,
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3.2",
    "ollama_available": true,
    "intents_available": 7
}
```

**Alerts:**
- `ollama_available: false` → Ollama crashed or unreachable. All traffic hitting OpenAI. Restart Ollama.
- `openai_key_configured: false` → No escalation path. Complex work will get fallback classification. Bad.
- Both false → System running on keywords + hardcoded only. Classification quality degraded.
