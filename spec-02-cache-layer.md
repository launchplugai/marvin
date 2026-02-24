# Document 2 of 8: THE FILING CABINET
## Cache Layer — SQLite Schema, TTL, Invalidation, Metrics

**Purpose:** Eliminate 40-60% of API calls. The cheapest API call is the one you never make.

---

## CACHE ARCHITECTURE

```
Request arrives (post-lobby classification)
    ↓
┌─────────────────────────────────────────┐
│  TIER 1: Exact Match                    │
│  Key: sha256(intent+project+state_hash) │
│  Speed: <5ms (SQLite index lookup)      │
│  Hit rate: 20-30%                       │
│  Phase: 1 (build first)                 │
└─────────────────────────────────────────┘
    ↓ miss
┌─────────────────────────────────────────┐
│  TIER 2: Pattern Match                  │
│  Embedding: all-MiniLM-L6-v2 (80MB)    │
│  Cosine similarity > 0.85 = hit        │
│  Speed: <50ms (local inference)         │
│  Hit rate: 15-25%                       │
│  Phase: 2 (build after Tier 1 proven)   │
└─────────────────────────────────────────┘
    ↓ miss
┌─────────────────────────────────────────┐
│  TIER 3: Context Primer                 │
│  Not a full answer — attaches context   │
│  Reduces downstream tokens 30-50%       │
│  Usefulness: ~80% of misses            │
│  Phase: 2                               │
└─────────────────────────────────────────┘
    ↓ full miss
Continue to Receptionist (Haiku)
```

---

## SQLITE SCHEMA

```sql
-- Main cache table
CREATE TABLE cache_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT UNIQUE NOT NULL,
    intent TEXT NOT NULL,
    project TEXT,
    state_hash TEXT,
    tier TEXT NOT NULL DEFAULT 'exact',
    request_text TEXT NOT NULL,
    response TEXT NOT NULL,
    embedding BLOB,
    tokens_saved INTEGER DEFAULT 0,
    hit_count INTEGER DEFAULT 0,
    ttl_seconds INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    invalidated_by TEXT,
    resolved_by TEXT,
    metadata TEXT
);

CREATE INDEX idx_cache_key ON cache_entries(cache_key);
CREATE INDEX idx_expires ON cache_entries(expires_at);
CREATE INDEX idx_project ON cache_entries(project);
CREATE INDEX idx_intent ON cache_entries(intent);
CREATE INDEX idx_tier ON cache_entries(tier);

-- Metrics tracking
CREATE TABLE cache_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    tier TEXT NOT NULL,
    event TEXT NOT NULL,
    tokens_saved INTEGER DEFAULT 0,
    project TEXT,
    intent TEXT,
    envelope_id TEXT
);

CREATE INDEX idx_metrics_time ON cache_metrics(timestamp);
CREATE INDEX idx_metrics_event ON cache_metrics(event);

-- Rate limit snapshots (updated on every API response)
CREATE TABLE rate_limit_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    provider TEXT NOT NULL,
    remaining_requests INTEGER,
    remaining_tokens INTEGER,
    resets_at TEXT,
    health TEXT
);

CREATE INDEX idx_rate_provider ON rate_limit_snapshots(provider, timestamp);
```

---

## CACHE KEY GENERATION

```python
import hashlib, json

def generate_cache_key(intent, project, state):
    """
    intent: from lobby classification ("fix_error", "status_check", etc.)
    project: detected project ("betapp", "brand-engine", etc.)
    state: dict of relevant project state signals
    """
    state_sig = hashlib.sha256(json.dumps({
        "branch": state.get("branch"),
        "last_commit": state.get("last_commit_short"),
        "deploy_status": state.get("deploy_status")
    }, sort_keys=True).encode()).hexdigest()[:16]

    raw = f"{intent}:{project}:{state_sig}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_project_state(project):
    """Gather current project state for cache key + context primer"""
    return {
        "branch": git_current_branch(project),
        "last_commit_short": git_last_commit(project)[:8],
        "last_commit_msg": git_last_commit_message(project),
        "deploy_status": check_deploy_status(project),
        "open_blockers": get_blockers(project),
        "recent_files": git_recent_changes(project, hours=4),
        "test_status": get_last_test_result(project)
    }
```

---

## TTL STRATEGY

| Intent | TTL | Rationale |
|--------|-----|-----------|
| status_check | 60 seconds | State changes frequently during active dev |
| trivial | 24 hours | "What time is it" doesn't change |
| how_to | 1 hour | Stable unless code changes |
| reference | 7 days | Architecture docs, API specs |
| fix_error | 30 minutes | Error context changes as fixes are attempted |
| code_task | 15 minutes | Code evolves fast |
| deploy | 1 hour | Deploy state relatively stable |
| test | 15 minutes | Test results change with code |
| planning | 4 hours | Sprint plans don't change minute-to-minute |
| conversation | NEVER CACHE | Dynamic by nature |

