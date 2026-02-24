# Document 6 of 8: THE RATE LIMIT TRACKER
## Health Monitor, HTTP Header Parsing, Buffer Switching

**Purpose:** The nervous system of the entire architecture. Reads rate limit headers from every API response, maintains a health dashboard, triggers buffer switches automatically. Zero extra API calls — it's purely reactive.

---

## THE PRINCIPLE

Every API response includes rate limit information in HTTP headers. We already get this data for free. The tracker simply reads it, stores it, and makes it available to the routing layer.

**No polling. No extra calls. No cost.**

---

## PROVIDER HEADER FORMATS

### Groq Headers
```
x-ratelimit-limit-requests: 14400          # RPD ceiling
x-ratelimit-remaining-requests: 14370      # RPD remaining
x-ratelimit-reset-requests: 2m59.56s       # Time until RPD reset
x-ratelimit-limit-tokens: 6000             # TPM ceiling
x-ratelimit-remaining-tokens: 5997         # TPM remaining
x-ratelimit-reset-tokens: 7.66s            # Time until TPM reset
retry-after: 2                              # Only on 429 responses
```

### Kimi / Moonshot Headers
```
x-ratelimit-limit-requests: <rpm_limit>
x-ratelimit-remaining-requests: <remaining>
x-ratelimit-reset-requests: <reset_time>
x-ratelimit-limit-tokens: <tpm_limit>
x-ratelimit-remaining-tokens: <remaining>
x-ratelimit-reset-tokens: <reset_time>
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

### OpenAI Headers
```
x-ratelimit-limit-requests: <rpm>
x-ratelimit-remaining-requests: <remaining>
x-ratelimit-reset-requests: <duration>
x-ratelimit-limit-tokens: <tpm>
x-ratelimit-remaining-tokens: <remaining>
x-ratelimit-reset-tokens: <duration>
```

---

## HEADER PARSER

```python
from datetime import datetime, timedelta
import re

def parse_rate_limit_headers(headers: dict, provider: str) -> dict:
    """
    Normalize rate limit headers from any provider into standard format.
    Called on EVERY API response.
    """
    
    if provider in ("groq", "openai", "moonshot"):
        remaining_requests = int(headers.get("x-ratelimit-remaining-requests", -1))
        limit_requests = int(headers.get("x-ratelimit-limit-requests", -1))
        remaining_tokens = int(headers.get("x-ratelimit-remaining-tokens", -1))
        limit_tokens = int(headers.get("x-ratelimit-limit-tokens", -1))
        reset_requests = parse_reset_time(headers.get("x-ratelimit-reset-requests", ""))
        reset_tokens = parse_reset_time(headers.get("x-ratelimit-reset-tokens", ""))
        
    elif provider == "anthropic":
        remaining_requests = int(headers.get("anthropic-ratelimit-requests-remaining", -1))
        limit_requests = int(headers.get("anthropic-ratelimit-requests-limit", -1))
        remaining_tokens = int(headers.get("anthropic-ratelimit-tokens-remaining", -1))
        limit_tokens = int(headers.get("anthropic-ratelimit-tokens-limit", -1))
        reset_requests = headers.get("anthropic-ratelimit-requests-reset", "")
        reset_tokens = headers.get("anthropic-ratelimit-tokens-reset", "")
    
    else:
        return {"health": "unknown"}
    
    # Calculate health based on BOTH requests and tokens remaining
    request_pct = (remaining_requests / limit_requests * 100) if limit_requests > 0 else 100
    token_pct = (remaining_tokens / limit_tokens * 100) if limit_tokens > 0 else 100
    
    # Health is determined by the LOWER of the two
    lowest_pct = min(request_pct, token_pct)
    
    if lowest_pct > 20:
        health = "green"
    elif lowest_pct > 5:
        health = "yellow"
    else:
        health = "red"
    
    return {
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
        "updated_at": iso_now()
    }


def parse_reset_time(raw: str) -> str:
    """Parse various reset time formats into ISO datetime"""
    if not raw:
        return ""
    
    # Already ISO format
    if "T" in raw:
        return raw
    
    # Groq format: "2m59.56s" or "7.66s"
    total_seconds = 0
    
    m_match = re.search(r'(\d+)m', raw)
    s_match = re.search(r'([\d.]+)s', raw)
    
    if m_match:
        total_seconds += int(m_match.group(1)) * 60
    if s_match:
        total_seconds += float(s_match.group(1))
    
    if total_seconds > 0:
        reset_time = datetime.utcnow() + timedelta(seconds=total_seconds)
        return reset_time.isoformat() + "Z"
    
    return raw  # Return as-is if unparseable
