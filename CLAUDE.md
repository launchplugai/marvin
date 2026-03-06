# Marvin — Operator Context

> This file is the single source of truth for any Claude Code session working on this project.
> It persists on the VPS vault and is synced to `/root/projects/CLAUDE.md` on every boot.

---

## 1. What Is This System

Marvin is a multi-agent engineering system running on a Hostinger VPS.
It has two operational layers:

1. **Marvin Core** — Python codebase (`src/`) implementing intelligent caching, intent classification, and rate-limit-aware routing across free-tier LLM APIs (Groq, Kimi, Ollama) with Claude as escalation.
2. **Claude Hub** — The VPS container infrastructure that runs Claude Code persistently, manages secrets, bootstraps repos, and enables remote control from `claude.ai/code`.

---

## 2. VPS Infrastructure

### Server
| Field | Value |
|-------|-------|
| Provider | Hostinger |
| Plan | KVM 2 (2 CPU, 8 GB RAM, 100 GB disk) |
| IP | `187.77.211.80` |
| IPv6 | `2a02:4780:4:d31e::1` |
| Hostname | `srv1405440.hstgr.cloud` |
| OS | Ubuntu 24.04 + Docker |
| VM ID | `1405440` |
| API | `https://developers.hostinger.com/api/vps/v1/` |

### Docker Containers

