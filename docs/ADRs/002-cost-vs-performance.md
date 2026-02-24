# ADR-002: Cost vs Performance Trade-offs

## Status
ACCEPTED

## Context
Marvin runs in cost-constrained environments. We must make explicit trade-offs between model quality, latency, and API spend.

## Decision

### Tier Selection Rules

**When to use Groq (free tier):**
- Classification (Lobby)
- Self-serving trivials (Receptionist)
- Grunt work (Haiku workers)
- Fallback/buffer work
- >95% of all requests by volume

Cost: $0/request | Latency: 200-800ms | Quality: Good enough for purpose

**When to use Haiku ($0.005/1K input + output):**
- Routing decisions (Receptionist)
- Inter-department coordination
- Context aggregation
- Spelling out complex reasoning to departments
- <5% of requests by volume, but high-leverage

Cost: ~$0.0001/request | Latency: 300-1000ms | Quality: Good

**When to use Kimi 2.5 ($0.008-0.012/1K):**
- Department primary work (Ralph/Ira/Tess)
- Customer-facing responses
- Architectural decisions
- Code review + complex debugging
- <3% of requests by volume

Cost: ~$0.001-0.002/request | Latency: 500-1500ms | Quality: Very Good

**When to use Claude Sonnet ($0.003/$0.015):**
- Boss arbitration (edge cases)
- Complex multi-file refactoring
- <1% of requests, only on escalation

Cost: ~$0.0005-0.001/request | Latency: 500-2000ms | Quality: Excellent

**When to use Claude Opus ($0.015/$0.075):**
- Emergency path only
- Critical security decisions
- <0.1% of requests, reserved for true emergencies

Cost: ~$0.005/request | Latency: 1000-3000ms | Quality: Best-in-class

### Budget Allocation (Monthly)

Assume $100/month API budget across all providers:

- Groq: $0 (free tier, used for 95% of work)
- Haiku: $20 (5000 calls × $0.004 avg)
- Kimi 2.5: $60 (50,000 calls × $0.0012 avg)
- Sonnet: $15 (10,000 calls × $0.0015 avg)
- Opus: $5 (reserved for 100 emergency calls max)

**Overage alerts:**
- Haiku >$25/month → review Receptionist routing
- Kimi >$80/month → review Department autonomy
- Sonnet >$20/month → review Boss escalation
- Opus >$10/month → architecture smell, investigate immediately

### Performance Minimums

All responses must meet these minimums:

- **Latency:** <3 seconds end-to-end (cache hit <100ms, API call <2s)
- **Quality:** Task-specific (see below)
- **Availability:** 99.5% uptime (allow 36 min/month downtime)

### Quality Minimums by Task Type

| Task | Minimum Quality | Acceptable Model |
|------|-----------------|-----------------|
| Status check | "Accurate info, boring is fine" | Groq 8B |
| How-to question | "Correct command, could be verbose" | Groq 70B or Haiku |
| Trivial fix | "Works, not elegant" | Groq or Haiku |
| Code review | "Catches real issues" | Kimi 2.5 or Claude |
| Architecture decision | "Considers trade-offs" | Claude Sonnet+ |
| Security decision | "Thorough, defensive" | Claude Opus |

## Consequences

**Positive:**
- Clear escalation rules (don't reach for expensive models)
- Budget predictable (most work on free tier)
- Performance expectations explicit
- Cost-quality trade-offs visible

**Negative:**
- Temptation to "just use Claude" when Groq is struggling
- Budget constraints may force degradation during peak usage
- Requires discipline on escalation threshold

## Exceptions

Violating this ADR requires explicit approval + documentation:
- Crisis response (security issue, data loss, etc.)
- One-time experimental work (evaluating new model)
- Customer escalation (paying customer demands premium model)

All exceptions must be logged in execution_chain with reason.

## Related ADRs
- ADR-001: Constitutional Principles
- ADR-003: Rate Limit Fallback Hierarchy
