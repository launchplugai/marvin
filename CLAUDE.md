# Marvin — Initialization Cascade

> **READ THIS FIRST. This is the only file you need to start.**
> Everything flows from here. No guessing, no searching.

---

## 0. WHO ARE YOU?

Run this decision tree **immediately** — before reading anything else:

```
/vault/.keys.enc exists?
  YES → You are THE ORACLE (VPS container). Go to Section A.
  NO  →
    .env exists in repo root?
      YES → You are a REMOTE CONTROL with credentials. Go to Section B.
      NO  →
        .env.example exists?
          YES → You are a COLD START. Tell the user:
                "Copy .env.example to .env and fill in HOSTINGER_API_TOKEN and GH_TOKEN."
                You can still work on the codebase. You cannot manage the VPS. Go to Section C.
          NO  → You are LOCAL ONLY. Work on the codebase. Go to Section C.
```

**The rule:** There is exactly ONE Oracle (the dockerized Claude on the VPS). Every other Claude instance — chat sessions, local CLI, web sessions — is a **Remote Control**. Remote Controls talk to the Oracle, they don't try to be it.

---

## A. YOU ARE THE ORACLE

You are Claude Code running inside `claude-hub` on the Hostinger VPS (187.77.211.80).
You are the persistent, always-on brain. You have:

- Direct filesystem access to all repos at `/root/projects/`
- Tokens loaded from `/vault/.keys.enc` ($ANTHROPIC_API_KEY, $GH_TOKEN)
- Access to Ollama on localhost:11434
- Network access to all containers (host network mode)
- tmux session with watchdog (auto-restart)

**Your job:** Execute. You own the codebase, the containers, and the deployment.
When Remote Controls send instructions, you carry them out.

**Key paths:**
- Repos: `/root/projects/{marvin, claude-hub, BetApp}`
- Vault: `/vault/` (read-only — update via key-locker redeploy)
- Memory: synced from vault on boot

**Skip to Section 1 for system architecture.**

---

## B. YOU ARE A REMOTE CONTROL

You are an ephemeral Claude session (chat, local CLI, or web).
You have tokens in `.env` and can manage the VPS via the Hostinger REST API.

**Your capabilities:**
- Read/write code in this repo
- Manage VPS containers via Hostinger API (deploy, restart, logs)
- Push code to GitHub for the Oracle to pick up
- Issue commands to the Oracle via remote control

**Initialization:**
```bash
source .env  # loads HOSTINGER_API_TOKEN, GH_TOKEN, etc.
```

**Verify VPS is alive:**
```bash
curl -s -H "Authorization: Bearer $HOSTINGER_API_TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker" \
  | python3 -m json.tool
```

**Available slash commands:** `/bootstrap`, `/vps-status`, `/vps-logs`, `/vps-deploy`, `/vault-update`

**Skip to Section 1 for system architecture.**

---

## C. YOU ARE LOCAL ONLY

No VPS access. Work on the codebase:
- Run tests: `python -m pytest tests/ -v`
- Read architecture: `docs/designs/` (8 design docs)
- Read decisions: `docs/ADRs/` (architecture decision records)

**Skip to Section 1 for system architecture.**

---

## 1. WHAT IS MARVIN

Marvin is a multi-agent LLM routing engine. It sits between the user and multiple LLM APIs, routing requests to the cheapest model that can handle them.

```
User Message
    ↓
LOBBY (Groq 8B) — classifies intent             ← src/lobby/
    ↓
CACHE (SQLite) — returns cached if hit           ← src/cache/
    ↓
RATE LIMITER — checks provider health            ← src/rate_limiter/
    ↓
RECEPTIONIST (Haiku) — routes to department      ← Phase 2
    ↓
DEPARTMENT HEAD (Kimi 2.5) — does the work       ← Phase 3
    ↓
BOSS → EMERGENCY (escalation)                    ← Phase 4
```

**Execution waterfall:** Groq (free) → Kimi 2.5 → Haiku → Boss → Opus (last resort)
**Budget:** $100/month — Groq $0, Haiku $20, Kimi $60, Sonnet $15, Opus $5

### Phase Status

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | Cache + Lobby + Rate Limiter | **COMPLETE** — 47 tests passing |
| Phase 2 | Receptionist + Dispatch | Pending |
| Phase 3 | Department Heads (Ralph/Ira/Tess) | Pending |
| Phase 4 | Boss + Emergency + Hardening | Pending |

---

## 2. CODEBASE MAP

