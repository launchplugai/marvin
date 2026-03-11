# Document 10 of 10: INTEGRATION PLUMBING
## How Marvin Modules Connect to BetApp

**Principle:** Every pipe has two ends. This document defines both ends for every integration point between the Marvin repo and the BetApp repo. If you can't trace a data flow from Marvin module to BetApp screen, the pipe isn't connected — it's just sitting in the yard.

---

## 0. THE TWO REPOS

| Repo | What it is | Where it runs |
|------|-----------|---------------|
| `launchplugai/marvin` | LLM routing engine + protocol definitions + context system | VPS (planned), currently library-only |
| `launchplugai/BetApp` | FastAPI web app + DNA evaluation engine + UI | VPS container `:19801` |

**Current state:** These repos are *not* connected at runtime. Marvin has modules. BetApp has a pipeline. The plumbing between them is not laid yet. This document is the plumbing diagram.

---

## 1. INTEGRATION MAP

```
MARVIN REPO                           BETAPP REPO
===========                           ===========

src/protocol_engine/        ------>   dna-matrix/core/protocols/
  models.py (ProtocolSignal)            pipeline.py (BetApp's own)
  runner.py (ProtocolRunner)            registry.py
  loader.py (PDC loader)               artifact_mapper.py
  evaluators/*.py                       physical.py, tactical.py, ...

protocols/pdc.json          ------>   protocols/registry.json
  (3 protocols, v1)                     (13 protocols, full)

src/context/                ------>   context/
  capture.py                            service.py
  compressor.py                         apply.py
  hydrator.py                           snapshot.py
  synthesizer.py                        providers/nba_availability.py
  sync.py --------[HTTP]------->   marvin-skills container

src/cache/                  ------>   (no equivalent in BetApp)
  cache.py                              BetApp has its own caching
  key_generator.py                      (odds cache, analytics cache)

src/lobby/                  ------>   (not used by BetApp)
  classifier.py                         BetApp doesn't route to LLMs

src/rate_limiter/           ------>   (not used by BetApp)
  tracker.py                            BetApp doesn't call external LLMs
  headers.py
```

---

## 2. PIPE-BY-PIPE DETAIL

### PIPE 1: Protocol Engine

**Marvin side:** `src/protocol_engine/` — 3 evaluators (fatigue_b2b, pace_shock, lineup_instability), PDC loader, runner, artifact mapper. 47 tests passing.

**BetApp side:** `dna-matrix/core/protocols/` — 13 protocols across 5 categories, its own registry, pipeline, artifact mapper. Status: UNKNOWN (pipeline stage 17 marked UNKNOWN in SRM).

**The gap:**
- Marvin's protocol engine was built as a *reference implementation* — clean, tested, well-specced.
- BetApp has its own protocol engine that evolved independently with 13 protocols.
- These are **two separate implementations** of the same concept.

**Resolution options (pick one):**

| Option | Description | Risk |
|--------|------------|------|
| A. Replace | Swap BetApp's protocol engine with Marvin's. Port the 10 missing protocols to Marvin's evaluator format. | High — BetApp's pipeline expects its own protocol shapes |
| B. Align | Keep both, but make Marvin's PDC format the spec. Validate BetApp's registry.json against Marvin's schema. | Medium — two codebases to maintain |
| C. Extract | Pull protocol engine into a shared package (`marvin-protocols`). Both repos import it. | Best long-term, most work now |

**Recommended:** Option B for now. Validate alignment, don't rewrite.

**Verification test:**
```bash
# Does BetApp's registry match Marvin's PDC schema?
python -c "
import json
betapp_reg = json.load(open('path/to/BetApp/protocols/registry.json'))
marvin_pdc = json.load(open('protocols/pdc.json'))
# Compare: do they share protocol IDs, field names, impact shapes?
"
```

---

### PIPE 2: Protocol Data -> UI

**Source:** BetApp pipeline stage 17 (protocol_engine) output
**Sink:** UI screen 2.7 (Protocol View) from `09-ui-schematics.md`

**The contract that must match:**

Pipeline output shape (BetApp side):
```python
# What the pipeline SHOULD return after protocol stage
{
    "triggeredProtocols": [
        {
            "protocolId": str,
            "name": str,
            "category": str,
            "impact": {"type": str, "value": float, "domain": str},
            "evidence": {...},
            "artifacts": {...},
            "tierRequired": str
        }
    ],
    "aggregateImpact": {
        "stabilityModifier": float,
        "fragilityDelta": float
    },
    "dnaMode": str
}
```

UI contract shape (from `09-ui-schematics.md` Section 2.7):
```json
{
    "protocols": [...],
    "aggregate": {"stability_modifier": float, "fragility_delta": float},
    "dna_mode": str
}
```

