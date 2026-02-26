# Document 6 of 8: THE RATE LIMIT TRACKER
## Health Monitor, HTTP Header Parsing, Buffer Switching

**Purpose:** The nervous system of the entire architecture. Reads rate limit headers from every API response, maintains a health dashboard, triggers buffer switches automatically. Zero extra API calls — it's purely reactive.

**Status: IMPLEMENTED** — `src/lobby/rate_limiter.py` (19 tests passing)

---

## THE PRINCIPLE

Every API response includes rate limit information in HTTP headers. We already get this data for free. The tracker simply reads it, stores it, and makes it available to the routing layer.

**No polling. No extra calls. No cost.**

---

## IMPLEMENTATION

### File: `src/lobby/rate_limiter.py`

The full implementation lives in a single module with:

- `_parse_reset_duration(raw)` — Parses reset times from all formats (Groq `"2m59.56s"`, ISO datetime, plain seconds)
- `RateLimitTracker` — Singleton class, in-memory + SQLite persistence
- `get_tracker()` — Module-level singleton accessor

### Integration: `src/lobby/classifier.py`

The classifier calls the tracker on every API response:

```python
# On 200 OK — update health from response headers
self.tracker.update(provider, model, dict(response.headers))

# On 429 — mark RED immediately, record retry-after
self.tracker.update_on_429(provider, model, retry_after)
```

Before calling any provider, the classifier checks health:

```python
if self.tracker.is_available("openai", self.openai_model):
    result = self._classify_by_openai(message)
else:
    # OpenAI rate limited, skip to Kimi 2.5
    result = self._classify_by_kimi(message)
```

---

## PROVIDER HEADER FORMATS

### Groq / OpenAI / Moonshot Headers
```
x-ratelimit-limit-requests: 14400
x-ratelimit-remaining-requests: 14370
x-ratelimit-reset-requests: 2m59.56s
x-ratelimit-limit-tokens: 6000
x-ratelimit-remaining-tokens: 5997
x-ratelimit-reset-tokens: 7.66s
retry-after: 2                              # Only on 429
```

### Anthropic (Haiku/Claude) Headers
```
anthropic-ratelimit-requests-limit: <rpm>
anthropic-ratelimit-requests-remaining: <remaining>
anthropic-ratelimit-requests-reset: <iso_datetime>
anthropic-ratelimit-tokens-limit: <tpm>
anthropic-ratelimit-tokens-remaining: <remaining>
anthropic-ratelimit-tokens-reset: <iso_datetime>
retry-after: <seconds>                      # Only on 429
```

All four provider formats are handled by `tracker.parse_headers(headers, provider)`.

---

## HEALTH STATES

```
GREEN  (>20% remaining)
├── Use normally
├── No special behavior
└── Happy path

YELLOW (5-20% remaining)
├── Still usable
├── Low/normal priority → divert to buffer
├── High/critical priority → stays on primary
└── Extends primary's capacity for important work

RED    (<5% remaining OR 429 received)
├── Do NOT send new requests
├── ALL traffic diverts to buffer immediately
├── Auto-recovers to YELLOW after reset time passes
└── No manual intervention needed
```

### Health Calculation

```python
request_pct = remaining_requests / limit_requests * 100
token_pct = remaining_tokens / limit_tokens * 100
lowest = min(request_pct, token_pct)  # bottleneck decides

if lowest > 20:  health = "green"
elif lowest > 5: health = "yellow"
else:            health = "red"
```

Health is determined by the LOWER of requests and tokens. If you have 90% tokens remaining but 3% requests remaining, you're RED.

---

## 429 CIRCUIT BREAKER

When a 429 hits, the tracker:

1. **Marks the provider RED immediately** — `update_on_429(provider, model, retry_after)`
2. **Records the reset time** — `reset_at = now + retry_after`
3. **All subsequent requests skip this provider** — `is_available()` returns `False`
4. **Auto-recovers** — After `reset_at` passes, `get_health()` upgrades RED → YELLOW

The classifier's cascade handles the diversion:

```
OpenAI 429
  → tracker marks OpenAI RED
  → next classify() call checks is_available("openai") → False
  → skips to Kimi 2.5
  → Kimi also 429? → marks Kimi RED → falls to hardcoded fallback
  → After OpenAI reset time passes → auto YELLOW → next call tries OpenAI again
```

No manual intervention. No restart needed. No 8-hour stuck loops.

