# ADR-001: Close BetApp Stale Branches

**Date:** 2026-03-03
**Status:** Approved — pending execution
**Repo:** launchplugai/BetApp

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

## Execution Commands

```bash
# From any session with BetApp push access:
git push origin --delete claude/ticket-38b-a-structural-snapshot
git push origin --delete claude/ticket-38b-c2-grounding-score
git push origin --delete betapp/api-sports-games-fix
```

## Cherry-pick reference (if needed later)

The non-vendor commits on `api-sports-games-fix` before deletion:
- `b00b43d` — Add resilient /api/sports and /api/games endpoints
- Dockerfile + .dockerignore + railway.json fix
