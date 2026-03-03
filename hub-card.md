# Hub Card — System Identity & Persistence Reference

> **Purpose:** This document gives any new Claude Code session complete context
> to operate the full system without prior conversation history.

---

## Identity

**System:** Marvin — Autonomous agentic engineering system
**Owner:** launchplugai
**Operator:** Claude Code (persistent VPS instance + ephemeral chat sessions)

---

## How This System Works

There are **two planes** where Claude Code operates:

### Plane 1: VPS (Persistent)
A Hostinger VPS runs Claude Code 24/7 inside a Docker container (`claude-hub`).
- It has filesystem access, git repos, and an Anthropic API key
- It runs in a tmux session with remote control enabled
- It survives reboots via the Docker restart policy + watchdog loop
- Secrets and scripts live on a Docker volume (`locker-vault`) provisioned by `key-locker`

### Plane 2: Chat Sessions (Ephemeral)
Each new conversation on claude.ai or Claude Code CLI is ephemeral.
- No memory of previous chats unless explicitly provided
- Can manage the VPS via the Hostinger REST API (no SSH needed)
- Reads `CLAUDE.md` and `hub-card.md` for full system context
- Can deploy code, update containers, check logs, and restart services

### The Bridge
Chat sessions control the VPS through the **Hostinger API**:
- Deploy/update Docker projects
- Read container logs
- Restart containers
- Update vault secrets

The VPS runs the code. Chat sessions orchestrate.

---

## Quick Start for New Sessions

### 1. Verify VPS is alive
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker" \
  | python3 -m json.tool
```

### 2. Check claude-hub logs
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/claude-hub/logs"
```

### 3. Restart if needed
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/claude-hub/restart"
```

---

## Container Map

| Container | Image | Purpose | Persistence | Network |
|-----------|-------|---------|-------------|---------|
| `claude-hub` | node:20-bookworm | Claude Code + tmux + repos | `claude-home` volume (npm globals, repos) | host |
| `key-locker` | alpine:3.19 | Provisions secrets + scripts to vault | `locker-vault` volume | default |
| `marvin-skills` | node:20-slim | HTTP probe server for diagnostics | none | default + openclaw_net |
| `ollama-wmf4` | ollama/ollama | Local LLM inference | `ollama` volume | default |
| `openclaw-quzk` | ghcr.io/hostinger/hvps-openclaw | Hostinger management agent | /data/.openclaw | default |

---

## Volume Architecture

```
locker-vault (external, shared)
├── .keys.enc          # ANTHROPIC_API_KEY + GH_TOKEN
├── entrypoint.sh      # Container startup script
├── bootstrap.sh       # Repo cloner + context syncer
├── CLAUDE.md          # Project instructions (synced to /root/projects/)
└── MEMORY.md          # Persistent memory (synced to Claude memory dir)

claude-home (claude-hub only)
├── .claude-hub-ready  # First-run sentinel
├── .npm-global/       # Claude Code, ruflo, global npm packages
├── .claude/           # Claude Code config + memory
├── .git-credentials   # GitHub auth (from GH_TOKEN)
└── projects/          # Cloned repos (claude-hub, BetApp)
    ├── claude-hub/
    ├── BetApp/
    ├── CLAUDE.md
    └── .claude-flow/  # Ruflo/Claude Flow V3 runtime
```

---

## Boot Sequence (claude-hub)

```
CONTAINER START
    │
    ▼
[1] Load /vault/.keys.enc → export ANTHROPIC_API_KEY, GH_TOKEN
    │
    ▼
[2] Install tmux (apt, every boot — container FS ephemeral)
    │
    ▼
[3] First-run? ──yes──▶ Install git, python3, gh, claude-code, ruflo
    │                    Create /root/.claude-hub-ready sentinel
    no
    │
    ▼
[4] Run bootstrap.sh:
    ├── Configure git credentials from GH_TOKEN
    ├── Clone repos if missing (claude-hub, BetApp)
    ├── Sync CLAUDE.md from vault → /root/projects/
    ├── Configure Claude Code settings (remoteControl: true)
    ├── Sync memory files from vault → Claude memory dir
    └── Run ruflo init --full (if .claude-flow missing)
    │
    ▼
