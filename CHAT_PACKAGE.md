# Chat Package — Marvin System (Non-Bootstrapped Session)

> **Version:** 1.0 | **Date:** 2026-03-03
> **Purpose:** Full context transfer for any model/session that needs to operate on this system without the VPS bootstrap.

---

## 1. SYSTEM OVERVIEW

This system has three components:

| Component | Repo | Purpose | Live URL |
|-----------|------|---------|----------|
| **Marvin Core** | `launchplugai/marvin` | Multi-agent LLM routing engine | Not deployed yet |
| **DNA Bet Engine (BetApp)** | `launchplugai/BetApp` | Sports parlay evaluation app | `http://187.77.211.80:19801` (VPS) |
| **Claude Hub** | `launchplugai/claude-hub` | VPS container infrastructure | Running on `187.77.211.80` |

---

## 2. VPS ACCESS

### Server
- **Provider:** Hostinger KVM 2 (2 CPU, 8 GB RAM, 100 GB disk)
- **IP:** `187.77.211.80`
- **VM ID:** `1405440`
- **OS:** Ubuntu 24.04 + Docker
- **API Base:** `https://developers.hostinger.com/api/vps/v1`
- **Auth:** `Authorization: Bearer <HOSTINGER_API_TOKEN>`

### Quick Health Check
```bash
# List all Docker containers
curl -s -H "Authorization: Bearer $HOSTINGER_API_TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker"

# Get container logs
curl -s -H "Authorization: Bearer $HOSTINGER_API_TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/{project_name}/logs"
```

### Running Docker Containers

| Container | Image | Purpose | Ports |
|-----------|-------|---------|-------|
| `betapp` | python:3.12-slim | DNA Bet Engine (FastAPI/Uvicorn) | :19801 |
| `claude-hub` | node:20-bookworm | Claude Code running in tmux, host network | host |
| `ollama-wmf4` | ollama/ollama | Local LLM inference | 127.0.0.1:11434 |
| `marvin-skills` | node:20-slim | HTTP probe server | :19800 |
| `openclaw-quzk` | ghcr.io/hostinger/hvps-openclaw | Hostinger management agent | 127.0.0.1:46282 |
| `key-locker` | alpine:3.19 | One-shot vault provisioner (exited) | — |

### Container Management API

| Action | Method | Path |
|--------|--------|------|
| List projects | GET | `/virtual-machines/1405440/docker` |
| Get compose | GET | `/virtual-machines/1405440/docker/{name}` |
| Get logs | GET | `/virtual-machines/1405440/docker/{name}/logs` |
| Restart | POST | `/virtual-machines/1405440/docker/{name}/restart` |
| Start/Stop | POST | `/virtual-machines/1405440/docker/{name}/start` or `/stop` |
| Create project | POST | `/virtual-machines/1405440/docker` |
| Delete project | DELETE | `/virtual-machines/1405440/docker/{name}/down` |

---

## 3. TOKEN & SECRET MANAGEMENT

### Where Tokens Live

| Context | Hostinger API Token | GitHub Token |
|---------|---------------------|--------------|
| VPS (claude-hub) | `$ANTHROPIC_API_KEY` env var | `$GH_TOKEN` env var |
| Local / .env | `$HOSTINGER_API_TOKEN` | `$GH_TOKEN` |
| Source of truth | `/vault/.keys.enc` on locker-vault volume | Same |

> **Note:** The Hostinger API token is stored as `ANTHROPIC_API_KEY` on the VPS for historical reasons. Same value, different name.

### Cold Start Procedure
1. Check for `.env` in repo root
2. If missing, copy `.env.example` → `.env` and fill in tokens
3. Verify: `source .env && curl -s -H "Authorization: Bearer $HOSTINGER_API_TOKEN" "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker" | python3 -m json.tool | head -5`

### Vault Architecture
The `locker-vault` Docker volume is shared:
- **key-locker** (alpine, run-once) writes: `.keys.enc`, `entrypoint.sh`, `bootstrap.sh`, `CLAUDE.md`, `MEMORY.md`
- **claude-hub** reads (read-only mount at `/vault/`)

To update vault contents: modify key-locker compose → delete old → recreate → restart claude-hub.

---

## 4. DNA BET ENGINE (BetApp)

### Live Deployment
- **URL:** `http://187.77.211.80:19801` (VPS Docker container)
- **Runtime:** Python 3.12 / FastAPI / Uvicorn
- **Deploy:** VPS Docker container via Hostinger API (was Railway, migrated 2026-03)
- **Health:** `GET /health` → `{"status": "healthy", "service": "dna-matrix"}`
- **Build info:** `GET /build` → commit, build time, environment

### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/app` | GET | Main web UI (4 tabs: Dashboard, Browse, Builder, Auth) |
| `/app?screen=dashboard` | GET | Dashboard with stats, active bets |
| `/app?screen=browse` | GET | Browse available events |
| `/app?screen=builder` | GET | Parlay builder |
| `/app?screen=auth` | GET | Login/signup |
| `/app/evaluate` | POST | Evaluate a parlay (`{input, tier, legs}`) |
| `/health` | GET | Health check |
| `/build` | GET | Build/deploy metadata |
| `/leading-light/evaluate/text` | POST | Core text evaluation API |
| `/leading-light/evaluate/image` | POST | Bet slip OCR evaluation |
| `/history` | GET | Evaluation history |
| `/voice/*` | — | Voice/TTS narration |
| `/panel` | GET | Developer testing panel |
| `/debug/contracts` | GET | Contract versions, feature flags |

