#!/usr/bin/env python3
"""Queue worker that executes instructions inside codex-brain container."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

CONTROL_DIR = Path(os.environ.get("CONTROL_PLANE_DIR", "/control"))
INBOX = CONTROL_DIR / "inbox"
RESULTS = CONTROL_DIR / "results"
AUDIT_LOG = CONTROL_DIR / "audit.jsonl"
CODEX_COMMAND = os.environ.get("CODEX_COMMAND", "codex")
POLL_SECONDS = float(os.environ.get("CONTROL_POLL_SECONDS", "2"))

INBOX.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _append_audit(event: dict) -> None:
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def _run_instruction(payload: dict) -> dict:
    mode = payload.get("mode", "codex")
    instruction = payload.get("instruction", "")

    if mode == "shell":
        command = ["bash", "-lc", instruction]
    else:
        command = [CODEX_COMMAND, instruction]

    start_ts = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    _append_audit({"event": "started", "instruction_id": payload.get("instruction_id"), "at": started, "mode": mode})

    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        duration = round(time.monotonic() - start_ts, 3)
        status = "completed" if proc.returncode == 0 else "failed"
        result = {
            **payload,
            "status": status,
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "command": command,
            "token_estimate_in": payload.get("token_estimate_in", _estimate_tokens(instruction)),
            "token_estimate_out": _estimate_tokens((proc.stdout or "") + (proc.stderr or "")),
        }
        _append_audit(
            {
                "event": "finished",
                "instruction_id": payload.get("instruction_id"),
                "status": status,
                "duration_seconds": duration,
                "token_estimate_in": result["token_estimate_in"],
                "token_estimate_out": result["token_estimate_out"],
                "at": result["completed_at"],
            }
        )
        return result
    except FileNotFoundError:
        result = {
            **payload,
            "status": "failed",
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - start_ts, 3),
            "exit_code": 127,
            "stdout": "",
            "stderr": f"Command not found: {command[0]}",
            "command": command,
            "token_estimate_in": payload.get("token_estimate_in", _estimate_tokens(instruction)),
            "token_estimate_out": 1,
        }
        _append_audit({"event": "finished", "instruction_id": payload.get("instruction_id"), "status": "failed", "at": result["completed_at"]})
        return result
    except subprocess.TimeoutExpired as exc:
        result = {
            **payload,
            "status": "failed",
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - start_ts, 3),
            "exit_code": 124,
            "stdout": (exc.stdout or "")[-12000:],
            "stderr": (exc.stderr or "")[-12000:],
            "command": command,
            "error": "timeout",
            "token_estimate_in": payload.get("token_estimate_in", _estimate_tokens(instruction)),
            "token_estimate_out": _estimate_tokens((exc.stdout or "") + (exc.stderr or "")),
        }
        _append_audit({"event": "finished", "instruction_id": payload.get("instruction_id"), "status": "failed", "at": result["completed_at"]})
        return result


def main() -> None:
    while True:
        for file in sorted(INBOX.glob("*.json")):
            payload = json.loads(file.read_text())
            result = _run_instruction(payload)
            (RESULTS / file.name).write_text(json.dumps(result, indent=2))
            file.unlink(missing_ok=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
