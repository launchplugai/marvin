# ADR-001: Constitutional Principles

## Status
ACCEPTED

## Context
Marvin is a system built to solve real-world constraints: rate limits, API costs, and multi-agent coordination. Without clear principles, decisions will drift. This ADR codifies the constitution.

## Decision

Marvin operates under these inviolable principles:

### 1. **Cache First**
Every request is an opportunity to avoid the next one. Before any API call, ask: "Have we seen this before?"
- Check cache before forwarding downstream
- Write every successful response to cache
- Invalidate cache aggressively on project state changes
- Measure everything: hit rate, tokens saved, stale answers

### 2. **Free Tier Primary**
Use free/cheap models as the primary workload, paid models as exceptions.
- Groq models are the default (free tier)
- Anthropic models are escalation-only
- OpenAI is last resort
- Every paid call must be justified in execution chain

### 3. **Transparent Fallback**
Users should never see throttling. When a model hits rate limits, automatically fall back to a buffer.
- No failures visible to user
- No retry loops or backoff visible to user
- Buffer quality acceptable for the task (may be lower, never unusable)
- Execution chain logs the fallback for audit

### 4. **Graceful Degradation**
If any component fails (cache, a model, rate limiter), the system continues.
- Cache down? Skip it, go directly to API
- Kimi throttled? Use Groq buffer
- Haiku throttled? Use Groq Kimi K2
- All paid models down? Emergency fallback to Claude
- **The system never refuses work; it finds a way**

### 5. **Metrics Obsessed**
What you don't measure, you can't optimize. Instrument everything.
- Every cache hit/miss logged
- Every API call logged with tokens, cost, latency
- Every rate limit event captured with provider, threshold, time
- Every escalation logged with reason + cost
- Dashboards updated in real-time
- Decisions made based on data, not gut feel

### 6. **Production Ready**
Code is only "done" when it handles failure, not when happy-path works.
- All external APIs must have timeout + retry logic
- All parsing must handle malformed input
- All config must validate before use
- All databases must have backup + recovery tested
- Load tests must pass before production deployment
- Monitoring must alert before human intervention needed

### 7. **Autonomous Specialization**
Department heads (Ralph/Ira/Tess) must handle 90%+ of their domain autonomously.
- Escalation to Boss should be <5% of requests
- Escalation to Emergency should be <3% of requests
- If escalation is higher, improve the agent, not the rule

### 8. **Semantic Versioning of Prompts**
Changing a department's system prompt is a decision, not a fix.
- Document prompt changes as ADRs
- Test prompt changes before deployment
- Track prompt versions in execution_chain
- Revert capability must exist for any prompt

## Consequences

**Positive:**
- Clear tradeoff decisions (rate limit over latency? cache over freshness?)
- Consistent behavior across all modules
- Easy to onboard new team members ("read the constitution")
- Disputes resolved by reference to first principles

**Negative:**
- Requires discipline to enforce (easy to justify violations)
- May conflict with urgency ("just pay for Claude for now")
- Measuring everything has a cost (CPU, disk for logging)

## Related ADRs
- ADR-002: Cost vs Performance Trade-offs
- ADR-003: Rate Limit Fallback Hierarchy
- ADR-004: Cache Invalidation Strategy
