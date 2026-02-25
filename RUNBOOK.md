# Marvin — Runbook (bootstrap)

This repo is currently **Phase 1 foundations** (cache + lobby classifier) and is not yet packaged as an installable Python module.

## Prereqs
- Python 3.11+ (this environment is on Python 3.13.x)

## Install dev dependencies

### Option A (recommended): venv
On Debian/Ubuntu, `python3 -m venv` requires the `python3-venv` / `python3.X-venv` OS package.

```bash
# if venv is missing:
#   sudo apt install python3-venv
# or (versioned):
#   sudo apt install python3.13-venv

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements-dev.txt
```

### Option B: override PEP 668 (not recommended)
If you insist on system-wide installs (riskier):

```bash
python3 -m pip install --break-system-packages -r requirements-dev.txt
```

## Running unit tests
Pytest is used; tests add `src/` to `sys.path` directly.

```bash
pytest -q
```

## Quick smoke test (cache layer)

```bash
python src/cache/cache.py
```

This writes/reads a temporary SQLite DB and prints a cache report.

## Environment variables
Lobby classifier (LLM path) is optional; keyword classification works without any API keys.

- `GROQ_API_KEY` — enables Groq-backed semantic classification in `src/lobby/classifier.py`

## Notes / gotchas
- README `Quick Start` currently references `requirements.txt` and `python -m marvin.main ...` which do not exist yet.
  - For now, use the commands in this runbook.
- Cache default DB path:
  - `~/.openclaw/workspace/cache/responses.db`

## Suggested next steps (Phase 1)
- Add packaging (`pyproject.toml`) and a real entrypoint (e.g., `src/marvin/main.py`).
- Add a minimal `requirements.txt` for runtime (separate from dev).
- Wire the Phase 1 end-to-end flow in `docs/designs/08-build-plan.md`.
