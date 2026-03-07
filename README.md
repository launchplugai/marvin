# Marvin Orchestration (Redesign)

Marvin is a Python orchestration baseline for multi-agent expansion, with a remote control-plane for a Codex brain container.

## What is implemented

- **Lobby classification**: intent detection with keyword-first logic and optional Groq fallback.
- **Cache layer**: SQLite-backed cache with TTL per intent and project/state-aware keys.
- **Transmission envelope**: envelope metadata plus execution-chain tracing.
- **Orchestration loop**: `MarvinSystem` runs classify → cache lookup → route/dispatch → optional cache write.
- **VPS bridge**: status-check flows can query Hostinger VPS API when configured.
- **Control plane**: HTTP endpoint for sending instructions to a Codex worker container and controlling peer containers.

## Project layout

- `src/lobby/` — intent classifier
- `src/cache/` — cache engine + state signature keying
- `src/marvin/` — orchestration package (`system`, `transmission`, `vps`, `control_plane`, `control_server`, `main`)
- `infra/codex-control.compose.yml` — container stack (control API, codex brain, Ollama, Open WebUI, OpenClaw placeholder)
- `tests/unit/` — classifier/cache/VPS/control-plane unit tests
- `tests/integration/` — orchestration integration tests

## Environment configuration

Copy `.env.example` to `.env` and set:

- `HOSTINGER_API_TOKEN` (required for VPS calls)
- `HOSTINGER_VM_ID` (recommended for direct VM status)
- `HOSTINGER_API_BASE` (optional override)
- `CONTROL_API_TOKEN` (recommended to secure remote control endpoint)
- `CODEX_COMMAND` (optional override, default `codex`)

Marvin runs without these values; external integrations are skipped when not configured.

## Run locally

```bash
# Run tests
pytest -q

# Run orchestration
PYTHONPATH=src python -m marvin.main "What's the status of the VPS?" --project .
```

## Start the Codex control stack

```bash
cd infra
cp ../.env.example ../.env  # fill secrets in ../.env first
docker compose --env-file ../.env -f codex-control.compose.yml up -d --build
```

## Send remote instructions

```bash
# Queue an instruction for Codex worker
curl -X POST http://localhost:8787/instructions \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instruction":"analyze current repo and suggest next steps","mode":"codex"}'

# Check status by instruction_id
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  http://localhost:8787/instructions/<instruction_id>

# Control peer containers
curl -X POST -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  http://localhost:8787/containers/ollama/actions/restart
```

## Next phase direction

- replace placeholder `openclaw` container command with production OpenClaw runtime
- harden auth (mTLS or signed tokens) and rate-limit control API
- persist instruction/result audit trail in SQLite/Postgres
- replace queue polling with Redis or NATS event bus


## Extended operator guide

- See `SYSTEM_OPERATIONS.md` for full operator, model-bootstrap (strap), monitoring, and proof-of-work procedures.