```
┌─────────────────────────────────────────────────────────────┐
│  HOSTINGER VPS  (187.77.211.80)                             │
│                                                             │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐ │
│  │ key-locker  │──▶│ locker-vault │◀──│   claude-hub     │ │
│  │ (alpine)    │   │   (volume)   │   │  (node:20)       │ │
│  │ run-once    │   │              │   │  Claude Code      │ │
│  │             │   │ .keys.enc    │   │  in tmux          │ │
│  │ Provisions: │   │ entrypoint.sh│   │  network: host    │ │
│  │ - API keys  │   │ bootstrap.sh │   │  mem: 4 GB        │ │
│  │ - scripts   │   │ CLAUDE.md    │   │                   │ │
│  │ - bootstrap │   │ MEMORY.md    │   │  /root/projects/  │ │
│  └─────────────┘   └──────────────┘   │   ├── claude-hub/ │ │
│                                       │   ├── BetApp/     │ │
│                                       │   └── CLAUDE.md   │ │
│  ┌──────────────┐   ┌──────────────┐  └──────────────────┘ │
│  │ ollama       │   │ marvin-skills│                        │
│  │ 127.0.0.1:   │   │ :19800       │  ┌──────────────────┐ │
│  │ 11434        │   │ http-server   │  │ openclaw         │ │
│  │ (healthy)    │   │ probe results │  │ 127.0.0.1:46282  │ │
│  └──────────────┘   └──────────────┘  │ Hostinger mgmt   │ │
│                                       └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Volume: `locker-vault`
Shared between key-locker (read-write) and claude-hub (read-only).
Contains:
- `.keys.enc` — `ANTHROPIC_API_KEY` and `GH_TOKEN`
- `entrypoint.sh` — Main container entrypoint
- `bootstrap.sh` — Repo cloning, CLAUDE.md sync, memory sync, Claude Flow init
- `CLAUDE.md` — This file (synced to /root/projects/)
- `MEMORY.md` — Persistent memory for Claude Code sessions

---

## 3. Boot Sequence

When claude-hub starts (or restarts), this happens:

```
1. entrypoint.sh loads /vault/.keys.enc → exports ANTHROPIC_API_KEY, GH_TOKEN
2. Installs tmux (container FS doesn't persist, but npm globals on volume do)
3. First-run only: installs git, python3, gh CLI, claude-code, ruflo
4. Runs bootstrap.sh:
   a. Sets up git credentials from GH_TOKEN
   b. Clones launchplugai/claude-hub (if missing)
   c. Clones launchplugai/BetApp (if missing)
   d. Syncs CLAUDE.md from vault → /root/projects/CLAUDE.md
   e. Configures Claude Code settings (remoteControl: true)
   f. Syncs memory files to Claude Code memory dir
   g. Runs ruflo init --full (Claude Flow V3)
5. Starts Claude Code in tmux session "claude"
6. Watchdog loop: restarts Claude if tmux session dies
```

---

## 4. Hostinger API Reference

**Auth:** `Authorization: Bearer <ANTHROPIC_API_KEY>`
**Base:** `https://developers.hostinger.com/api/vps/v1`

### Key Endpoints

| Action | Method | Path |
|--------|--------|------|
| List VMs | GET | `/virtual-machines` |
| VM details | GET | `/virtual-machines/{id}` |
| List Docker projects | GET | `/virtual-machines/{id}/docker` |
| Get project compose | GET | `/virtual-machines/{id}/docker/{name}` |
| Create project | POST | `/virtual-machines/{id}/docker` |
| Update project | POST | `/virtual-machines/{id}/docker/{name}/update` |
| Get project logs | GET | `/virtual-machines/{id}/docker/{name}/logs` |
| Get containers | GET | `/virtual-machines/{id}/docker/{name}/containers` |
| Start project | POST | `/virtual-machines/{id}/docker/{name}/start` |
| Stop project | POST | `/virtual-machines/{id}/docker/{name}/stop` |
| Restart project | POST | `/virtual-machines/{id}/docker/{name}/restart` |
| Delete project | DELETE | `/virtual-machines/{id}/docker/{name}/down` |
| Start VM | POST | `/virtual-machines/{id}/start` |
| Stop VM | POST | `/virtual-machines/{id}/stop` |
| Restart VM | POST | `/virtual-machines/{id}/restart` |
| Get actions | GET | `/virtual-machines/{id}/actions` |
| Action status | GET | `/virtual-machines/{id}/actions/{actionId}` |
| Set root password | PUT | `/virtual-machines/{id}/root-password` |
| Firewall list | GET | `/firewall` |
| Create firewall | POST | `/firewall` |

### VM ID: `1405440`

### Docker Projects

| Project | Image | State | Ports | Notes |
|---------|-------|-------|-------|-------|
| `claude-hub` | node:20-bookworm | running | host network | Claude Code + tmux |
| `key-locker` | alpine:3.19 | exited | none | Run-once vault provisioner |
| `marvin-skills` | node:20-slim | running | 19800 | HTTP probe server |
| `ollama-wmf4` | ollama/ollama | running (healthy) | 127.0.0.1:11434 | Local LLM |
| `openclaw-quzk` | ghcr.io/hostinger/hvps-openclaw | running | 127.0.0.1:46282 | Hostinger mgmt |

---

## 5. Operating Procedures

### Restart claude-hub (bootstrap fresh)
```bash
# Via Hostinger API
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "$API/virtual-machines/1405440/docker/claude-hub/restart"
```

### Update vault keys
1. Update key-locker compose to include new keys in `.keys.enc`
2. Delete old key-locker: `DELETE .../docker/key-locker/down`
3. Recreate: `POST .../docker` with `{"project_name": "key-locker", "content": "..."}`
4. Restart claude-hub to pick up new keys

### Update entrypoint/bootstrap scripts
Same as updating vault keys — scripts are base64-encoded in the key-locker compose.
Decode → modify → re-encode → update compose → redeploy key-locker → restart claude-hub.

### Deploy new Docker project
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_name": "my-project", "content": "<docker-compose YAML>"}' \
  "$API/virtual-machines/1405440/docker"
```

### Check container health
```bash
# List all projects
curl -H "Authorization: Bearer $TOKEN" "$API/virtual-machines/1405440/docker"

# Get logs
curl -H "Authorization: Bearer $TOKEN" "$API/virtual-machines/1405440/docker/{name}/logs"
```

---

## 6. Repositories

| Repo | Purpose | VPS Path |
|------|---------|----------|
| `launchplugai/marvin` | Agentic system core (this repo) | `/root/projects/marvin` (planned) |
| `launchplugai/claude-hub` | Claude Hub infrastructure | `/root/projects/claude-hub` |
| `launchplugai/BetApp` | Betting app project | `/root/projects/BetApp` |

---

## 7. Marvin Architecture (Quick Reference)

```
Transmission → Cache (3-tier) → Lobby (Groq 8B) → Receptionist (Haiku)
    → Department Heads (Ralph/Ira/Tess via Kimi 2.5)
    → Boss (escalation) → Emergency (Opus, last resort)
```

**Execution waterfall:** Claude CLI → Groq Pool → Kimi 2.5 → Boss → Opus API

**Agents:** Ralph (Scrum), Ira (Infra), Tess (Test)

**Phase Status:** Phase 1 routing integration in progress (cache + classifier done)

---

## 8. Key Constraints

- Docker compose content limit: **8192 characters** (Hostinger API)
- Container memory: 4 GB (claude-hub)
- No SSH access via API — management is Docker-only via Hostinger API
- Vault volume is read-only from claude-hub
- Ollama and OpenClaw bind to 127.0.0.1 only (not externally accessible)
- claude-hub uses `network_mode: host` — can reach all localhost services

---

## 9. Secrets & Token Discovery

### Where tokens live

| Context | Hostinger API Token | GH_TOKEN |
|---------|--------------------:|:---------|
| **VPS (claude-hub container)** | `$ANTHROPIC_API_KEY` env var (loaded from vault) | `$GH_TOKEN` env var (loaded from vault) |
| **Local / new chat session** | `.env` file in repo root (gitignored) | `.env` file in repo root (gitignored) |
| **Vault source of truth** | `/vault/.keys.enc` on locker-vault volume | `/vault/.keys.enc` on locker-vault volume |

### Cold Start — New Session Without Context

If you're a new Claude Code session with no prior context, do this:

1. **Check if `.env` exists** in the repo root. If yes, read it for tokens.
2. **If no `.env`**, try to retrieve tokens from the **key-locker** on the VPS:
   - Fetch the key-locker compose: `GET .../docker/key-locker`
   - The compose contains a `printf` line writing `/vault/.keys.enc` with `ANTHROPIC_API_KEY` and `GH_TOKEN`
   - Extract those values and write them to `.env` using the `.env.example` template
   - If you have no existing token to call the API, ask the user to provide one or fill `.env` manually
3. **To verify tokens work**, run:
   ```bash
   source .env
   curl -s -H "Authorization: Bearer $HOSTINGER_API_TOKEN" \
     "$HOSTINGER_API_BASE/virtual-machines/$HOSTINGER_VM_ID/docker" \
     | python3 -m json.tool | head -5
   ```
4. **Once tokens are confirmed**, you have full VPS access. Read `hub-card.md` for the architecture.

### Token Naming

The Hostinger API token is stored as `ANTHROPIC_API_KEY` on the VPS for historical reasons.
In `.env` it's called `HOSTINGER_API_TOKEN` for clarity. They're the same value.

---

## 10. Available Commands

These slash commands are defined in `.claude/commands/` and work in any session on this repo:

| Command | Purpose |
|---------|---------|
| `/bootstrap` | Load full system context + check VPS health |
| `/vps-status` | List all Docker containers and their states |
| `/vps-logs` | Tail logs from a specific container |
| `/vps-deploy` | Deploy or update a Docker project |
| `/vault-update` | Update secrets or scripts in the vault |
