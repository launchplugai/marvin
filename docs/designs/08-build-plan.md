# Document 8 of 8: BUILD PLAN
## Phased Construction Timeline

**Principle:** Build bottom-up. Each phase delivers standalone value. No phase depends on a future phase to be useful. If we stop at Phase 1, we still have a working system that's better than today.

---

## PHASE OVERVIEW

| Phase | What | Duration | Standalone Value |
|-------|------|----------|-----------------|
| Phase 1 | Lobby + Cache + Rate Tracker | Week 1 | 40-60% fewer API calls, no more blind 429s |
| Phase 2 | Receptionist + Dispatch | Week 2 | Smart routing, self-handle trivials, buffer activation |
| Phase 3 | Department Heads | Week 3 | Ralph/Ira/Tess operational, domain autonomy |
| Phase 4 | Boss + Emergency + Hardening | Week 4 | Full escalation chain, production-grade |

---

## PHASE 1: FOUNDATION (Week 1)
### Cache + Lobby + Rate Tracker

This phase alone solves the immediate pain (rate limiting).

#### Day 1: SQLite + Cache Schema

```
DELIVERABLE: Working database on VPS
```

- [ ] Create SQLite database file on VPS
- [ ] Execute schema from Doc 2 (cache_entries, cache_metrics, rate_limit_snapshots, envelopes)
- [ ] Write basic CRUD module:
  - `cache_get(key) → response | None`
  - `cache_set(key, response, intent, project, ttl)`
  - `cache_invalidate(project=None, intent=None)`
  - `cache_clear_expired()`
  - `cache_stats() → {hits, misses, entries, tokens_saved}`
- [ ] Test: write entry, read it, expire it, verify it's gone
- [ ] Verify indexes work (query by key should be <5ms)

#### Day 2: Cache Key Generation + TTL Logic

```
DELIVERABLE: Cache can classify and store/retrieve by intent
```

- [ ] Implement `generate_cache_key(intent, project, state)` from Doc 2
- [ ] Implement `get_project_state(project)` — git branch, last commit, deploy status
- [ ] Wire TTL map (status=60s, how_to=1h, trivial=24h, etc.)
- [ ] Test: same message + same state = cache hit
- [ ] Test: same message + different commit = cache miss (key changes)
- [ ] Test: entry expires after TTL
- [ ] Implement metrics logging (hit/miss/write/invalidate events)

#### Day 3: Lobby Router — DONE

```
DELIVERABLE: Messages get classified into JSON
```

- [x] Create lobby-router config from Doc 3 (updated: Ollama + OpenAI + Kimi cascade)
- [x] Implement `LobbyClassifier.classify(message) → Classification`
- [x] Implement keyword matching (free, instant, no API)
- [x] Implement Ollama local classification (free, ~100-500ms)
- [x] Implement OpenAI classification (paid, quality work)
- [x] Implement Kimi 2.5 backup (paid, when OpenAI rate limited)
- [x] Implement `_fallback_classification()` for when all providers fail
- [x] Test: 7 unit tests passing (keywords, cacheability, fallback, stats)

#### Day 4: Rate Limit Tracker — DONE

```
DELIVERABLE: Every API call updates health dashboard
```

- [x] Implement `parse_headers()` — all four formats: Groq, Anthropic, OpenAI, Moonshot
- [x] Implement `_parse_reset_duration()` — Groq "2m59.56s", ISO datetime, plain seconds
- [x] Implement `RateLimitTracker` class (in-memory + SQLite persistence)
- [x] Wire into classifier: every API response updates tracker
- [x] Handle 429: immediate RED, record retry_after, auto-recover after reset
- [x] Implement `get_all_health()` for envelope/stats
- [x] Implement `is_available()`, `should_divert()`, `seconds_until_available()`
- [x] Test: 19 unit tests passing (green/yellow/red, 429, auto-recovery, persistence, diversion)

#### Day 5: Integration + End-to-End Test

```
DELIVERABLE: Message → Lobby → Cache → [API or cached response]
```

- [ ] Wire full Phase 1 flow:
  1. Message arrives
  2. Lobby classifies (Groq 8B)
  3. Cache check (SQLite)
  4. HIT → return cached
  5. MISS → forward to Kimi 2.5 (existing flow)
  6. Response → write to cache
  7. Rate limits updated from response headers
- [ ] Test: send same status question twice → second is cached
- [ ] Test: change git commit → cache key changes → miss on third call
- [ ] Add git post-commit hook for invalidation
- [ ] Run for 2 hours of real work: measure cache hit rate
- [ ] Verify: rate limit tracker shows accurate health for all providers

