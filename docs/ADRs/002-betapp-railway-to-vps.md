# ADR-002: Migrate BetApp from Railway to VPS Docker

**Date:** 2026-03-05
**Status:** Executed
**Repo:** launchplugai/BetApp

---

## Context

BetApp was deployed on Railway (`https://dna-production-cb47.up.railway.app`) using Nixpacks auto-deploy on push to `main`. Railway deployments became intermittent (blocker B002), and the VPS already hosted all other infrastructure.

## Decision

Migrate BetApp to a Docker container on the Hostinger VPS (187.77.211.80), consolidating all services on one host.

## Implementation

- **Container:** `betapp` (python:3.12-slim)
- **Port:** `:19801` (public)
- **Runtime:** FastAPI / Uvicorn
- **Health check:** `GET /health` every 30s (Docker healthcheck)
- **Deploy method:** Hostinger Docker API (`POST /virtual-machines/1405440/docker`)

## Verification

Container confirmed running and healthy via Hostinger API on 2026-03-05:
- Status: `Up 2 hours (healthy)`
- Health endpoint returning `200 OK` every 30 seconds
- All existing endpoints accessible at `http://187.77.211.80:19801`

## Consequences

- Railway deployment is no longer used; Railway tokens in `.env` can be removed
- Blocker B002 (Railway deploy failures) is resolved
- All services now consolidated on one VPS (betapp, claude-hub, marvin-skills, ollama, openclaw)
- Single point of failure on VPS, but simpler to manage and monitor
- Docs updated: CLAUDE.md, CHAT_PACKAGE.md, mission-control, design docs