### Architecture
```
Web UI (/app) → FastAPI Router → Evaluation Pipeline
  ↓
  Leading Light Engine → DNA Matrix Core
  ↓
  Tier Gating (GOOD/BETTER/BEST) → Response
```

### Sprint Status
- **Sprint 1:** LOCKED (12 tickets complete, all DoD gates PASS)
- **Sprint 2:** Pending (focus: explainability — why the engine said what it said)
- **Governance:** Ralph Loop — Build → Validate → Explain → Observe → Adjust → Lock

### E2E Testing (Playwright)
Tests live in `e2e/` directory:
- `health.spec.ts` — Health and build endpoints
- `app-ui.spec.ts` — Dashboard, browse, builder, auth screens
- `evaluate-flow.spec.ts` — Evaluate API, landing page, root redirect

Run: `npx playwright test` (targets live VPS deployment at `http://187.77.211.80:19801`)

GitHub Actions CI runs Playwright on every push to `main` (`.github/workflows/e2e.yml` — needs `workflow` scope PAT to push).

---

## 5. MARVIN CORE

### Architecture
```
Transmission → Cache (3-tier) → Lobby (Groq 8B) → Receptionist (Haiku)
  → Department Heads (Ralph/Ira/Tess via Kimi 2.5)
  → Boss (escalation) → Emergency (Opus, last resort)
```

### Execution Waterfall
Claude CLI → Groq Pool → Kimi 2.5 → Boss → Opus API

### Agents
- **Ralph** — Scrum master agent
- **Ira** — Infrastructure agent
- **Tess** — Test agent

### Status
Phase 1 routing integration in progress (cache + classifier done)

---

## 6. CLAUDE HUB BOOT SEQUENCE

When `claude-hub` starts/restarts:

```
1. entrypoint.sh loads /vault/.keys.enc → exports ANTHROPIC_API_KEY, GH_TOKEN
2. Installs tmux + Playwright deps (ephemeral, every boot)
3. First-run: installs git, python3, gh CLI, claude-code, ruflo, playwright
4. bootstrap.sh:
   a. Sets up git credentials from GH_TOKEN
   b. Clones launchplugai/claude-hub, BetApp, marvin (if missing)
   c. Syncs CLAUDE.md from vault → /root/projects/CLAUDE.md
   d. Configures Claude Code settings (remoteControl: true)
   e. Syncs memory files
   f. Runs ruflo init --full (Claude Flow V3)
5. Starts Claude Code in tmux session "claude"
6. Watchdog loop: restarts Claude if tmux session dies
```

---

## 7. CONNECTING TO THE CLAUDE CONTAINER

### From OpenClaw or Another Model

The Claude container runs on the VPS with `network_mode: host`, meaning:
- It can reach Ollama at `127.0.0.1:11434`
- It can reach OpenClaw at `127.0.0.1:46282`
- It exposes Claude Code's remote control interface on the host network

### Sending Commands to Claude Code
Claude Code runs inside `claude-hub` with `remoteControl: true`. To interact:

1. **Via Hostinger Docker API** — Use the container exec-like capabilities through the API
2. **Via tmux session** — The Claude Code process runs in `tmux session "claude"`
3. **Via `claude.ai/code`** — Remote control from the web UI

### Inter-Container Communication
All containers share the host network or can reach localhost services:
```
OpenClaw (127.0.0.1:46282) ←→ Claude Hub (host network)
Ollama  (127.0.0.1:11434)  ←→ Claude Hub (host network)
marvin-skills (:19800)     ←→ Claude Hub (host network)
```

---

## 8. KEY CONSTRAINTS

- Docker compose content limit: **8192 characters** (Hostinger API)
- Container memory: 4 GB (claude-hub)
- No SSH access — Docker-only management via Hostinger API
- Vault volume is read-only from claude-hub
- Ollama and OpenClaw bind to 127.0.0.1 only
- BetApp core evaluation engine is **frozen** — do not modify `dna-matrix/core/evaluation.py`

---

## 9. GITHUB REPOS

| Repo | Branch | CI | Deploy |
|------|--------|-----|--------|
| `launchplugai/marvin` | main | — | VPS (planned) |
| `launchplugai/BetApp` | main | Playwright E2E (GH Actions) | VPS Docker (:19801) |
| `launchplugai/claude-hub` | main | — | VPS Docker |

### GitHub Access
```bash
# Clone with token
git clone https://x-access-token:${GH_TOKEN}@github.com/launchplugai/BetApp.git

# API access
curl -H "Authorization: token $GH_TOKEN" https://api.github.com/repos/launchplugai/BetApp
```

---

## 10. QUICK REFERENCE COMMANDS

```bash
# Check VPS health
curl -s -H "Authorization: Bearer $HOSTINGER_API_TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker" | python3 -m json.tool

# Check BetApp health (VPS)
curl -s http://187.77.211.80:19801/health | python3 -m json.tool

# Check BetApp build (VPS)
curl -s http://187.77.211.80:19801/build | python3 -m json.tool

# Restart claude-hub
curl -X POST -H "Authorization: Bearer $HOSTINGER_API_TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/claude-hub/restart"

# Get container logs
curl -s -H "Authorization: Bearer $HOSTINGER_API_TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/claude-hub/logs"

# Run Playwright E2E tests
cd BetApp && npx playwright test
```