#### Phase 1 Success Criteria
- [ ] Cache hit rate >15% (conservative, day 1)
- [ ] Lobby classification accuracy >80%
- [ ] Rate limit tracker reflects real provider health
- [ ] Zero regression: existing Kimi 2.5 + Haiku flow unbroken
- [ ] Cache adds <100ms to total request latency

---

## PHASE 2: ROUTING (Week 2)
### Receptionist + Dispatch + Buffer Activation

#### Day 6: Receptionist Prompt + Dispatch Table

```
DELIVERABLE: Haiku routes requests to correct destination
```

- [ ] Implement Haiku receptionist system prompt from Doc 4
- [ ] Implement dispatch table: intent × complexity → destination
- [ ] Implement `receptionist_route(envelope) → routing block`
- [ ] Implement `haiku_self_handle(envelope)` for trivials
- [ ] Wire: envelope from lobby/cache → receptionist → routing block added
- [ ] Test: trivial message → self-handled, no downstream API call
- [ ] Test: fix_error/high → routes to Claude CLI
- [ ] Test: status_check/low → routes to cache or Haiku self

#### Day 7: Buffer Model Integration

```
DELIVERABLE: Groq models activate when Kimi is throttled
```

- [ ] Set up Groq API calls for each buffer model:
  - GPT-OSS 120B (Ralph's buffer)
  - Kimi K2 0905 (Ira's buffer)
  - Qwen3 32B (Tess's buffer)
  - Llama 70B (general overflow)
- [ ] Implement `select_primary_or_buffer(department, rate_limits)` from Doc 4
- [ ] Wire rate limit tracker into routing decisions
- [ ] Test: mock Kimi red → verify request goes to department buffer
- [ ] Test: mock Kimi red + buffer red → verify cascade to next
- [ ] Test: mock all red → verify Claude CLI emergency path
- [ ] Verify: Groq buffer receives SAME envelope as Kimi would

#### Day 8: Haiku Buffer + Degraded Mode

```
DELIVERABLE: System works even when multiple providers are down
```

- [ ] Implement Haiku → Groq K2 0905 fallback (receptionist buffer)
- [ ] Implement lobby degraded mode (Groq down → skip to Haiku direct)
- [ ] Wire: full cascade chain operational end-to-end
- [ ] Test: kill Groq API key → lobby bypassed, Haiku takes over
- [ ] Test: kill Haiku → Groq K2 0905 handles receptionist role
- [ ] Test: kill everything except Claude → emergency handles all

#### Day 9: Priority-Based Diversion

```
DELIVERABLE: Yellow state preserves primary for important work
```

- [ ] Implement `should_divert_to_buffer(priority, health)` from Doc 6
- [ ] Wire: yellow state → low/normal diverts, high/critical stays
- [ ] Test: Kimi yellow + trivial request → goes to buffer
- [ ] Test: Kimi yellow + critical fix_error → stays on Kimi
- [ ] Measure: tokens saved on primary by diverting low-priority

#### Day 10: Integration Test + Cache Tier 2 Prep

```
DELIVERABLE: Full routing pipeline operational
```

- [ ] End-to-end: message → lobby → cache → receptionist → department model → response
- [ ] Verify envelope grows correctly at each stage
- [ ] Verify execution_chain logs every model touch
- [ ] Run for 4 hours of real work: measure routing accuracy
- [ ] Install all-MiniLM-L6-v2 on VPS (prep for Phase 2 cache tier)
- [ ] Begin embedding existing cache entries (background job)

#### Phase 2 Success Criteria
- [ ] Routing accuracy >85% (correct department)
- [ ] Self-handle catches >50% of trivials (zero downstream cost)
- [ ] Buffer activation works on simulated 429
- [ ] Priority diversion preserves primary for high/critical work
- [ ] Degraded mode works: any single provider failure = graceful fallback
- [ ] Envelope structure correct at every stage

---

## PHASE 3: DEPARTMENTS (Week 3)
### Ralph, Ira, Tess Operational

#### Day 11-12: Department System Prompts + Config

```
DELIVERABLE: Three specialized agents responding in character
```

- [ ] Create Ralph agent config (system prompt from Doc 5)
- [ ] Create Ira agent config (system prompt from Doc 5)
- [ ] Create Tess agent config (system prompt from Doc 5)
- [ ] Each reads project memory files on session start
- [ ] Each receives full envelope with context primer
- [ ] Test: planning question → Ralph responds in character
- [ ] Test: deploy question → Ira responds in character
- [ ] Test: test failure → Tess responds in character
- [ ] Test: wrong department → agent self-corrects or re-routes

#### Day 13: Worker Spawning

```
DELIVERABLE: Department heads delegate grunt work to Haiku
```

- [ ] Implement `spawn_worker(department, task, envelope)` from Doc 5
- [ ] Wire: department head can request Haiku to gather info
- [ ] Wire: department head can invoke Claude CLI for heavy tasks
- [ ] Test: Ralph asks for multi-file status → Haiku gathers, Ralph synthesizes
- [ ] Test: Tess needs debugging → Claude CLI invoked, result returned
- [ ] Verify: worker results logged in execution_chain

#### Day 14: Department Buffer Quality Testing

```
DELIVERABLE: Buffer models produce usable (not just any) output
```

- [ ] Force each department onto its buffer model
- [ ] Run 10 real tasks per department on buffer only
- [ ] Compare: buffer output vs. Kimi 2.5 output for same tasks
- [ ] Document quality gaps per department:
  - Ralph on GPT-OSS 120B: planning quality?
  - Ira on Kimi K2 0905: infra task quality?
  - Tess on Qwen3 32B: test reporting quality?
- [ ] Adjust buffer prompts if quality is below acceptable threshold
- [ ] Add buffer-specific instructions where needed (e.g., "Reasoning: medium" for GPT-OSS)

#### Day 15: Cache Tier 2 + 3

```
DELIVERABLE: Pattern matching + context primers active
```

- [ ] Implement Tier 2: embedding similarity search on cache miss
- [ ] Threshold: >0.85 cosine = hit (test with 20 similar/dissimilar pairs)
- [ ] Implement Tier 3: context primer attachment on full miss
- [ ] Gather project state → attach to envelope → measure token reduction
- [ ] Test: "fix import error" after previous import fix cached → Tier 2 hit
- [ ] Measure: combined cache hit rate (target >35% with Tier 1+2)
- [ ] Measure: token reduction from Tier 3 primers (target >25%)

#### Phase 3 Success Criteria
- [ ] All three departments respond in character with domain expertise
- [ ] Departments handle tasks autonomously (no boss escalation on routine work)
- [ ] Worker spawning functional (Haiku subtasks, Claude CLI heavy tasks)
- [ ] Buffer quality acceptable for each department (documented gaps)
- [ ] Cache Tier 2+3 operational (combined hit rate >35%)
- [ ] Envelope execution_chain shows full audit trail

---

## PHASE 4: BOSS + HARDENING (Week 4)
### Full Escalation Chain + Production Grade

#### Day 16-17: Boss Implementation

```
DELIVERABLE: Cross-domain escalation resolved by Boss
```

- [ ] Implement Boss system prompt from Doc 7
- [ ] Implement `boss_process(envelope)` from Doc 7
- [ ] Implement Boss budget tracking (max 10% of daily Kimi tokens)
- [ ] Implement Boss → OpenAI fallback when over budget
- [ ] Wire: department escalation → Boss → decision → delegate back
- [ ] Test: simulate Ralph/Tess conflict → Boss arbitrates
- [ ] Test: Boss budget exhausted → OpenAI fallback produces usable decision
- [ ] Test: Boss sets escalate_further → Claude emergency fires

#### Day 18: Emergency Tier

```
DELIVERABLE: Claude Opus emergency path functional
```

- [ ] Implement `emergency_claude(envelope, reason)` from Doc 7
- [ ] Wire: all-providers-exhausted detection → emergency
- [ ] Wire: boss escalate_further → emergency
- [ ] Wire: context overflow detection → emergency
- [ ] Wire: 2+ failed attempts detection → emergency
- [ ] Test: simulate all-red → emergency activates
- [ ] Test: emergency response gets cached (expensive = cache it)
- [ ] Implement emergency budget alert (5+ per day = architecture smell)

#### Day 19: Monitoring + Metrics Dashboard

```
DELIVERABLE: Visibility into system health
```

- [ ] Implement all SQL queries from Docs 2, 6, 7
- [ ] Build simple metrics report (run daily or on-demand):
  - Cache: hit rate per tier, tokens saved, invalidation frequency
  - Rate limits: time in green/yellow/red per provider
  - Routing: requests per department, self-handle rate
  - Boss: escalation count, reasons, architecture health score
  - Emergency: activation count, reasons, cost
- [ ] Set up alerts:
  - Boss >5 calls/day → "departments may need better prompts"
  - Emergency >3 calls/day → "boss may need improvement"
  - Cache hit rate <20% → "cache invalidation may be too aggressive"
  - Any provider >50% time in red → "consider upgrading tier or adding buffer"

#### Day 20: Hardening

```
DELIVERABLE: Production-grade resilience
```

- [ ] Abstract all model selections behind config file (not hardcoded)
- [ ] Add graceful handling for Groq model deprecation (model removed → skip)
- [ ] Cache size management: prune entries >30 days, cap total DB at 500MB
- [ ] GPT-OSS reasoning token leak: parse and strip on every response
- [ ] Compound rate limit awareness: track cascade impact
- [ ] Load test: simulate 4-hour sustained session, verify no crashes
- [ ] Document all config files, prompts, and tuning knobs
- [ ] Backup strategy: SQLite DB backed up with VPS daily

#### Phase 4 Success Criteria
- [ ] Full escalation chain: department → boss → emergency works end-to-end
- [ ] Boss calls <5/day during normal operation
- [ ] Emergency calls <3/day during normal operation
- [ ] All config externalized (model swap = config change, not code change)
- [ ] 4-hour sustained load test passes without crash or data loss
- [ ] Metrics dashboard shows accurate system health
- [ ] All 8 spec documents reflected in working code

---

## POST-BUILD: ONGOING TUNING

### Week 5+: Optimize Based on Data

Once the system runs for a week with real usage:

1. **Tune classification accuracy** — Review lobby misclassifications from envelope logs. Add few-shot examples to 8B prompt for common mistakes.

2. **Tune cache TTLs** — If hit rate is low, TTLs may be too aggressive. If stale answers appear, TTLs are too generous. Adjust per-intent.

3. **Tune department prompts** — Review execution_chains where departments escalated unnecessarily. Improve prompts to handle those cases autonomously.

4. **Tune buffer model selection** — If a buffer model is consistently poor for a department, swap it. Config change, not code change.

5. **Tune boss threshold** — If boss is getting trivial escalations, tighten the escalation triggers. If departments are stuck without escalating, loosen them.

6. **Evaluate Groq model changes** — Groq adds/removes models. Check monthly. Update config if better options appear.

7. **Evaluate Kimi K2.5 vs K2.5+ or K3** — Moonshot ships updates. If primary model improves, the whole system benefits. If pricing changes, adjust boss budget.

---

## QUICK REFERENCE: FILE MAP

```
agents/
├── lobby-router.json          # 8B config (Doc 3)
├── lobby-router.md            # Lobby architecture docs
├── lobby_dispatcher.py        # Classification + dispatch (Doc 3-4)
├── receptionist.py            # Haiku routing logic (Doc 4)
├── departments/
│   ├── ralph.json             # Scrum master config (Doc 5)
│   ├── ira.json               # Infra guardian config (Doc 5)
│   ├── tess.json              # Test engineer config (Doc 5)
│   └── worker.py              # Haiku worker spawning (Doc 5)
├── boss.py                    # Boss escalation logic (Doc 7)
├── emergency.py               # Claude Opus last resort (Doc 7)
├── cache/
│   ├── cache.py               # SQLite CRUD + TTL (Doc 2)
│   ├── cache_invalidate.py    # Git hook + manual clear (Doc 2)
│   ├── embeddings.py          # Tier 2 similarity (Doc 2, Phase 2)
│   └── primer.py              # Tier 3 context primer (Doc 2, Phase 2)
├── rate_limiter/
│   ├── tracker.py             # RateLimitTracker class (Doc 6)
│   ├── headers.py             # Header parsing (Doc 6)
│   └── circuit_breaker.py     # 429 handling + cascade (Doc 6)
├── envelope.py                # Envelope create/update/archive (Doc 1)
└── metrics/
    ├── dashboard.py            # Metrics queries + reports
    └── alerts.py               # Threshold-based alerting

config/
├── models.json                # All model configs (swap without code change)
├── buffers.json               # Department → buffer mapping
├── ttl.json                   # Cache TTL per intent
└── thresholds.json            # Green/yellow/red thresholds

db/
└── openclaw.sqlite            # Cache + metrics + envelopes + rate limits
```

---

## THE BOTTOM LINE

**Week 1 alone** delivers: 40-60% fewer API calls, rate limit visibility, and no more blind 429s.

**Week 2** adds: smart routing, self-handling of trivials, and automatic buffer switching.

**Week 3** adds: domain-specialized agents that work autonomously 90%+ of the time.

**Week 4** adds: full escalation chain, emergency handling, and production-grade monitoring.

Each week stands on its own. Stop at any phase and you still have a better system than today.