---

## PRIORITY-BASED DIVERSION (YELLOW STATE)

```python
tracker.should_divert("openai", "gpt-4o-mini", priority="low")     # True in YELLOW
tracker.should_divert("openai", "gpt-4o-mini", priority="high")    # False in YELLOW
tracker.should_divert("openai", "gpt-4o-mini", priority="low")     # True in RED
tracker.should_divert("openai", "gpt-4o-mini", priority="high")    # True in RED
```

In YELLOW: cheap stuff diverts, important stuff stays on primary.
In RED: everything diverts. No exceptions.

---

## PERSISTENCE

Every health update is written to SQLite (`rate_limit_snapshots` table) for historical tracking:

```sql
CREATE TABLE rate_limit_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,        -- green, yellow, red
    tpm_remaining INTEGER,
    tpm_limit INTEGER,
    rpm_remaining INTEGER,
    rpm_limit INTEGER,
    tokens_remaining INTEGER,
    tokens_limit INTEGER,
    time_until_reset INTEGER,
    metadata TEXT
);
```

Database: `~/.openclaw/workspace/cache/responses.db` (shared with cache layer)

Query historical snapshots:

```python
tracker.get_recent_snapshots()                       # last 20 across all providers
tracker.get_recent_snapshots("openai_gpt4o_mini")    # last 20 for OpenAI
```

---

## DIAGNOSTICS

```python
tracker.get_stats()
# Returns:
{
    "providers_tracked": 2,
    "providers_red": 1,
    "providers_yellow": 0,
    "providers_green": 1,
    "all_health": {
        "openai_gpt4o_mini": "red",
        "moonshot_moonshot-v1-auto": "green"
    },
    "openai_gpt4o_mini_resets_in": 45   # seconds until recovery
}
```

```python
tracker.seconds_until_available("openai", "gpt-4o-mini")  # 45
tracker.is_available("openai", "gpt-4o-mini")              # False
tracker.get_health("openai", "gpt-4o-mini")                # "red"
```

---

## METRICS QUERIES

```sql
-- Rate limit events per provider (last 24h)
SELECT provider, status, COUNT(*) as snapshots
FROM rate_limit_snapshots
WHERE timestamp > strftime('%s', 'now') - 86400
GROUP BY provider, status
ORDER BY provider, status;

-- 429 events (when did we get rate limited?)
SELECT provider, timestamp,
       datetime(timestamp, 'unixepoch') as when_hit
FROM rate_limit_snapshots
WHERE rpm_remaining = 0 OR status = 'red'
ORDER BY timestamp DESC
LIMIT 20;

-- Time spent in each state per provider
SELECT
    provider,
    status,
    COUNT(*) * 1.0 / (SELECT COUNT(*) FROM rate_limit_snapshots WHERE provider = r.provider) * 100 as pct_time
FROM rate_limit_snapshots r
WHERE timestamp > strftime('%s', 'now') - 86400
GROUP BY provider, status;
```

---

## TESTING

**19 tests in `tests/unit/test_rate_limiter.py`**, all passing:

- [x] Parse Groq reset duration (`"2m59.56s"` → 179 seconds)
- [x] Parse plain seconds (`"60"` → 60)
- [x] Handle empty/None input (safe default 60s)
- [x] Default health is GREEN (no data = healthy)
- [x] Green health from healthy headers (>20% remaining)
- [x] Yellow health from low headers (5-20% remaining)
- [x] Red health from very low headers (<5% remaining)
- [x] 429 marks provider RED immediately
- [x] Auto-recovery: RED → YELLOW after reset time passes
- [x] `is_available()`: green/yellow = True, red = False
- [x] `should_divert()`: never on green, low-priority on yellow, always on red
- [x] `seconds_until_available()`: reports correct countdown
- [x] `get_all_health()`: returns snapshot of all providers
- [x] Anthropic header format parsed correctly
- [x] SQLite persistence: snapshots written and queryable
- [x] `get_stats()`: reflects tracked state

---

## WHAT'S NEXT

The tracker is fully functional for the lobby classifier. To extend it to ALL API calls in the system (department heads, boss, emergency):

1. Wire `tracker.update()` into every API response handler
2. Wire `tracker.is_available()` into every routing decision
3. Add the full cascade from ADR-003 (department buffers, emergency tier)

Currently covers: OpenAI, Moonshot/Kimi, with support for Groq and Anthropic header parsing ready.