[5] Start Claude Code in tmux session "claude"
    │
    ▼
[6] Watchdog: every 30s, restart tmux session if dead
```

---

## API Cheatsheet

**Base:** `https://developers.hostinger.com/api/vps/v1`
**Auth:** `Authorization: Bearer <token>`
**VM:** `1405440`

| What | Call |
|------|------|
| All projects | `GET /virtual-machines/1405440/docker` |
| Project compose | `GET /virtual-machines/1405440/docker/{name}` |
| Project logs | `GET /virtual-machines/1405440/docker/{name}/logs` |
| Create project | `POST /virtual-machines/1405440/docker` body: `{project_name, content}` |
| Update project | `POST /virtual-machines/1405440/docker/{name}/update` body: `{content}` |
| Restart project | `POST /virtual-machines/1405440/docker/{name}/restart` |
| Stop project | `POST /virtual-machines/1405440/docker/{name}/stop` |
| Delete project | `DELETE /virtual-machines/1405440/docker/{name}/down` |
| Action status | `GET /virtual-machines/1405440/actions/{id}` |
| VM info | `GET /virtual-machines/1405440` |

**Compose limit:** 8192 characters max.

---

## Repos

| Repo | Branch Convention | Purpose |
|------|-------------------|---------|
| `launchplugai/marvin` | `claude/code-mode-*` | Agentic system, cache, routing |
| `launchplugai/claude-hub` | `main` | VPS infrastructure, scripts |
| `launchplugai/BetApp` | varies | Betting app project |

---

## Updating the Vault

The vault is a Docker volume. You can't write to it directly — you update it
by redeploying the key-locker container:

1. Fetch current compose: `GET .../docker/key-locker`
2. Modify the compose (keys in printf line, scripts in base64 blobs)
3. Delete old: `DELETE .../docker/key-locker/down`
4. Wait for action success
5. Create new: `POST .../docker` with `{project_name: "key-locker", content: "..."}`
6. Restart claude-hub: `POST .../docker/claude-hub/restart`

**Scripts are base64-encoded in the compose.** To edit:
```bash
echo '<base64>' | base64 -d > script.sh    # decode
# edit script.sh
base64 -w0 script.sh                        # re-encode
# paste back into compose
```

---

## What Persists Across Chat Sessions

| What | Where | Survives |
|------|-------|----------|
| API keys | locker-vault volume | Container restarts, VM reboots |
| Entrypoint/bootstrap scripts | locker-vault volume | Container restarts, VM reboots |
| CLAUDE.md | locker-vault + /root/projects/ | Container restarts |
| Memory files | locker-vault + Claude memory dir | Container restarts |
| Cloned repos | claude-home volume | Container restarts |
| npm globals (claude-code, ruflo) | claude-home volume | Container restarts |
| Container FS (apt packages) | **LOST** on recreate | Only within single container lifecycle |

---

## Failure Modes & Recovery

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Clone failed (auth needed?)" | GH_TOKEN missing/invalid | Update key-locker with valid GH_TOKEN, restart |
| "tmux: command not found" | Container recreated, apt cache lost | Entrypoint auto-installs tmux on boot |
| Claude Code crash loop | API key invalid or network issue | Check logs, verify ANTHROPIC_API_KEY |
| Container won't start | Compose syntax error | GET compose, validate YAML, update |
| Vault empty after restart | key-locker didn't run | Delete + recreate key-locker, then restart claude-hub |

---

## Network Topology

```
Internet
    │
    ▼
┌─────────────────────────┐
│  VPS 187.77.211.80      │
│                         │
│  :19800 ◀── marvin-skills (public, probe results)
│                         │
│  127.0.0.1:11434 ◀── ollama (local only)
│  127.0.0.1:46282 ◀── openclaw (local only)
│                         │
│  claude-hub (host network) can reach all localhost ports
└─────────────────────────┘
```

Only port 19800 is publicly accessible. Ollama and OpenClaw are localhost-only.
claude-hub uses `network_mode: host` so it can reach everything on localhost.