```python
TTL_MAP = {
    "status_check": 60,
    "trivial": 86400,
    "how_to": 3600,
    "reference": 604800,
    "fix_error": 1800,
    "code_task": 900,
    "deploy": 3600,
    "test": 900,
    "planning": 14400,
    "conversation": 0  # never cache
}
```

---

## INVALIDATION LOGIC

### 1. Git Post-Commit Hook
```bash
#!/bin/bash
# .git/hooks/post-commit
# Clears cache entries for changed projects

CHANGED=$(git diff HEAD~1 --name-only)
python3 agents/cache_invalidate.py --changed-files "$CHANGED"
```

```python
# agents/cache_invalidate.py
def invalidate_on_commit(changed_files):
    projects = detect_affected_projects(changed_files)
    for project in projects:
        # Clear status and test caches (most volatile)
        db.execute("""
            DELETE FROM cache_entries
            WHERE project = ? AND intent IN ('status_check', 'test', 'code_task', 'fix_error')
        """, (project,))
        
        # Log the invalidation
        db.execute("""
            INSERT INTO cache_metrics (timestamp, tier, event, project, intent)
            VALUES (?, 'all', 'invalidate_git', ?, 'multiple')
        """, (now(), project))
```

### 2. TTL Expiry (Lazy)
```python
def get_cached(cache_key):
    row = db.execute("""
        SELECT * FROM cache_entries
        WHERE cache_key = ? AND expires_at > ?
    """, (cache_key, now())).fetchone()
    
    if row:
        # Update hit count
        db.execute("UPDATE cache_entries SET hit_count = hit_count + 1 WHERE id = ?", (row['id'],))
        log_metric('hit', row['tier'], row['tokens_saved'], row['project'], row['intent'])
        return row['response']
    
    log_metric('miss', 'none', 0, None, None)
    return None
```

### 3. Manual Clear
```python
def handle_user_command(message):
    if message.strip().lower() in ["clear cache", "forget that", "fresh start"]:
        db.execute("DELETE FROM cache_entries")
        return "Cache cleared."
    
    if message.strip().lower().startswith("forget "):
        project = message.split("forget ")[1].strip()
        db.execute("DELETE FROM cache_entries WHERE project = ?", (project,))
        return f"Cache cleared for {project}."
```

### 4. Branch Switch
```python
def on_branch_change(project, old_branch, new_branch):
    """Clear project cache when branch changes — state is different"""
    db.execute("""
        DELETE FROM cache_entries WHERE project = ?
    """, (project,))
```

---

## CACHE WRITE (on successful API response)

```python
def cache_response(envelope, response, model_used):
    """Write successful response to cache for future hits"""
    intent = envelope['classification']['intent']
    
    # Don't cache conversations or uncacheable intents
    if intent == 'conversation' or not envelope['classification'].get('can_cache', True):
        return
    
    project = envelope['classification'].get('project', 'unknown')
    state = envelope.get('context_primer', {}).get('project_state', {})
    cache_key = generate_cache_key(intent, project, state)
    ttl = TTL_MAP.get(intent, 900)  # default 15 min
    
    db.execute("""
        INSERT OR REPLACE INTO cache_entries
        (cache_key, intent, project, state_hash, tier, request_text, response,
         ttl_seconds, created_at, expires_at, resolved_by)
        VALUES (?, ?, ?, ?, 'exact', ?, ?, ?, ?, ?, ?)
    """, (
        cache_key, intent, project,
        state.get('last_commit_short', ''),
        envelope['original_message']['text'],
        response,
        ttl, now(), now() + ttl,
        model_used
    ))
```

---

## METRICS QUERIES

```sql
-- Cache hit rate (last 24 hours)
SELECT 
    tier,
    event,
    COUNT(*) as count,
    SUM(tokens_saved) as total_tokens_saved
FROM cache_metrics
WHERE timestamp > strftime('%s', 'now') - 86400
GROUP BY tier, event;

-- Most cached intents
SELECT intent, COUNT(*) as hits
FROM cache_metrics
WHERE event = 'hit'
GROUP BY intent
ORDER BY hits DESC;

-- Tokens saved per day
SELECT 
    date(timestamp, 'unixepoch') as day,
    SUM(tokens_saved) as tokens_saved
FROM cache_metrics
WHERE event = 'hit'
GROUP BY day
ORDER BY day DESC;

-- Invalidation frequency
SELECT 
    intent,
    COUNT(*) as invalidations
FROM cache_metrics
WHERE event LIKE 'invalidate%'
GROUP BY intent
ORDER BY invalidations DESC;
```

---

## PHASE 1 BUILD CHECKLIST

- [ ] Create SQLite database with schema above
- [ ] Implement `generate_cache_key()` 
- [ ] Implement `get_cached()` with TTL check
- [ ] Implement `cache_response()` write-on-success
- [ ] Wire into dispatcher: check cache AFTER lobby, BEFORE receptionist
- [ ] Add git post-commit hook
- [ ] Implement manual "clear cache" command
- [ ] Add metrics logging on every hit/miss/write/invalidate
- [ ] Test with 30 real messages: verify hit/miss behavior
- [ ] Monitor: target >20% hit rate within first day
