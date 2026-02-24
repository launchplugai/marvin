-- Marvin Cache Layer Schema
-- SQLite database for cache, metrics, rate limits, and envelopes
-- All tables use `created_at` timestamp in seconds since epoch

-- CACHE TABLE: Stores cached responses
CREATE TABLE IF NOT EXISTS cache_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT UNIQUE NOT NULL,
    intent TEXT NOT NULL,
    project TEXT,
    response TEXT NOT NULL,
    state_signature TEXT,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    hit_count INTEGER DEFAULT 0,
    miss_count INTEGER DEFAULT 0,
    tokens_saved INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'exact_match',
    metadata TEXT,
    last_hit_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_cache_key ON cache_entries(cache_key);
CREATE INDEX IF NOT EXISTS idx_cache_intent ON cache_entries(intent);
CREATE INDEX IF NOT EXISTS idx_cache_project ON cache_entries(project);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_entries(expires_at);
CREATE INDEX IF NOT EXISTS idx_cache_tier ON cache_entries(tier);

-- CACHE METRICS: Track cache performance
CREATE TABLE IF NOT EXISTS cache_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    event_type TEXT NOT NULL,  -- hit, miss, write, invalidate, expire
    intent TEXT,
    project TEXT,
    tier TEXT,
    tokens_saved INTEGER DEFAULT 0,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON cache_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_event ON cache_metrics(event_type);
CREATE INDEX IF NOT EXISTS idx_metrics_intent ON cache_metrics(intent);

-- INVALIDATION LOG: Track cache invalidations
CREATE TABLE IF NOT EXISTS invalidation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    reason TEXT NOT NULL,  -- ttl_expiry, git_commit, manual_clear, etc.
    target_type TEXT,      -- project, intent, all
    target_value TEXT,     -- project name or intent
    keys_cleared INTEGER,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_invalidation_timestamp ON invalidation_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_invalidation_reason ON invalidation_log(reason);

-- RATE LIMIT SNAPSHOTS: Track provider health over time
CREATE TABLE IF NOT EXISTS rate_limit_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    provider TEXT NOT NULL,  -- groq, anthropic, openai, moonshot
    model TEXT NOT NULL,
    status TEXT NOT NULL,    -- green, yellow, red, critical
    tpm_remaining INTEGER,
    tpm_limit INTEGER,
    rpm_remaining INTEGER,
    rpm_limit INTEGER,
    tokens_remaining INTEGER,
    tokens_limit INTEGER,
    time_until_reset INTEGER,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_ratelimit_timestamp ON rate_limit_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_ratelimit_provider ON rate_limit_snapshots(provider);
CREATE INDEX IF NOT EXISTS idx_ratelimit_status ON rate_limit_snapshots(status);

-- ENVELOPES: Message tracking through system
CREATE TABLE IF NOT EXISTS envelopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope_id TEXT UNIQUE NOT NULL,
    user_message TEXT NOT NULL,
    classification TEXT,
    routing_decision TEXT,
    department TEXT,
    models_used TEXT,  -- JSON array of models tried in order
    final_response TEXT,
    execution_chain TEXT,  -- JSON array of execution steps
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    total_tokens_used INTEGER,
    total_cost REAL,
    hit_cache INTEGER DEFAULT 0,
    fallback_activated INTEGER DEFAULT 0,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_envelope_id ON envelopes(envelope_id);
CREATE INDEX IF NOT EXISTS idx_envelope_created ON envelopes(created_at);
CREATE INDEX IF NOT EXISTS idx_envelope_department ON envelopes(department);

-- MIGRATION TRACKING (for schema updates)
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name TEXT UNIQUE NOT NULL,
    applied_at INTEGER NOT NULL
);

-- Insert initial migration
INSERT OR IGNORE INTO schema_migrations (migration_name, applied_at)
VALUES ('001_initial_schema', strftime('%s', 'now'));
