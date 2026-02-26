# SIM Office System v1
## Product Requirements Document + Constitutional Guardrails

### 1. Mission
Build a deterministic, event-driven, agent-based orchestration system (“SIM Office”) that:
- Routes work cost-efficiently (Keyword → Ollama → OpenAI → Fallback)
- Models agent life-state in fine-grained, measurable ways
- Evolves skills and specialization over time
- Tracks inter-agent trust and collaboration
- Allows autonomy without losing control
- Provides a visual “office” dashboard for non-technical management
- Remains replayable, testable, and cost-governed

The system must feel alive while remaining fully deterministic and auditable.

---

### 2. Non-Negotiable Architectural Principles
1. **Event-Sourced Core**
   - All state changes derived from logged events
   - Replay regenerates identical agent state
2. **Deterministic Escalation**
   - OpenAI escalation only if triggers fire, policy allows, and justification is logged
3. **No Hidden State**
   - UI reflects measurable system conditions only
4. **Circuit Breakers Everywhere**
   - Ollama breaker, OpenAI breaker, help-loop breaker, retry caps
5. **Constitution Over Convenience**
   - No silent escalation, no unlogged tool use, no runtime rule mutation without config changes

---

### 3. System Layers

#### 3.1 Lobby / Dispatcher (Already Spec’d)
Responsibilities:
- Classify inbound request
- Route cheapest viable layer
- Produce routing contract output

Routing output must include:
- `layer`
- `intent`
- `confidence`
- `reason`
- escalation trigger (if any)
- health snapshot
- cost guard status

#### 3.2 SIM Control Plane
Wrap every inbound request into a SIM Envelope.

**SIM Envelope schema (minimum):**
```json
{
  "requestId": "uuid",
  "sessionId": "string",
  "userId": "string",
  "timestamp": "iso8601",
  "routing": {},
  "policy": {
    "mode": "normal|brownout|safe",
    "costCeilingUsd": 0.05,
    "openaiAllowed": true,
    "toolsAllowed": []
  },
  "context": {},
  "input": {}
}
```

SIM responsibilities:
- Emit lifecycle events
- Enforce brownout + tool gating + breaker policy
- Log all decisions
- Orchestrate agent handoffs

---

### 4. Event System (Source of Truth)
All subsystems must react only to events.

Core event types:
- `TASK_ASSIGNED`
- `TASK_STARTED`
- `TASK_COMPLETED`
- `TASK_FAILED`
- `THROTTLED`
- `DEPENDENCY_BLOCKED`
- `HELP_REQUESTED`
- `HELP_RECEIVED`
- `HANDOFF`
- `ESCALATED_TO_PREMIUM`
- `BREAKER_TRIPPED`
- `BROWNOUT_ENTERED` / `BROWNOUT_EXITED`

Event requirements:
- `timestamp`, `agentId`, `requestId`, `severity`, structured `payload`
- Replay must regenerate: Life, Growth, Relationships, Autonomy

---

### 5. Agent Model

#### 5.1 Identity (Static)
- role
- provider
- capabilities
- escalation authority
- limits (timeouts, retries)
- personality skin (UI-only)

Identity **cannot** mutate at runtime.

#### 5.2 Life System (Dynamic State)
Variables (0..1):
- energy, stress, morale, focus, confidence, friction

Derived:
- mood label, burnout risk

Rules:
- event-based deltas
- time-based decay + recovery when idle
- burnout is pattern-based (sustained stress/throttle/block/low success)

Burnout must trigger:
- suggested UI remedy
- possible automatic redistribution (policy-driven)

#### 5.3 Growth System
Track:
- skill vector by task type
- experience weighted by difficulty
- mastery thresholds

Growth affects:
- assignment bias
- autonomy ceiling
- escalation confidence

#### 5.4 Relationship System
Trust graph (directed weighted edges) updated on:
- successful help
- failed handoff
- repeated collaboration
- escalation blame loops

Trust influences:
- handoff selection
- help probability
- collaboration success rate

#### 5.5 Autonomy System
Autonomy derived from:
- morale, confidence, skill mastery, peer trust, current policy mode

Autonomy governs:
- proactive escalation
- self-assignment
- early help request
- initiative

Brownout clamps autonomy.

#### 5.6 Communication System
Message bus abstraction (logged and replayable).

Supports:
- Agent → Agent (handoff, help, escalation)
- Agent → User (status, proactive updates)
- System → Agents (policy change, brownout)

No direct side-channels allowed.

---

### 6. Office UI Requirements

#### 6.1 Office Overview
- agent cards
- queue size
- needs meters
- mood indicator
- breaker status
- provider health
- cost meter

#### 6.2 Agent Desk View
- current task
- needs breakdown
- event timeline
- skill levels
- top collaborators

#### 6.3 Task Board
- queues
- blocked tasks
- escalation candidates
- brownout indicator

#### 6.4 Relationship Graph
- trust visualization
- help flow map
- collaboration health

**UI truth rule:** every visual state must map to measurable signals and show causes + remedies.

---

### 7. Constitutional Guardrails
These rules override all system logic.

1. **Cost Guard**
   - Every OpenAI call logs: trigger, policy approval, cost estimate, outcome
   - Brownout restricts premium calls automatically
2. **Replayability**
   - State reproducible from event log; no hidden caches without events
3. **No Infinite Loops**
   - help depth cap, retry cap, breakers on repeated failure
4. **Tool Safety**
   - allowlisted CLI/tools only; no arbitrary shell; no dynamic eval
5. **Config Authority**
   - thresholds configurable; no hard-coded exceptions

---

### 8. Phased Build Plan (High Level)
- **Phase 1:** Envelope + event store + breakers + basic life + replay test
- **Phase 2:** Orchestration (handoff/help) + escalation + brownout
- **Phase 3:** Growth + Relationships + Autonomy gating
- **Phase 4:** UI MVP
- **Phase 5:** Chaos + audit tests

---

### 9. Test Requirements
Must include:
- deterministic replay test
- escalation justification test
- brownout enforcement test
- breaker trip/reset test
- skill growth progression test
- trust graph update test
- autonomy gating test
- UI state mapping test

---

### 10. Definition of Done
v1 complete when:
- replay produces identical state
- every premium call is explainable and justified
- specialization emerges deterministically
- burnout produces actionable UI suggestions
- no infinite handoff/help loops
- non-technical user can answer:
  - “Who is overloaded?”
  - “Why is this blocked?”
  - “Why did we escalate?”
  - “What should I adjust?”
