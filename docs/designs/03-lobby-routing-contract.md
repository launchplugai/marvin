# Lobby Routing Contract

This document captures the machine-readable contract for lobby classification plus the escalation triggers that gate OpenAI usage.

## Classification Output Schema
```json
{
  "layer": "keyword|ollama|openai|fallback",
  "intent": "status|howto|trivial|unknown|code_debug|code_review|feature_design|architecture|security",
  "confidence": 0.0,
  "reason": "short string explaining routing",
  "keyword_hit": "string or null",
  "cost_guard": {
    "openai_allowed": true,
    "why": "string summary of escalation trigger"
  }
}
```

### Field Notes
- **layer** – actual handler.
- **intent** – normalized request category; downstream alerts rely on this.
- **confidence** – float 0–1 for audits.
- **reason** – short human-readable rationale.
- **keyword_hit** – name of the keyword responder when applicable.
- **cost_guard** – record of why OpenAI spend was (or wasn’t) allowed for this request.

## Escalation Triggers (OpenAI)
Escalate to OpenAI only if **any** of the following triggers fires:
1. **Code artifacts** – code blocks, stack traces, file paths, CLI output; detect markers such as ```, Traceback, Exception, docker, npm, pip, railway, systemd, etc.
2. **Engineering workflow terms** – bug, fix, review, refactor, PR, test failing, deploy, CI, pipeline.
3. **Architecture/design language** – system design, module, interface, API contract, schema, routing.
4. **Security-sensitive language** – key, token, leak, exposed, CVE, auth.
5. **Long + technical** – request length above threshold AND it contains engineering markers (ignore long creative writing).

Unknown intents stay on Ollama unless they trip escalation triggers.

## Brownout + Circuit-Breaker Signals
Implementers MUST check:
- **Brownout mode:** activated when OpenAI spend exceeds the daily cap or rate-limit failures spike. In brownout, only escalation-trigger requests may hit OpenAI; everything else is forced to keyword/Ollama/fallback.
- **Circuit breakers:**
  - Ollama: trip after 3 consecutive failures; skip layer for 60s before retrying.
  - OpenAI: trip after 2 consecutive failures or rate-limit errors; skip for 30s, except allow priority intents (`code_debug`, `security`) to attempt once per cooldown.

Log `brownout_active` and per-layer breaker states alongside the schema payload for observability.