```

---

## STATE STORAGE

### In-Memory (Fast Access for Routing)

```python
class RateLimitTracker:
    """
    Singleton. Updated on every API response.
    Read by routing layer on every request.
    """
    
    def __init__(self):
        self.providers = {}
        self.db = get_sqlite_connection()
    
    def update(self, provider: str, model: str, headers: dict):
        """Called after EVERY API response"""
        parsed = parse_rate_limit_headers(headers, provider)
        
        key = self._provider_key(provider, model)
        self.providers[key] = parsed
        
        # Also persist to SQLite for historical tracking
        self.db.execute("""
            INSERT INTO rate_limit_snapshots
            (timestamp, provider, remaining_requests, remaining_tokens, resets_at, health)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            now(), key,
            parsed["remaining_requests"],
            parsed["remaining_tokens"],
            parsed.get("reset_requests", ""),
            parsed["health"]
        ))
    
    def update_on_429(self, provider: str, model: str, retry_after: int):
        """Called specifically when we get a 429 response"""
        key = self._provider_key(provider, model)
        self.providers[key] = {
            "remaining_requests": 0,
            "remaining_tokens": 0,
            "health": "red",
            "bottleneck": "rate_limited",
            "retry_after": retry_after,
            "reset_at": (datetime.utcnow() + timedelta(seconds=retry_after)).isoformat() + "Z",
            "updated_at": iso_now()
        }
    
    def get_health(self, provider_key: str) -> str:
        """Get current health for a provider. Used by routing layer."""
        info = self.providers.get(provider_key, {})
        
        # Check if a previous "red" has expired (reset time passed)
        if info.get("health") == "red" and info.get("reset_at"):
            if datetime.utcnow().isoformat() > info["reset_at"]:
                # Reset time passed — optimistically set to yellow
                info["health"] = "yellow"
                self.providers[provider_key] = info
        
        return info.get("health", "green")  # default green if no data yet
    
    def get_all_health(self) -> dict:
        """Snapshot of all providers. Attached to every envelope."""
        return {
            key: info.get("health", "green")
            for key, info in self.providers.items()
        }
    
    def get_best_available(self, preferred: str, fallbacks: list) -> str:
        """Find the healthiest provider from preferred + fallback list"""
        # Try preferred first
        if self.get_health(preferred) in ("green", "yellow"):
            return preferred
        
        # Try fallbacks in order
        for fb in fallbacks:
            if self.get_health(fb) in ("green", "yellow"):
                return fb
        
        # Everything stressed — return preferred anyway (may get 429, will retry)
        return preferred
    
    def _provider_key(self, provider: str, model: str) -> str:
        """Normalize provider key"""
        key_map = {
            ("moonshot", "kimi-2.5"): "kimi_2_5",
            ("groq", "moonshotai/kimi-k2-instruct-0905"): "groq_kimi_k2_0905",
            ("groq", "openai/gpt-oss-120b"): "groq_gpt_oss_120b",
            ("groq", "qwen/qwen3-32b"): "groq_qwen3_32b",
            ("groq", "llama-3.1-8b-instant"): "groq_llama_8b",
            ("groq", "llama-3.3-70b-versatile"): "groq_llama_70b",
            ("anthropic", "haiku"): "haiku",
            ("openai", "gpt-4o"): "openai_gpt4o",
            ("anthropic", "opus"): "claude_opus",
        }
        return key_map.get((provider, model), f"{provider}_{model}")


# Singleton instance
tracker = RateLimitTracker()
```

---

## INTEGRATION POINTS

### 1. After Every API Call

```python
def call_model(provider, model, messages, **kwargs):
    """Wrapper around all API calls. Parses rate limits on every response."""
    
    response = make_api_request(provider, model, messages, **kwargs)
    
    # ALWAYS update rate limits from response headers
    if response.status_code == 200:
        tracker.update(provider, model, dict(response.headers))
    elif response.status_code == 429:
        retry_after = int(response.headers.get("retry-after", 60))
        tracker.update_on_429(provider, model, retry_after)
        raise RateLimitError(provider, model, retry_after)
    
    return response
```

### 2. Envelope Rate Limit Snapshot

```python
def attach_rate_limits_to_envelope(envelope: dict) -> dict:
    """Called before routing. Gives receptionist current health view."""
    envelope["rate_limit_state"] = tracker.get_all_health()
    return envelope
```

### 3. Routing Decision

```python
def select_model_for_department(department: str) -> str:
    """Used by receptionist to pick primary or buffer"""
    primary = "kimi_2_5"
    buffer = DEPARTMENT_BUFFERS[department]
    
    return tracker.get_best_available(
        preferred=primary,
        fallbacks=[buffer, "groq_llama_70b", "openai_gpt4o", "claude_opus"]
    )
```

---

## HEALTH THRESHOLDS

```
GREEN  (>20% remaining)
├── Use normally
├── No special behavior
└── This is the happy path

YELLOW (5-20% remaining)
├── Still usable — don't panic
├── Set fallback on every routed request
├── Log warning: "Kimi approaching limit"
├── Start prioritizing: high/critical requests stay on primary
│   low/normal requests divert to buffer preemptively
└── This extends primary's remaining capacity for important work

RED    (<5% remaining OR 429 received)
├── Do NOT send new requests to this provider
├── All traffic diverts to buffer immediately
├── Log alert: "Kimi rate limited — buffer active"
├── Check reset_at — set timer to retry after reset
└── Optimistically upgrade to yellow after reset time passes
```

### Priority-Based Diversion (Yellow State)

When primary is yellow, don't divert everything. Divert strategically:

```python
def should_divert_to_buffer(priority: str, provider_health: str) -> bool:
    """In yellow state, only divert low-priority requests"""
    if provider_health == "green":
        return False  # Never divert on green
    
    if provider_health == "red":
        return True  # Always divert on red
    
    # Yellow: divert low priority, keep high/critical on primary
    if provider_health == "yellow":
        return priority in ("low", "normal")
    
    return False
```

This means: when Kimi is getting warm, trivial questions and routine tasks go to Groq buffer, but critical debugging and high-priority fixes stay on Kimi. The expensive model is reserved for expensive problems.

---

## 429 HANDLING — THE CIRCUIT BREAKER

```python
def handle_rate_limit_error(provider, model, retry_after, envelope):
    """
    Called when a 429 is received.
    Does NOT retry on the same provider.
    Immediately routes to buffer.
    """
    # 1. Mark provider as red
    tracker.update_on_429(provider, model, retry_after)
    
    # 2. Log the event
    log_event("rate_limit_hit", {
        "provider": provider,
        "model": model,
        "retry_after": retry_after,
        "envelope_id": envelope["envelope_id"],
        "intent": envelope["classification"]["intent"]
    })
    
    # 3. Find buffer
    department = envelope["routing"]["department"]
    buffer = DEPARTMENT_BUFFERS.get(department, "groq_llama_70b")
    buffer_health = tracker.get_health(buffer)
    
    if buffer_health != "red":
        # 4a. Route to buffer with same envelope
        envelope["execution_chain"].append({
            "model": f"{provider}/{model}",
            "action": "rate_limited_429",
            "diverted_to": buffer,
            "retry_after": retry_after,
            "timestamp": iso_now()
        })
        return call_model_with_envelope(buffer, envelope)
    
    # 4b. Buffer also red — cascade
    for cascade in ["groq_llama_70b", "openai_gpt4o", "claude_opus"]:
        if tracker.get_health(cascade) != "red":
            envelope["execution_chain"].append({
                "model": f"{provider}/{model}",
                "action": "rate_limited_429_cascade",
                "diverted_to": cascade,
                "timestamp": iso_now()
            })
            return call_model_with_envelope(cascade, envelope)
    
    # 4c. Everything red — queue and wait
    log_event("all_providers_exhausted", envelope["envelope_id"])
    return queue_for_retry(envelope, min_wait=retry_after)
```

---

## METRICS QUERIES

```sql
-- Rate limit events per provider (last 24h)
SELECT provider, health, COUNT(*) as snapshots
FROM rate_limit_snapshots
WHERE timestamp > strftime('%s', 'now') - 86400
GROUP BY provider, health
ORDER BY provider, health;

-- 429 events (when did we get rate limited?)
SELECT provider, timestamp, 
       datetime(timestamp, 'unixepoch') as when_hit
FROM rate_limit_snapshots
WHERE remaining_requests = 0 OR health = 'red'
ORDER BY timestamp DESC
LIMIT 20;

-- Buffer activation frequency
SELECT provider, COUNT(*) as times_used_as_buffer
FROM rate_limit_snapshots
WHERE health != 'green'
GROUP BY provider
ORDER BY times_used_as_buffer DESC;

-- Time spent in each state per provider
SELECT 
    provider,
    health,
    COUNT(*) * 1.0 / (SELECT COUNT(*) FROM rate_limit_snapshots WHERE provider = r.provider) * 100 as pct_time
FROM rate_limit_snapshots r
WHERE timestamp > strftime('%s', 'now') - 86400
GROUP BY provider, health;
```

---

## TESTING CHECKLIST

- [ ] Parse Groq rate limit headers correctly (format: "2m59.56s")
- [ ] Parse Anthropic rate limit headers correctly (format: ISO datetime)
- [ ] Parse OpenAI rate limit headers correctly
- [ ] Health calculation: 25% remaining = green ✓
- [ ] Health calculation: 15% remaining = yellow ✓
- [ ] Health calculation: 3% remaining = red ✓
- [ ] Health uses LOWER of request% and token% (not just one)
- [ ] 429 response → immediate red status
- [ ] Red status + reset time passed → auto-upgrade to yellow
- [ ] Yellow state: low/normal priority diverts, high/critical stays on primary
- [ ] Red state: all traffic diverts to buffer
- [ ] Buffer also red: cascade to next available provider
- [ ] All providers red: queue for retry with min wait
- [ ] Every API call updates tracker (verify with logging)
- [ ] Envelope rate_limit_state reflects current snapshot
- [ ] SQLite snapshots recording for historical analysis
- [ ] Simulate: Kimi yellow → verify only low-priority diverts
- [ ] Simulate: Kimi red → verify ALL traffic diverts
- [ ] Simulate: Kimi red + Groq red → verify cascade to OpenAI
