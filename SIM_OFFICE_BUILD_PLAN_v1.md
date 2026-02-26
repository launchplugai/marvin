# SIM Office System v1
## Build Plan + Repo Structure (Execution Authority)

### 0. Rule of the land
- **No UI before replay tests pass.**
- **No premium calls without logged trigger + justification.**
- **All state derived from events; no hidden side-state.**

---

## 1. Repo Structure (recommended)
```
/sim-office/
  /docs/prd/
    SIM_OFFICE_SYSTEM_v1.md
    SIM_OFFICE_BUILD_PLAN_v1.md

  /config/
    agents.registry.json
    keywords.registry.json
    policy.defaults.json
    thresholds.defaults.json

  /src/
    /core/
      envelope.ts
      events.ts
      eventStore.ts
      time.ts
      schema.ts

    /policy/
      lobbyContract.ts
      escalation.ts
      brownout.ts
      breakers.ts
      toolGate.ts

    /agents/
      registry.ts
      providers/
        ollama.ts
        groq.ts
        openaiCli.ts
        kimi.ts
      orchestrator.ts
      taskRouter.ts
      runtime.ts

    /state/
      reducers/
        life.reducer.ts
        growth.reducer.ts
        relationship.reducer.ts
        autonomy.reducer.ts
      selectors/
        agentStatus.ts

    /comms/
      bus.ts
      triggers.ts
      templates.ts
      notifier.ts

    /observability/
      decisionLog.ts
      metrics.ts
      audit.ts

    /ui/
      /api/
        officeState.ts
        agentDetail.ts
        taskBoard.ts

  /tests/
    /unit/
    /golden/
    /integration/
    /chaos/
```

---

## 2. Epics and Tickets (with dependencies)

### EPIC A — Core event-sourced spine
**A1 — SIM Envelope + schema validation**
- DoD: invalid envelopes fail fast; required fields present
- Test: `tests/unit/envelope.test.ts`

**A2 — Event types + append-only event store**
- DoD: append/read by requestId/agentId/sessionId; immutability
- Test: `tests/unit/events.test.ts`

**A3 — Decision logging + schema enforcement**
- DoD: exactly one decision log per dispatch; schema validated in tests
- Test: `tests/unit/decisionLog.test.ts`

---

### EPIC B — Policy enforcement (cost shield, breakers, tools)
**B1 — Lobby routing contract enforcement** (depends A1)
- DoD: rejects invalid routing decisions; persists routing in envelope
- Test: `tests/golden/routing.golden.test.ts` (table-driven)

**B2 — Circuit breakers** (depends A2)
- DoD: trip on N failures; reset after TTL; state queryable
- Tests: `tests/unit/breakers.test.ts`, `tests/chaos/breakerStorm.test.ts`

**B3 — Brownout mode clamps** (depends B1)
- DoD: brownout enter/exit; clamps premium + autonomy actions
- Test: `tests/integration/brownoutClamp.test.ts`

**B4 — Escalation triggers + justification logging** (depends B1, A3)
- DoD: premium call requires trigger + policy approval; refuse otherwise
- Test: `tests/unit/escalation.test.ts`

**B5 — Tool allowlist gate**
- DoD: allowlisted only; violations blocked and logged
- Test: `tests/unit/toolGate.test.ts`

---

### EPIC C — Agent runtime + orchestration
**C1 — Agent registry loader**
- DoD: schema validated at boot; identity static; limits applied
- Test: `tests/unit/agentRegistry.test.ts`

**C2 — Provider adapters** (depends C1)
- DoD: common interface; timeouts; retries; failures emit events
- Test: `tests/integration/dispatchToAgent.test.ts` (mock providers)

**C3 — Orchestrator: assign/handoff/help** (depends A2, B2, C1)
- DoD: bounded help depth/TTL; emits handoff/help events; respects policy
- Test: `tests/integration/helpHandoffFlow.test.ts`

---

### EPIC D — State reducers (pure functions over events + ticks)
**D1 — Life reducer**
- DoD: deltas + decay/recovery + burnout detection
- Test: `tests/unit/life.test.ts`

**D2 — Growth reducer**
- DoD: skill/xp/mastery deterministic, weighted by difficulty
- Test: `tests/unit/growth.test.ts`

**D3 — Relationship reducer**
- DoD: trust edges updated from help/handoff outcomes; loop penalties
- Test: `tests/unit/relationship.test.ts`

**D4 — Autonomy reducer + gates** (depends D1–D3, B3)
- DoD: derived autonomy; brownout clamps
- Test: `tests/unit/autonomy.test.ts`

**D5 — State selectors** (depends D1–D4)
- DoD: one “office truth” per agent: mood+causes, needs, queue pressure, collaborators
- Test: `tests/golden/eventReplay.golden.test.ts` passes (replay -> identical outputs)

---

### EPIC E — Communication system
**E1 — Message bus + schemas** (depends A2)
- DoD: messages logged and replayable; no side-channels
- Test: `tests/unit/commsBus.test.ts`

**E2 — Trigger rules** (depends E1, D5)
- DoD: state->message mapping; includes measurable cause + suggested remedy
- Test: `tests/integration/commsTriggers.test.ts`

---

### EPIC F — Office UI MVP (read-only projection)
**F1 — Office state API** (depends D5)
- DoD: derived state only; includes “why” fields
- Test: `tests/integration/officeStateApi.test.ts`

**F2 — Office overview UI** (depends F1)
- DoD: tooltips show causes; remedy buttons emit policy events (not magic)
- Test: UI snapshots/basic harness if available

---

### EPIC G — Chaos + durability
**G1 — Provider-down simulations** (depends C2, B2)
- DoD: reroute per policy; breakers trip; no outage (fallback)
- Test: `tests/chaos/providerDown.test.ts`

---

## 3. Build Order (don’t freestyle)
1) A1–A3  
2) B1–B4  
3) C1–C3  
4) D1–D5  
5) E1–E2  
6) F1–F2  
7) G1  

---

## 4. Deliverables to produce immediately
- `agents.registry.json` (6 starter agents)
- `keywords.registry.json` (exact-match commands)
- `policy.defaults.json` and `thresholds.defaults.json`
- `routing.golden.test.ts` with 20+ cases

---

## 5. Acceptance Gate
CI must fail if:
- replay differs from expected
- premium call lacks justification
- schema validation fails
- help loop exceeds caps
- breaker logic not respected
