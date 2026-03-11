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

-- ============================================================
-- CONVERSATION MEMORY PIPELINE (Phase 1.5)
-- ============================================================

-- CONTEXT BLOCKS: Raw conversation captures
CREATE TABLE IF NOT EXISTS context_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    block_index INTEGER NOT NULL,       -- ordering within session
    timestamp INTEGER NOT NULL,
    role TEXT NOT NULL,                  -- user, assistant, system
    content_hash TEXT NOT NULL,          -- SHA256 of raw_content
    raw_content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    tags TEXT,                           -- JSON array of tags
    metadata TEXT,                       -- JSON object for extensibility
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ctx_blocks_session ON context_blocks(session_id);
CREATE INDEX IF NOT EXISTS idx_ctx_blocks_timestamp ON context_blocks(timestamp);
CREATE INDEX IF NOT EXISTS idx_ctx_blocks_hash ON context_blocks(content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ctx_blocks_session_index ON context_blocks(session_id, block_index);

-- CONTEXT SYNTHESIS: Compressed/summarized conversation blocks
CREATE TABLE IF NOT EXISTS context_synthesis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    block_range_start INTEGER NOT NULL,  -- first block_index covered
    block_range_end INTEGER NOT NULL,    -- last block_index covered
    context_level TEXT NOT NULL,          -- 'high' or 'low'
    summary TEXT NOT NULL,               -- compressed text from Groq
    model_used TEXT DEFAULT 'llama-3.1-8b-instant',
    tokens_input INTEGER DEFAULT 0,      -- tokens sent to compressor
    tokens_output INTEGER DEFAULT 0,     -- tokens received from compressor
    tags TEXT,                            -- JSON array
    metadata TEXT,                        -- JSON object
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ctx_synth_session ON context_synthesis(session_id);
CREATE INDEX IF NOT EXISTS idx_ctx_synth_level ON context_synthesis(context_level);

-- CONTEXT THREADS: Re-synthesized high-level and low-level threads
CREATE TABLE IF NOT EXISTS context_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT UNIQUE NOT NULL,       -- deterministic ID for upsert
    thread_type TEXT NOT NULL,            -- 'high_level' or 'low_level'
    session_ids TEXT NOT NULL,            -- JSON array of session_ids covered
    content TEXT NOT NULL,                -- the re-synthesized thread text
    synthesis_count INTEGER DEFAULT 1,    -- how many times re-synthesized
    model_used TEXT DEFAULT 'llama-3.1-8b-instant',
    tokens_used INTEGER DEFAULT 0,
    metadata TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ctx_threads_type ON context_threads(thread_type);
CREATE INDEX IF NOT EXISTS idx_ctx_threads_updated ON context_threads(updated_at);

-- Track context pipeline migrations
INSERT OR IGNORE INTO schema_migrations (migration_name, applied_at)
VALUES ('002_context_memory_pipeline', strftime('%s', 'now'));
