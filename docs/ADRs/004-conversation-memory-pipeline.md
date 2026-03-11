# ADR-004: Conversation Memory Pipeline

**Status:** Accepted
**Date:** 2026-03-04
**Context:** Phase 1.5 — bridging cache layer (Phase 1) and routing (Phase 2)

## Decision

Build a four-stage conversation memory pipeline that captures, compresses, synthesizes, and hydrates conversation context across sessions.

## Architecture

```
capture -> compress (Groq 8B) -> synthesize (two-layer) -> hydrate (inject)
```

### Pipeline Stages

1. **Capture** (`context/capture.py`) — Records raw conversation blocks (user/assistant/system messages) into SQLite with session scoping, deterministic content hashing (SHA256), and token estimation.

2. **Compress** (`context/compressor.py`) — Sends raw blocks to Groq Llama 8B (free tier) for summarization into two levels: high-level (goals, decisions, state changes) and low-level (code changes, commands, technical details). Falls back to extractive keyword-based summarization when Groq is unavailable.

3. **Synthesize** (`context/synthesizer.py`) — Periodically re-synthesizes per-session summaries into cross-session threads. Produces one `high_level` and one `low_level` thread spanning all sessions. Idempotent via deterministic thread IDs and upsert logic.

4. **Hydrate** (`context/hydrator.py`) — Loads synthesized threads and formats them for injection into new sessions. Supports pull mode (returns formatted string) and push mode (generates CONTEXT.md). Token-budget aware with automatic trimming.

5. **Sync** (`context/sync.py`) — Pushes context deltas to VPS via marvin-skills HTTP endpoint. Tracks last sync timestamp for incremental push.

## Schema Additions

Three new tables added to `src/cache/schema.sql`:
- `context_blocks` — raw conversation captures
- `context_synthesis` — compressed summaries (per-session, per-level)
- `context_threads` — re-synthesized cross-session threads

## Key Design Decisions

1. **Shared SQLite database** — Extends the existing cache database rather than creating a separate one. This keeps the deployment simple and lets cache invalidation and context capture share the same connection patterns.

2. **Two-layer context model** — High-level and low-level separation allows callers to choose granularity. Routing decisions need high-level context; code generation needs low-level. This mirrors how humans context-switch between "what are we doing?" and "where exactly were we?"

3. **Groq free tier for compression** — Matches the existing lobby classifier pattern. Zero-cost compression with extractive fallback means the pipeline works even without API keys.

4. **Extractive fallback** — When Groq is unavailable (no key, rate limited, timeout), the compressor falls back to keyword-based line selection. Not as good as LLM summarization, but functional and deterministic.

5. **Idempotent synthesis** — Thread IDs are deterministic hashes of (thread_type + session_ids). Re-running synthesis updates existing threads rather than creating duplicates. synthesis_count tracks how many times a thread has been re-synthesized.

6. **Delta sync** — Only new records since last successful sync are pushed to VPS. Full sync available for recovery. Sync failures do not block local operations.

7. **Token budget trimming** — Hydrator trims output to fit within a configurable token budget (default 4000). Trimming happens at line boundaries to avoid mid-sentence cuts.

## Conventions Followed

- Dataclasses for structured data (ConversationBlock, SynthesisResult)
- Same Groq integration pattern as lobby/classifier.py
- SQLite with check_same_thread=False and row_factory
- Logging via module-level logger
- Config from environment variables (GROQ_API_KEY, MARVIN_SYNC_URL, MARVIN_SYNC_TOKEN)
- All tests use tempfile for database isolation

## Test Coverage

65 new tests across 4 test files covering:
- Capture format validation and SQLite operations (15 tests)
- Compression pipeline with mocked Groq calls (13 tests)
- Synthesis logic and idempotency (12 tests)
- Hydration output format and fallback chain (13 tests)
- Sync delta/full push with mocked HTTP (12 tests)

All 112 tests passing (47 existing + 65 new).
