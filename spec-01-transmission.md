# Document 1 of 8: THE TRANSMISSION
## Context Synchronization Across Model Changes

**Purpose:** When a request moves between models (8B → Haiku → Kimi → Groq buffer), context must travel with it. Without a standard envelope, each model gets a cold start. The Transmission is the clipboard that follows the request through every handoff.

---

## THE PROBLEM

Model A classifies a request. Model B routes it. Model C does the work. Model D validates.

Each model has:
- Different context windows (8K usable → 256K)
- Different system prompts
- Different capabilities
- NO shared memory

Without a standard handoff format, every model transition loses context.

---

## THE SOLUTION: REQUEST ENVELOPE

Every request travels inside an envelope. Each layer adds its stamp but never removes previous stamps.

```json
{
  "envelope_id": "env_20260223_143500_a1b2c3",
  "created_at": "2026-02-23T14:35:00Z",
  "updated_at": "2026-02-23T14:35:02Z",

  "original_message": {
    "text": "the import error in dna-matrix is back again",
    "sender": "user",
    "timestamp": "2026-02-23T14:35:00Z",
    "medium": "openclaw-control-ui"
  },

  "classification": {
    "classified_by": "lobby-8b",
    "intent": "fix_error",
    "complexity": "high",
    "project": "betapp",
    "department": "tess",
    "can_cache": false,
    "confidence": 0.87,
    "timestamp": "2026-02-23T14:35:01Z"
  },

  "cache_result": {
    "checked": true,
    "hit": false,
    "tier": null,
    "partial_context": "Last import fix (2026-02-21): PYTHONPATH missing dna-matrix/src. 127 test failures linked to same root cause.",
    "timestamp": "2026-02-23T14:35:01Z"
  },

  "routing": {
    "routed_by": "haiku",
    "destination": "tess",
    "fallback": "groq_qwen3_32b",
    "priority": "high",
    "reason": "recurring error + high complexity + test domain",
    "timestamp": "2026-02-23T14:35:02Z"
  },

  "context_primer": {
    "project_state": {
      "branch": "main",
      "last_commit": "a4f8e2c1",
      "last_commit_msg": "fix: update requirements.txt",
      "deploy_status": "vps_healthy",
      "test_status": "127 failures (dna-matrix imports)",
      "open_blockers": ["PYTHONPATH", "Railway deploy"]
    },
    "recent_decisions": [
      "2026-02-21: Decided to fix PYTHONPATH at project level, not system level",
      "2026-02-23: Architecture session — agentic delegation system design"
    ],
    "related_cache_entries": [
      "Last import fix attempt: added sys.path.insert in conftest.py — partial fix"
    ]
  },

  "execution_chain": [],

  "rate_limit_state": {
    "kimi_2_5": "green",
    "haiku": "green",
    "groq_qwen3_32b": "green"
  }
}
```

---

## ENVELOPE LIFECYCLE

```
USER MESSAGE
    ↓
LOBBY (8B) adds:
    → classification block (intent, complexity, project, department)
    → ~50 tokens added to envelope

CACHE LAYER adds:
    → cache_result block (hit/miss, partial context if available)
    → context_primer block (project state, recent decisions)
    → ~200-500 tokens added to envelope

RECEPTIONIST (Haiku) adds:
    → routing block (destination, fallback, priority, reason)
    → ~30 tokens added to envelope

DEPARTMENT HEAD (Kimi 2.5) receives:
    → Full envelope: original message + all stamps
    → Total overhead: ~300-600 tokens
    → Knows: what user asked, why it's here, what was tried before
    → Does the work, adds to execution_chain

RESPONSE flows back:
    → Result written to cache (with envelope metadata)
    → Rate limit headers parsed and updated
    → Envelope archived for audit/debugging
```

---

## CONTEXT COMPRESSION BY TIER

Each tier gets a DIFFERENT view of the envelope.

### Lobby (8B) — Sees ONLY:
```json
{ "message": "the import error in dna-matrix is back again" }
```
No history. No context. Just the raw message. Classify and stamp.

### Receptionist (Haiku) — Sees:
```json
{
  "message": "the import error in dna-matrix is back again",
  "classification": { "intent": "fix_error", "complexity": "high", "project": "betapp", "department": "tess" },
  "cache_partial": "Last import fix: PYTHONPATH issue. 127 test failures."
}
```
Enough to route smartly. ~200 tokens.

### Department Head (Kimi 2.5) — Sees:
```json
{
  "message": "the import error in dna-matrix is back again",
  "classification": { "...full..." },
  "routing": { "reason": "recurring error + high complexity + test domain" },
  "context_primer": {
    "branch": "main",
    "last_commit": "a4f8e2c1",
    "test_status": "127 failures",
    "open_blockers": ["PYTHONPATH"],
    "recent_decisions": ["fix PYTHONPATH at project level"],
    "related_fixes": ["sys.path.insert in conftest.py — partial fix"]
  }
}
```
Full picture. ~400-600 tokens.

### Boss — Full envelope + execution_chain (what was tried and failed)
### Emergency (Opus) — Full envelope + all attempts + escalation reason

---

## BUFFER MODEL HANDOFF

When Kimi 2.5 is rate-limited and falls to Groq buffer:

```
KIMI 2.5 THROTTLED → rate_limit_state: "red"
    ↓
Dispatcher reads envelope.routing.fallback = "groq_qwen3_32b"
    ↓
SAME envelope sent to Qwen3 32B on Groq
    ↓
Qwen3 receives identical context — no cold start
    ↓
Response quality may differ (capability gap)
    but context is preserved (no information loss)
```

The envelope IS the transmission. Doesn't matter which engine — same torque to the wheels.

---

## ENVELOPE STORAGE

```sql
CREATE TABLE envelopes (
    envelope_id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    original_message TEXT NOT NULL,
    classification TEXT,          -- JSON
    cache_result TEXT,            -- JSON
    routing TEXT,                 -- JSON
    context_primer TEXT,          -- JSON
    execution_chain TEXT,         -- JSON array
    final_response TEXT,
    total_tokens_used INTEGER,
    models_touched TEXT,          -- JSON array
    resolved_by TEXT,             -- which model produced answer
    escalation_count INTEGER DEFAULT 0
);

CREATE INDEX idx_envelope_created ON envelopes(created_at);
```

Envelopes are archived, not deleted. They become audit trail and training data for improving classification over time.

---

## SYNC RULES

1. **Append-only.** Each tier adds its block. No tier modifies previous stamps.
2. **Tiered visibility.** Lobby sees raw message. Boss sees everything.
3. **Buffer = same envelope.** No context loss on model switch.
4. **Envelope is the state.** Models are stateless. The envelope carries everything.
5. **Cache writes include envelope metadata.** Future hits carry forward original context.
6. **Execution chain logs every model touch.** Full audit trail for debugging.
