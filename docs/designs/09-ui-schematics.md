# Document 9 of 10: UI SCHEMATICS
## Ground-Truth Screen Architecture for BetApp

**Principle:** Sand to studs. Every screen spec here starts from what the API *actually returns*, not what we wish it returned. No screen gets built until its data contract is verified against the live endpoint. If an endpoint returns placeholder data, the screen spec says so and the screen stays blocked.

**Repo boundary:** BetApp UI code lives in `launchplugai/BetApp`. This document is the *blueprint* that BetApp code must conform to. Marvin modules (protocol engine, context, cache) feed data into BetApp's pipeline — their integration points are defined in `10-integration-plumbing.md`.

---

## 0. VERIFICATION STATUS

Before building anything, each data source gets one of three stamps:

| Stamp | Meaning | Action |
|-------|---------|--------|
| VERIFIED | Endpoint tested, returns real structured data | Build the screen |
| PLACEHOLDER | Endpoint exists but returns mock/empty/hardcoded data | Fix the endpoint first |
| MISSING | No endpoint exists | Build the endpoint first |

**Nothing gets a "WORKING" label without a curl proof.**

---

## 1. SCREEN MAP

```
                    +------------------+
                    |    LANDING (/)   |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   AUTH (/auth)   |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
    +---------v--+  +--------v---+  +-------v------+
    | DASHBOARD  |  |   BROWSE   |  |   HISTORY    |
    | (/app)     |  | (/browse)  |  | (/history)   |
    +-----+------+  +-----+-----+  +--------------+
          |              |
          |         +----v-------+
          +-------->|  BUILDER   |
                    | (/builder) |
                    +-----+------+
                          |
                    +-----v------+
                    |  PROTOCOL  |    <-- S6: Does not exist yet
                    | (/protocol)|
                    +-----+------+
                          |
                    +-----v------+
                    |  RESULT    |    <-- Post-evaluation view
                    | (inline)   |
                    +------------+

    SIDE PANELS (overlay, not full screens):
    - Notifications (/notifications)
    - Onboarding (first-visit flow)
    - Admin (/admin) — internal only
```

---

## 2. SCREEN SPECS

### 2.1 LANDING

| Field | Value |
|-------|-------|
| Route | `GET /` |
| Purpose | Entry point. Redirects authed users to dashboard, unauthed to auth. |
| Data needed | Auth state only (JWT in cookie/header) |
| Verification | VERIFIED — just a redirect, no data contract |

**Layout:** None. Pure redirect.

---

### 2.2 AUTH

| Field | Value |
|-------|-------|
| Route | `GET /app?screen=auth` |
| Purpose | Login + registration |
| API calls | `POST /api/auth/login`, `POST /api/auth/register` |
| Verification | **NEEDS PROOF** — are auth endpoints returning real JWTs or stubs? |

**Layout zones:**
```
+-------------------------------+
|          LOGO / BRAND         |
+-------------------------------+
|   [Login] tab  [Register] tab |
+-------------------------------+
|   Email:    [____________]    |
|   Password: [____________]    |
|                               |
|   [ Submit ]                  |
|                               |
|   Tier badge: FREE / PRO     |
+-------------------------------+
```

**States:**
- Default: Login form
- Error: Invalid credentials message
- Loading: Submit disabled, spinner
- Success: Redirect to dashboard

**Data contract (response from /api/auth/login):**
```json
{
  "token": "jwt_string",
  "user": {
    "id": "uuid",
    "email": "string",
    "tier": "FREE | PRO | ELITE",
    "created_at": "iso_datetime"
  }
}
```

---

### 2.3 DASHBOARD

| Field | Value |
|-------|-------|
| Route | `GET /app?screen=dashboard` |
| Purpose | Home screen. Active bets, recent evaluations, quick stats. |
| API calls | `GET /api/bets/history`, `GET /history`, `GET /health` |
| Verification | **NEEDS PROOF** — what does /api/bets/history actually return? |

