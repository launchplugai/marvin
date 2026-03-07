# Marvin Orchestration (Redesign)

Marvin is a Python orchestration baseline for multi-agent expansion, now with optional Hostinger VPS API integration.

## What is implemented

- **Lobby classification**: intent detection with keyword-first logic and optional Groq fallback.
- **Cache layer**: SQLite-backed cache with TTL per intent and project/state-aware keys.
- **Transmission envelope**: envelope metadata plus execution-chain tracing.
- **Orchestration loop**: `MarvinSystem` runs classify → cache lookup → route/dispatch → optional cache write.
- **VPS bridge**: status-check flows can query Hostinger VPS API when configured.
- **CLI runner**: invoke the full flow from terminal.

## Project layout

- `src/lobby/` — intent classifier
- `src/cache/` — cache engine + state signature keying
- `src/marvin/` — orchestration package (`system`, `transmission`, `vps`, `main`)
- `tests/unit/` — classifier/cache/VPS unit tests
- `tests/integration/` — orchestration integration tests

## Environment configuration

Copy `.env.example` to `.env` and set:

- `HOSTINGER_API_TOKEN` (required for VPS calls)
- `HOSTINGER_VM_ID` (recommended for direct VM status)
- `HOSTINGER_API_BASE` (optional override)

Marvin will run without these values; VPS checks are skipped when token is missing.

## Run locally

```bash
# Run tests
pytest -q

# Run orchestration
PYTHONPATH=src python -m marvin.main "What's the status of the VPS?" --project .
```

## Next phase direction

- replace `_dispatch` stubs with real agent/container RPC
- add service interfaces for department workers
- expose HTTP API for external control
- persist envelope execution traces for ops dashboards
