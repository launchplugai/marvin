# ADR-003: Rate Limit Fallback Hierarchy

## Status
ACCEPTED

## Context
When a model hits rate limits, requests must go somewhere. This ADR defines the fallback chain for each component.

## Decision

### Global Fallback Chain
```
Primary Model → Buffer 1 → Buffer 2 → Buffer 3 → Emergency
```

### Specific Chains by Role

#### Lobby (Intent Classification)

```
Primary:   groq/llama-3.1-8b-instant (12k TPM)
Buffer 1:  groq/llama-3.3-70b-versatile (12k TPM, separate pool)
Buffer 2:  Haiku skip (forward to Receptionist directly, less context)
Emergency: Hardcoded classification (keywords + rule-based fallback)
```

- Detection: 429 from Groq → activate Buffer 1
- Retry: Immediate, no backoff
- Timeout: 10 seconds per attempt
- Max retries: 3
- Cost of fallback: Known + acceptable (Llama 70B vs 8B minimal difference)

#### Receptionist (Haiku Routing)

```
Primary:   Claude Haiku (50k RPM)
Buffer 1:  groq/moonshotai/kimi-k2-instruct (12k TPM, good at routing)
Buffer 2:  groq/llama-3.3-70b-versatile (12k TPM, fallback quality)
Emergency: Hardcoded routing rules (envelope + envelope.intent → destination)
```

- Detection: 429 from Anthropic + repeated failures → activate buffer
- Retry: Exponential backoff (1s, 2s, 4s, 8s max)
- Timeout: 15 seconds per attempt
- Max retries: 2
- Cost of fallback: ~$0 (Groq)
- Quality trade-off: Kimi K2 good at routing, may disagree with Haiku on edge cases

#### Department Heads (Ralph/Ira/Tess - Kimi 2.5 Primary)

```
Primary:   Moonshot Kimi 2.5 (rate limit depends on plan)
Buffer 1:  groq/moonshotai/kimi-k2-instruct (12k TPM, same model family)
Buffer 2:  Department-specific (see below)
Buffer 3:  groq/llama-3.3-70b-versatile (universal)
Emergency: Claude Sonnet (quality >> cost when escalated)
```

**Ralph (Scrum Master):**
- Buffer 2: groq/gpt-oss-120b (reasoning + planning focused)

**Ira (Infra Guardian):**
- Buffer 2: groq/qwen3-32b (good at infrastructure reasoning)

**Tess (Test Engineer):**
- Buffer 2: groq/qwen3-32b (strong at test reasoning)

Detection rules by rate limit health:
- **Green (>30% TPM remaining):** Use Kimi 2.5 exclusively
- **Yellow (10-30% remaining):** Route low/normal priority to buffer, keep high/critical on Kimi
- **Red (<10% remaining):** All new work to buffer
- **Critical red (0% or 429):** All work to buffer
- **All buffers red:** Emergency escalation (Sonnet)

### Boss (Cross-Domain Arbitration - Kimi 2.5)

```
Primary:   Moonshot Kimi 2.5
Buffer:    Claude Haiku (different provider, high quality)
Emergency: Claude Sonnet (if Boss call itself fails)
```

- Budget limit: 10 calls/day max (5% of typical daily spend)
- If budget exhausted: Haiku handles boss decisions
- Timeout: 30 seconds (complex decision, allow more time)

### Emergency Escalation

```
When ALL else fails:
Claude Opus (unrestricted, for true emergencies only)
```

Triggers:
- 2+ consecutive fallback failures in same domain
- Rate limit red for >5 minutes across all buffers
- Context overflow despite compaction
- Data loss risk detected

## Rate Limit State Machine

```
START
├─ GREEN (>30% TPM)
│  └─ Use primary
│  └─ On 429 → YELLOW, activate buffer
├─ YELLOW (10-30%)
│  └─ Low priority → buffer, high priority → primary
│  └─ On repeated 429 → RED, all to buffer
├─ RED (<10%)
│  └─ All requests to buffer
│  └─ If buffer also 429 → CRITICAL
├─ CRITICAL (0% or exhausted)
│  └─ All to emergency (Sonnet/Opus)
│  └─ Alert human (usually means need upgrade)
└─ RECOVERED (rate limit resets)
   └─ Back to GREEN

Timeout: After 1 hour in RED, assume provider issue (not rate limit) → skip to emergency
```

## Implementation Requirements

### Tracking

Every fallback activation must log:
- Timestamp
- Original model + TPM remaining
- Fallback model selected
- Request details (intent, department, size)
- Execution time
- Quality assessment (worked / degraded / failed)

### Monitoring

Daily report:
- How many fallbacks per provider?
- Which models are bottlenecks?
- Are buffers adequate quality?
- Should we upgrade rate limits?

### Testing

Before deployment, simulate:
- Single model 429 → verify buffer catches it
- Multiple model 429 → verify cascade works
- All models 429 → verify emergency activates
- Emergency bottleneck → verify system degradation is acceptable
- Recovery → verify auto-upgrade to green

## Related ADRs
- ADR-001: Constitutional Principles
- ADR-002: Cost vs Performance Trade-offs