**Layout zones:**
```
+-------------------------------+
|  NAV: [Dashboard] [Browse]    |
|       [Builder]  [History]    |
+-------------------------------+
|  STATS ROW                    |
|  [Bets Today] [Win Rate]     |
|  [Active Bets] [Tier]        |
+-------------------------------+
|  RECENT EVALUATIONS           |
|  +---------------------------+|
|  | Parlay summary | Grade   ||
|  | Parlay summary | Grade   ||
|  | Parlay summary | Grade   ||
|  +---------------------------+|
+-------------------------------+
|  ACTIVE BETS                  |
|  +---------------------------+|
|  | Bet | Status | Outcome   ||
|  +---------------------------+|
+-------------------------------+
```

**Data contract (what the UI needs):**
```json
{
  "stats": {
    "bets_today": "number",
    "win_rate": "number (0-1)",
    "active_count": "number",
    "tier": "FREE | PRO | ELITE"
  },
  "recent_evaluations": [
    {
      "id": "string",
      "input_summary": "string (truncated parlay text)",
      "grade": "string (A-F or numeric)",
      "risk_level": "string",
      "created_at": "iso_datetime",
      "leg_count": "number"
    }
  ],
  "active_bets": [
    {
      "id": "string",
      "summary": "string",
      "status": "active | settled | voided",
      "outcome": "win | loss | pending | push"
    }
  ]
}
```

---

### 2.4 BROWSE

| Field | Value |
|-------|-------|
| Route | `GET /app?screen=browse` |
| Purpose | Browse today's games with odds. Pick games to build parlays. |
| API calls | `GET /api/v1/odds/sports`, `GET /api/v1/odds/games`, `GET /api/nba/games/today` |
| Verification | **NEEDS PROOF** — odds endpoint requires ODDS_API_KEY. Is it configured? |

**Layout zones:**
```
+-------------------------------+
|  SPORT FILTER                 |
|  [NBA] [NFL] [NHL] [MLB] ... |
+-------------------------------+
|  TODAY'S GAMES                |
|  +---------------------------+|
|  | Team A vs Team B          ||
|  | Time | Spread | O/U       ||
|  | [ Add to Builder ]        ||
|  +---------------------------+|
|  | Team C vs Team D          ||
|  | ...                        ||
+-------------------------------+
```

**Data contract (per game):**
```json
{
  "game_id": "string",
  "sport": "string",
  "home_team": "string",
  "away_team": "string",
  "commence_time": "iso_datetime",
  "odds": {
    "spread": { "home": "number", "away": "number" },
    "moneyline": { "home": "number", "away": "number" },
    "total": { "over": "number", "under": "number", "line": "number" }
  },
  "context": {
    "injuries": ["string"],
    "rest_days": "number | null",
    "edge_summary": "string | null"
  }
}
```

**Blocker:** If ODDS_API_KEY is not set, this screen shows stale/mock data. Must verify before shipping.

---

### 2.5 BUILDER

| Field | Value |
|-------|-------|
| Route | `GET /app?screen=builder` |
| Purpose | Core screen. Build a parlay, submit for evaluation. |
| API calls | `POST /leading-light/evaluate/text`, `POST /app/evaluate` |
| Verification | **NEEDS PROOF** — does evaluate return full pipeline output or stubs? |

