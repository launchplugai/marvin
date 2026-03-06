# ADR-001: Close Stale Development Branches

**Date:** 2026-03-03 (BetApp), 2026-03-06 (Marvin)
**Status:** Executed — all stale branches deleted
**Repos:** launchplugai/BetApp, launchplugai/marvin

---

## Context

Three feature branches have been open on BetApp and need to be closed out.

## Branch Analysis

### 1. `claude/ticket-38b-a-structural-snapshot`
- **Tip:** `33a2540`
- **Commits ahead of main:** 0
- **Verdict:** Already merged. Safe to delete.

### 2. `claude/ticket-38b-c2-grounding-score`
- **Tip:** `c20fbae`
- **Commits ahead of main:** 0
- **Verdict:** Already merged. Safe to delete.

### 3. `betapp/api-sports-games-fix`
- **Tip:** `b00b43d`
- **Commits ahead of main:** 3
- **Unmerged changes:**
  - `Dockerfile` — production container (python:3.12-slim)
  - `Dockerfile.test` — test container (python:3.13-slim)
  - `.dockerignore` — standard exclusions
  - `core/__init__.py` — bridge package for dna-matrix imports
  - `railway.json` — fix `sh -lc` wrapper for `$(date)` expansion
  - `vendor/` — ~53K lines of vendored Python packages (httpx, bcrypt, certifi, etc.)
- **Verdict:** Delete. The vendor/ directory is not appropriate for version control. The useful changes (Dockerfile, railway.json fix) can be cherry-picked onto a clean branch if needed later.

## Decision

Delete all three remote branches.

## Execution

All three branches were deleted. Verified via GitHub API on 2026-03-03:
- `claude/ticket-38b-a-structural-snapshot` — **DELETED**
- `claude/ticket-38b-c2-grounding-score` — **DELETED**
- `betapp/api-sports-games-fix` — **DELETED**

BetApp now has only `main`. No open PRs remain.

## Cherry-pick reference (if needed later)

The non-vendor commits on `api-sports-games-fix` before deletion:
- `b00b43d` — Add resilient /api/sports and /api/games endpoints
- Dockerfile + .dockerignore + railway.json fix

---

## Phase 2: Marvin Repo Branch Cleanup (2026-03-06)

### Branch Analysis

#### 1. `bootstrap/runbook`
- **Commits ahead of master:** 6 (diverged, 9 behind)
- **Content:** Alternative lobby implementation with circuit breakers, routing contracts, config-driven design. Removes Phase 1 cache/rate-limiter code.
- **Verdict:** Superseded. Master has the canonical Phase 1 implementation. Delete.

#### 2. `claude/code-mode-TgCva`
- **Commits ahead of master:** 1 (diverged, 3 behind)
- **Content:** Cold-start bootstrap fix — adds `.claude/` commands, `.env.example`, infra scripts, `.gitignore`.
- **Verdict:** Already incorporated into the active development branch. Delete.

#### 3. `claude/create-vps-api-Gf2cY`
- **Commits ahead of master:** 17 (diverged, 9 behind)
- **Content:** 79K+ lines — VPS API client, Telegram bot, gateway, rate limiter, deploy scripts, claude-flow orchestration with 200+ auto-generated agent/skill/command files.
- **Verdict:** Bloat-heavy. Useful VPS/gateway patterns exist but buried under generated scaffolding. The active branch has cleaner implementations. Delete.

### Execution

All three marvin branches deleted via GitHub API on 2026-03-06:
- `bootstrap/runbook` — **DELETED** (HTTP 204)
- `claude/code-mode-TgCva` — **DELETED** (HTTP 204)
- `claude/create-vps-api-Gf2cY` — **DELETED** (HTTP 204)

Marvin repo now has only `master` and the active working branch.
