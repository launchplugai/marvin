# Marvin System Operations & Model Bootstrap Guide

This guide explains:
- how the system works,
- how to use it,
- how to instruct models to use it,
- how to bootstrap “small models” quickly from repo context,
- how to monitor proof-of-work (tasks, duration, token estimates),
- and how to verify what is working.

## 1) System architecture (what runs where)

### Core containers
- **control-api** (`marvin-control-api`): HTTP access point for remote commands.
- **codex-brain** (`codex-brain`): executes queued instructions via Codex CLI (or shell mode).
- **ollama**: local model runtime.
- **open-webui**: browser UI for Ollama.
- **openclaw**: placeholder service container to swap for your production OpenClaw runtime.

### Control-plane storage
Shared volume: `marvin-control`.
- `/control/inbox/*.json` = queued instructions
- `/control/results/*.json` = completed/failed results
- `/control/audit.jsonl` = event log (queued, started, finished)

## 2) Quick start (VPS)

```bash
cd /path/to/repo
cp .env.example .env
# fill secrets in .env
cd infra
docker compose --env-file ../.env -f codex-control.compose.yml up -d --build
```

Health check:

```bash
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" http://<host>:8787/health
```

## 3) Remote API usage

### Queue an instruction to Codex brain

```bash
curl -X POST http://<host>:8787/instructions \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "instruction":"review repo and prepare deployment checklist",
    "target":"codex-brain",
    "mode":"codex"
  }'
```

### Check one instruction

```bash
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  http://<host>:8787/instructions/<instruction_id>
```

### List recent results

```bash
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  "http://<host>:8787/results?limit=20"
```

### Metrics/proof endpoint

```bash
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  http://<host>:8787/metrics
```

Returns queue depth, completed/failed totals, average duration, and token estimates.

### Control other containers

```bash
# restart ollama
curl -X POST -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  http://<host>:8787/containers/ollama/actions/restart

# fetch logs
curl -X POST -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  http://<host>:8787/containers/openclaw/actions/logs
```

## 4) How to instruct models to use this system

Use this baseline instruction block in new chats:

```text
You are operating inside the Marvin control-plane.
1) Read README.md and SYSTEM_OPERATIONS.md first.
2) Use remote API endpoints on /instructions, /instructions/{id}, /results, /metrics, /containers.
3) Never print secrets. Never commit tokens.
4) Report proof for each task: instruction_id, status, duration_seconds, token_estimate_in/out.
5) If a container command fails, capture stderr and suggest remediation.
```

## 5) Small-model bootstrap (“strap”) flow

When starting a new model/session, do this sequence:

1. Pull repo context:
   - `README.md`
   - `SYSTEM_OPERATIONS.md`
   - `.env.example` (variable names only)
2. Query runtime state:
   - `/health`
   - `/metrics`
   - `/containers`
   - `/results?limit=10`
3. Build local working memory summary:
   - running containers
   - current queue depth
   - last failed tasks and error signatures
   - outstanding priorities

Prompt template:

```text
Bootstrap summary required:
- What services are up?
- What tasks are queued or failed?
- What is avg task duration and estimated token burn?
- What should be done next, in priority order?
```

## 6) Monitoring and proof-of-work

### Available proof fields
From result payloads and metrics:
- `instruction_id`
- `status`
- `duration_seconds`
- `exit_code`
- `token_estimate_in`
- `token_estimate_out`
- `started_at` / `completed_at`

### Audit log
`/control/audit.jsonl` records lifecycle events for traceability.

## 7) Verification checklist (still working)

Run these after deploy/update:

```bash
# tests
pytest -q

# health
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" http://<host>:8787/health

# queue smoke
curl -X POST http://<host>:8787/instructions \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instruction":"echo smoke-test","mode":"shell"}'

# metrics
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" http://<host>:8787/metrics
```

If queue grows but results do not, inspect `codex-brain` logs and `/control/audit.jsonl`.