**Known mismatch:** BetApp uses camelCase (`triggeredProtocols`, `protocolId`). Marvin/UI spec uses snake_case. The `ui_contract_v1.py` in BetApp is supposed to normalize this. **Must verify.**

---

### PIPE 3: Context System

**Marvin side:** `src/context/` — capture, compress, synthesize, hydrate, sync. Full pipeline for conversation context management.

**BetApp side:** `context/` — service, apply, snapshot, providers. Game/injury context for evaluations.

**These are different things with the same name:**
- Marvin's context = *conversation* context (what Claude said in previous sessions)
- BetApp's context = *game* context (injuries, availability, rest days)

**No integration needed.** These modules solve different problems. The naming collision is confusing but harmless.

---

### PIPE 4: Context Sync to VPS

**Marvin side:** `src/context/sync.py` → pushes context blocks/threads to marvin-skills
**VPS side:** `marvin-skills` container on `:19800`

**Status:** marvin-skills container is running on VPS. sync.py targets `http://187.77.211.80:19800/context/sync`.

**Verification:**
```bash
curl -s http://187.77.211.80:19800/health
# Should return 200 if marvin-skills is alive
```

**This pipe is Marvin-internal.** BetApp doesn't consume it. It's for Oracle continuity.

---

### PIPE 5: Cache / Lobby / Rate Limiter

**Marvin side:** `src/cache/`, `src/lobby/`, `src/rate_limiter/`

**BetApp side:** None. BetApp doesn't use Marvin's LLM routing.

**These modules exist for Marvin's own LLM routing pipeline (Phases 2-4).** They have no BetApp integration point. They're solid (47 tests) and ready for when Marvin's receptionist/department heads go live — but that's a separate workstream from BetApp UI.

---

## 3. WHAT'S ACTUALLY CONNECTED TODAY

| Pipe | Marvin End | BetApp End | Connected? |
|------|-----------|-----------|------------|
| Protocol Engine | `src/protocol_engine/` | `dna-matrix/core/protocols/` | NO — parallel implementations |
| Protocol -> UI | N/A | pipeline stage 17 -> web template | UNKNOWN — stage 17 status UNKNOWN |
| Conversation Context | `src/context/` | N/A | N/A — different domain |
| Context Sync | `src/context/sync.py` | `marvin-skills:19800` | UNKNOWN — needs health check |
| Cache | `src/cache/` | N/A | N/A — Marvin-internal |
| Lobby | `src/lobby/` | N/A | N/A — Marvin-internal |
| Rate Limiter | `src/rate_limiter/` | N/A | N/A — Marvin-internal |

**Honest answer: nothing is connected between the two repos at runtime today.** Marvin is a standalone library. BetApp is a standalone app. The PDC format in Marvin *could* be the source of truth for BetApp's protocols, but that pipe hasn't been laid.

---

## 4. PLUMBING PLAN (ordered by value)

### Layer 0: Verify what BetApp actually has
- Run the curl proofs from `09-ui-schematics.md` Section 5
- Specifically test pipeline stage 17 (protocol engine)
- Confirm `ui_contract_v1.py` output shape

### Layer 1: Align protocol schemas
- Compare `protocols/pdc.json` (Marvin) with `protocols/registry.json` (BetApp)
- Document mismatches
- Decide: Option A (replace), B (align), or C (extract)

### Layer 2: Wire protocol data to UI
- Ensure pipeline returns `triggeredProtocols` in evaluation response
- Ensure `ui_contract_v1.py` normalizes to the shape in `09-ui-schematics.md` Section 2.5
- Build Protocol screen (S6) against verified contract

### Layer 3: PDC as source of truth
- If Option B: BetApp's registry.json validates against Marvin's PDC schema
- If Option C: Extract shared package, both repos depend on it
- New protocols get added to Marvin first (tested), then deployed to BetApp

### Layer 4: Context sync verification
- Confirm marvin-skills health endpoint
- Confirm sync.py successfully pushes
- This is Oracle infrastructure, not BetApp integration

---

## 5. WHAT NOT TO CONNECT

Some things should stay separate:

| Module | Why it stays separate |
|--------|----------------------|
| Marvin cache | BetApp has its own caching (odds, analytics). Different cache keys, different TTLs, different invalidation. |
| Marvin lobby | BetApp doesn't route to multiple LLMs. It has one pipeline. |
| Marvin rate limiter | BetApp doesn't call external LLM APIs (it IS the API). |
| Marvin conversation context | BetApp game context is a different domain entirely. |

**Don't force connections where there aren't any.** Marvin and BetApp share protocol concepts and infrastructure. That's it. The rest of Marvin is for Marvin's own Phase 2-4 routing engine.