**Layout zones:**
```
+-------------------------------+
|  PARLAY INPUT                 |
|  +---------------------------+|
|  | Free text input area      ||
|  | (paste bet slip text)     ||
|  |                           ||
|  | --OR-- selected legs:     ||
|  | [x] Game A - Team A ML    ||
|  | [x] Game B - Over 220.5   ||
|  +---------------------------+|
|                               |
|  TIER SELECTOR                |
|  ( ) FREE  ( ) PRO  ( ) ELITE|
|                               |
|  [ Evaluate Parlay ]          |
+-------------------------------+
|  RESULT (appears after eval)  |
|  +---------------------------+|
|  | GRADE: B+                 ||
|  | RISK: MODERATE            ||
|  |                           ||
|  | LEG BREAKDOWN:            ||
|  | Leg 1: Team A ML  [B]    ||
|  | Leg 2: Over 220.5 [C+]   ||
|  |                           ||
|  | CORRELATION: 0.34         ||
|  | DNA VERDICT: PROCEED      ||
|  |                           ||
|  | SHERLOCK SAYS:            ||
|  | "The over bet conflicts..."||
|  |                           ||
|  | PROTOCOLS TRIGGERED: (S6) ||
|  | [fatigue_b2b] [pace_shock]||
|  +---------------------------+|
+-------------------------------+
```

**Data contract (evaluation response — the big one):**

This is what `ui_contract_v1.py` in BetApp must enforce. The UI renders exactly this shape:

```json
{
  "evaluation_id": "string",
  "grade": "string",
  "risk_level": "LOW | MODERATE | HIGH | EXTREME",
  "confidence": "number (0-1)",

  "legs": [
    {
      "description": "string",
      "grade": "string",
      "risk": "string",
      "notes": "string"
    }
  ],

  "correlation": {
    "score": "number (0-1)",
    "correlated_pairs": [["leg_index", "leg_index"]],
    "explanation": "string"
  },

  "dna_verdict": {
    "action": "PROCEED | CAUTION | REJECT",
    "rules_triggered": ["string"],
    "explanation": "string"
  },

  "sherlock": {
    "summary": "string (plain English explanation)",
    "audit_trail": ["string"]
  },

  "protocols_triggered": [
    {
      "protocol_id": "string",
      "name": "string",
      "category": "physical | tactical | volatility | psychological | market",
      "impact": {
        "type": "string",
        "value": "number",
        "explanation": "string"
      },
      "tier_required": "PRO | ELITE"
    }
  ],

  "delta": {
    "previous_grade": "string | null",
    "grade_change": "string | null",
    "confidence_trend": "up | down | stable | null"
  },

  "grounding_score": "number (0-1)",
  "tier_used": "FREE | PRO | ELITE",
  "created_at": "iso_datetime"
}
```

**This is the contract.** If the pipeline doesn't return this shape, the UI breaks. If the UI expects fields not in this shape, the UI is wrong.

---

### 2.6 HISTORY

| Field | Value |
|-------|-------|
| Route | `GET /app?screen=history` |
| Purpose | Past evaluations. Searchable, filterable. |
| API calls | `GET /history` |
| Verification | **NEEDS PROOF** |

**Layout zones:**
```
+-------------------------------+
|  FILTERS                      |
|  [Date range] [Sport] [Grade] |
+-------------------------------+
|  EVALUATION LIST              |
|  +---------------------------+|
|  | Date | Input | Grade | Risk|
|  | Date | Input | Grade | Risk|
|  | Date | Input | Grade | Risk|
|  +---------------------------+|
|  [ Load More ]                |
+-------------------------------+
```

**Data contract:** Array of evaluation summaries (same shape as dashboard `recent_evaluations`, paginated).

---

### 2.7 PROTOCOL (S6 — NOT BUILT)

| Field | Value |
|-------|-------|
| Route | `GET /app?screen=protocol` |
| Purpose | Deep dive into triggered protocols for an evaluation. |
| API calls | `GET /api/protocols`, `GET /api/protocols/{id}` |
| Verification | **MISSING** — screen does not exist. Endpoint status UNKNOWN. |
| Prerequisite | S4 (Protocol Engine Functional) and S5 (Protocol Toggle) |

