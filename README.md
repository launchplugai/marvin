# Marvin Orchestration (Redesign)

Marvin is now centered on a **working Python orchestration baseline** for multi-agent expansion.

## What is implemented

- **Lobby classification**: intent detection with keyword-first logic and optional Groq fallback.
- **Cache layer**: SQLite-backed cache with TTL per intent and project/state-aware keys.
- **Transmission envelope**: consistent envelope metadata plus execution-chain tracing.
- **Orchestration loop**: `MarvinSystem` runs classify → cache lookup → route/dispatch → optional cache write.
- **CLI runner**: invoke the full flow from terminal.

## Project layout

- `src/lobby/` — intent classifier
- `src/cache/` — cache engine + state signature keying
- `src/marvin/` — orchestration package (system, transmission, CLI)
- `tests/unit/` — classifier/cache unit tests
- `tests/integration/` — orchestration integration tests

## Run locally

```bash
# Run tests
pytest -q

# Run orchestration
PYTHONPATH=src python -m marvin.main "What's the status?" --project .
```

## Next phase direction

This codebase is prepared to become the “mainline” for containerized deployment:

- replace `_dispatch` stubs with real agent/container RPC
- add service interfaces for department workers
- expose HTTP API for external control
- persist envelope execution traces for ops dashboards