```
src/
├── cache/
│   ├── cache.py             # SQLite cache with TTL, metrics, invalidation
│   ├── key_generator.py     # State-aware cache key generation (git state)
│   ├── git_invalidation.py  # Post-commit hook → clear stale cache
│   └── schema.sql           # Full DB schema (cache, metrics, rate limits, envelopes)
├── lobby/
│   └── classifier.py        # Groq 8B intent classifier (keyword → LLM → fallback)
└── rate_limiter/
    ├── headers.py            # Parse rate limit headers from all providers
    └── tracker.py            # Health tracking, fallback selection, priority diversion

docs/
├── designs/                  # 8 architecture documents (the blueprints)
│   ├── 01-transmission.md   # Request envelope protocol
│   ├── 02-cache-layer.md    # Cache architecture & schema
│   ├── 03-lobby.md          # Intent classifier design
│   ├── 04-receptionist.md   # Haiku routing logic
│   ├── 05-departments.md    # Ralph/Ira/Tess agent specs
│   ├── 06-rate-limiter.md   # Health monitor & fallback chains
│   ├── 07-boss-emergency.md # Escalation & arbitration
│   └── 08-build-plan.md     # Phased construction timeline
└── ADRs/                     # Architecture decision records

tests/unit/                   # pytest suite (47 tests)
infra/                        # Docker compose, entrypoint, bootstrap scripts
```

---

## 3. VPS INFRASTRUCTURE

### Server: Hostinger KVM 2
- **IP:** 187.77.211.80 | **VM ID:** 1405440
- **OS:** Ubuntu 24.04 + Docker | **RAM:** 8 GB | **Disk:** 100 GB
- **API:** `https://developers.hostinger.com/api/vps/v1`

### Containers

| Container | Purpose | State | Access |
|-----------|---------|-------|--------|
| `claude-hub` | The Oracle — Claude Code in tmux | running | host network |
| `key-locker` | Vault provisioner (run-once) | exited | — |
| `marvin-skills` | HTTP probe server | running | :19800 |
| `ollama-wmf4` | Local LLM | healthy | 127.0.0.1:11434 |
| `openclaw-quzk` | Hostinger mgmt agent | running | 127.0.0.1:46282 |

### API Quick Reference

| Action | Call |
|--------|------|
| List containers | `GET /virtual-machines/1405440/docker` |
| Container logs | `GET /virtual-machines/1405440/docker/{name}/logs` |
| Restart | `POST /virtual-machines/1405440/docker/{name}/restart` |
| Deploy | `POST /virtual-machines/1405440/docker` body: `{project_name, content}` |
| Update compose | `POST /virtual-machines/1405440/docker/{name}/update` body: `{content}` |
| Delete | `DELETE /virtual-machines/1405440/docker/{name}/down` |

**Auth:** `Authorization: Bearer $HOSTINGER_API_TOKEN`
**Compose limit:** 8192 chars max.

---

## 4. TOKENS & SECRETS

| Context | Hostinger API Token | GitHub Token |
|---------|---------------------|--------------|
| VPS (Oracle) | `$ANTHROPIC_API_KEY` from vault | `$GH_TOKEN` from vault |
| Remote Control | `$HOSTINGER_API_TOKEN` from `.env` | `$GH_TOKEN` from `.env` |
| Vault (source) | `/vault/.keys.enc` | `/vault/.keys.enc` |

The Hostinger API token is stored as `ANTHROPIC_API_KEY` on the VPS for historical reasons.
In `.env` it's called `HOSTINGER_API_TOKEN`. Same value.

---

## 5. DEEP DIVES (read when needed, not upfront)

| Document | When to read it |
|----------|-----------------|
| `hub-card.md` | VPS boot sequence, volume architecture, failure recovery |
| `CHAT_PACKAGE.md` | Full context dump (BetApp, DNA engine, Claude Hub details) |
| `docs/designs/*.md` | Building new modules — the architectural blueprints |
| `docs/ADRs/*.md` | Understanding past decisions and constraints |
| `PRD-openclaw-marvin.md` | Product requirements, agent specs, budget model |
| `SIM_OFFICE_BUILD_PLAN_v1.md` | Sims engine (Layers 2-7): life, growth, relationships |

---

## 6. CONSTRAINTS

- Docker compose limit: **8192 characters** (Hostinger API)
- Container memory: **4 GB** (claude-hub)
- No SSH — Docker-only management via Hostinger API
- Vault is **read-only** from claude-hub
- Ollama/OpenClaw bind to localhost only
- claude-hub uses `network_mode: host` — reaches all local services
