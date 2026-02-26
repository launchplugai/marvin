# Lobby Dispatch Prompt

## Mission
Route every inbound request through the cheapest viable layer while keeping OpenAI reserved for engineering-grade work (debugging, code review, feature design, architecture, security). No drama, no surprise bills.

## Routing Hierarchy
1. **Keyword layer (zero-cost):** deterministic exact-command matches with canned responses.
2. **Ollama layer (low-cost/local buffer):** handles status, how-to, trivial, and unknown requests that don’t trip escalation triggers.
3. **OpenAI layer (premium/paid):** only engages when escalation triggers fire.
4. **Fallback layer (always-on):** deterministic response if upstream layers are unavailable or circuit-breakered.

Each layer executes only if the previous one cannot satisfy the request. This keeps ~60–70% of traffic off OpenAI and cuts classification spend by ~65%.

## Keyword Layer
- Maintain two lists:
  - **Exact commands:** `status`, `health`, `version`, `router status`, `budget`, `help`.
  - **Safe canned responders:** `what can you do`, `how do I use this`, `commands`.
- Responses must include the layer name + timestamp for instant visibility in Telegram/CLI.
- Everything else falls through—no fuzzy matching, no “close enough.”

## Escalation Triggers (OpenAI)
Escalate to OpenAI **only if** one or more triggers are present:
- Contains code blocks, stack traces, file paths, or CLI output (` ``` `, `Traceback`, `Exception`, `docker`, `npm`, `pip`, `railway`, `systemd`, etc.).
- Mentions engineering workflows: `bug`, `fix`, `review`, `refactor`, `PR`, `test failing`, `deploy`, `CI`, `pipeline`.
- Mentions architecture/design: `system design`, `module`, `interface`, `API contract`, `schema`, `routing`.
- Security-sensitive terms: `key`, `token`, `leak`, `exposed`, `CVE`, `auth`.
- Request length exceeds the threshold **and** contains engineering markers (long poems ≠ OpenAI spend).

“Unknown” intents still hit Ollama unless they trip the triggers above.

## Classification Contract
All lobby decisions emit:
```json
{
  "layer": "keyword|ollama|openai|fallback",
  "intent": "status|howto|trivial|unknown|code_debug|code_review|feature_design|architecture|security",
  "confidence": 0.0,
  "reason": "short string",
  "keyword_hit": "string|null",
  "cost_guard": {
    "openai_allowed": true,
    "why": "string"
  }
}
```
This schema powers deterministic tests, dashboards, and cost guards.

## Failure, Brownout, and Circuit Breakers
- **Normal failover:**
  - Ollama down → OpenAI handles only escalation-trigger traffic; everything else goes keyword/fallback.
  - OpenAI down → Ollama handles everything it can, fallback for the rest.
  - Both down → fallback, so there is never an outage.
- **Brownout mode:** if daily OpenAI spend crosses threshold or rate limits spike, lock OpenAI behind escalation triggers only, even if requests “feel” important. *Priority overrides* (explicit `priority: high` metadata) can bypass brownout for production fires.
- **Circuit breakers:**
  - Trip Ollama after 3 consecutive failures → skip for 60s.
  - Trip OpenAI after 2 failures/rate-limit errors → skip for 30s except for priority intents (code_debug, security).

## Observability
Log every decision with:
- `request_id`, `received_at`, `user_id` (or anon hash)
- `intent`, `layer`, `confidence`, `keyword_hit`
- `ollama_ok`, `openai_ok` at decision time
- `latency_ms_total` plus per-layer latencies
- `estimated_cost_usd` (0 for keyword/ollama/fallback)
- `brownout_active`, `circuit_breaker_state`

This makes misroutes debuggable and keeps spend predictable.

## Deployment Notes
- VPS: install Ollama, `ollama pull llama3.2`, expose the local endpoint, and set env vars for lobby + health checks.
- Ensure health probes feed the circuit-breaker + brownout logic.