**Layout zones:**
```
+-------------------------------+
|  EVALUATION HEADER            |
|  Parlay: "Lakers ML + Over"  |
|  Grade: B+ | Risk: MODERATE  |
+-------------------------------+
|  TRIGGERED PROTOCOLS          |
|  +---------------------------+|
|  | [PHYSICAL] fatigue_b2b    ||
|  | Impact: -0.12 stability   ||
|  | Evidence: LAL played last  ||
|  | night, 18h rest, 600mi    ||
|  | travel                    ||
|  |                           ||
|  | Sherlock: "The Lakers are ||
|  | on the second night of a  ||
|  | back-to-back after flying ||
|  | from Denver..."           ||
|  +---------------------------+|
|  | [TACTICAL] pace_shock     ||
|  | Impact: -0.10 stability   ||
|  | Evidence: pace diff 6.2,  ||
|  | rank diff 12              ||
|  +---------------------------+|
+-------------------------------+
|  AGGREGATE IMPACT             |
|  Stability modifier: -0.22   |
|  Fragility delta: +0.00      |
+-------------------------------+
|  DNA MODE                     |
|  [CORE_ONLY] vs              |
|  [CORE_PLUS_PROTOCOLS]       |
|  Shadow comparison: ...       |
+-------------------------------+
```

**Data contract (protocol detail):**
```json
{
  "evaluation_id": "string",
  "protocols": [
    {
      "protocol_id": "string",
      "name": "string",
      "version": "string",
      "category": "string",
      "tier_required": "PRO | ELITE",
      "triggered": true,
      "impact": {
        "type": "stability_modifier | fragility_delta",
        "mode": "additive | multiplicative",
        "value": "number",
        "domain": "string"
      },
      "evidence": {
        "inputs_used": {},
        "thresholds_exceeded": {},
        "explanation": "string"
      },
      "artifacts": {
        "evidence": "string",
        "weight": "number",
        "audit_note": "string",
        "constraint": "string | null"
      }
    }
  ],
  "aggregate": {
    "stability_modifier": "number",
    "fragility_delta": "number"
  },
  "dna_mode": "CORE_ONLY | CORE_PLUS_PROTOCOLS",
  "shadow_comparison": {}
}
```

**This screen is the S6 deliverable.** It cannot be built until:
1. Protocol engine is integrated into BetApp pipeline (S4)
2. Protocol toggle is wired (S5)
3. The above data contract is verified against real pipeline output

---

### 2.8 NOTIFICATIONS (Side Panel)

| Field | Value |
|-------|-------|
| Route | `GET /app?screen=notifications` |
| Purpose | Alert feed — opportunity alerts, system notices. |
| API calls | `GET /api/notifications` |
| Verification | **NEEDS PROOF** |

**Layout:** Slide-out panel with notification cards. Each card: title, body, timestamp, read/dismiss actions.

---

### 2.9 ONBOARDING (Overlay)

| Field | Value |
|-------|-------|
| Route | First-visit detection (localStorage flag or user.onboarded field) |
| Purpose | Walk new users through the app. |
| Verification | **NEEDS PROOF** — is this just HTML or does it hit an API? |

**Layout:** Step-through modal. 3-4 steps explaining Browse > Build > Evaluate > Track.

---

### 2.10 ADMIN (Internal)

| Field | Value |
|-------|-------|
| Route | `GET /admin` |
| Purpose | Config, reports, cache mgmt, NBA sync. |
| API calls | `GET /api/admin/config`, `GET /api/admin/report/super`, etc. |
| Verification | **NEEDS PROOF** |

Not user-facing. Lower priority. Spec deferred until S8+.

---

## 3. SHARED COMPONENTS

These appear across multiple screens:

### 3.1 Navigation Bar
- Tabs: Dashboard, Browse, Builder, History
- User avatar + tier badge
- Notification bell (count badge)

### 3.2 Evaluation Card (compact)
Used in: Dashboard (recent), History (list)
```
+---------------------------+
| Input summary (truncated) |
| Grade: B+ | Risk: MOD     |
| 3 legs | 2 protocols      |
| 2 minutes ago             |
+---------------------------+
```

### 3.3 Leg Row
Used in: Builder (result), Protocol (context)
```
| Leg description | Grade | Risk | Notes |
```

### 3.4 Protocol Badge
Used in: Builder (result), Protocol (list)
```
[CATEGORY] protocol_name — impact_value
```

### 3.5 Tier Gate
Used in: Builder (pro features), Protocol (elite protocols)
```
+---------------------------+
| This feature requires PRO |
| [ Upgrade ]               |
+---------------------------+
```
Wraps any UI element that requires a higher tier. Checks `user.tier` against `tier_required`.

---

## 4. USER FLOWS

### 4.1 Primary Flow: Evaluate a Parlay

```
Landing → Auth (if needed) → Dashboard → Builder → [type parlay] → Evaluate
  → Result (inline) → Protocol deep-dive (S6)
  → History (saved)
```

### 4.2 Browse-to-Build Flow

```
Dashboard → Browse → [select games] → Builder (legs pre-filled) → Evaluate
```

### 4.3 Repeat Evaluation Flow

```
History → [select past eval] → Builder (pre-filled) → Re-evaluate
```

---

## 5. VERIFICATION CHECKLIST

Before any screen gets code, run these proofs:

| Screen | Proof Command | Expected |
|--------|---------------|----------|
| Auth | `curl -X POST http://187.77.211.80:19801/api/auth/login -d '{"email":"test@test.com","password":"test"}'` | JWT token + user object |
| Dashboard | `curl http://187.77.211.80:19801/api/bets/history` | Array of bet objects |
| Browse | `curl http://187.77.211.80:19801/api/v1/odds/games` | Array of game objects with odds |
| Builder | `curl -X POST http://187.77.211.80:19801/leading-light/evaluate/text -d '{"input":"Lakers ML + Warriors Over 220.5","tier":"FREE"}'` | Full evaluation response |
| History | `curl http://187.77.211.80:19801/history` | Paginated evaluation list |
| Protocol | `curl http://187.77.211.80:19801/api/protocols` | Protocol registry |
| Notifications | `curl http://187.77.211.80:19801/api/notifications` | Notification array |
| Admin | `curl http://187.77.211.80:19801/api/admin/config` | Config object |

**Rule:** If a curl returns 404, 500, or placeholder data — that screen is BLOCKED. Fix the API first.

---

## 6. BUILD ORDER

Sand down, then build up. Each layer proves itself before the next starts.

```
Layer 0: VERIFY ENDPOINTS        ← Run Section 5 checklist
  |
Layer 1: AUTH + LANDING           ← Gate everything behind login
  |
Layer 2: BUILDER (core screen)   ← The product IS evaluation
  |
Layer 3: DASHBOARD + HISTORY     ← Show what you've built
  |
Layer 4: BROWSE                  ← Requires live odds (ODDS_API_KEY)
  |
Layer 5: PROTOCOL (S6)           ← Requires S4 + S5 complete
  |
Layer 6: NOTIFICATIONS           ← Nice-to-have, not core
  |
Layer 7: ONBOARDING + POLISH     ← Last coat of paint
```

**Each layer ships independently.** Layer 2 (Builder) is the product. If we stop there, we still have something useful.

---

## 7. ANTI-PATTERNS (what we're sanding away)

1. **"WORKING" without proof.** The SRM labels 10 screens as WORKING. None have curl proofs attached. From this point forward: no label without evidence.

2. **Screen before data.** Browse screen exists but ODDS_API_KEY status is unknown. The screen might render empty or with mock data. Verify the data source before touching the screen.

3. **Monolith HTML.** Mission Control is 36KB of inline HTML/CSS/JS. If we add more screens this way, we get an unmaintainable blob. BetApp should use Jinja2 templates with shared base + blocks.

4. **No component reuse.** Evaluation cards appear on Dashboard and History but are likely copy-pasted. Extract shared components.

5. **Protocol UI designed without protocol data.** S6 (Protocol View) has a checkpoint but no spec for what the protocol engine actually returns. This doc (Section 2.7) is that missing spec.
