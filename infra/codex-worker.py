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
CODEX_COMMAND = os.environ.get("CODEX_COMMAND", "codex")
POLL_SECONDS = float(os.environ.get("CONTROL_POLL_SECONDS", "2"))

INBOX.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)


def _run_instruction(payload: dict) -> dict:
    mode = payload.get("mode", "codex")
    instruction = payload.get("instruction", "")

    if mode == "shell":
        command = ["bash", "-lc", instruction]
    else:
        command = [CODEX_COMMAND, instruction]

    started = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        status = "completed" if proc.returncode == 0 else "failed"
        return {
            **payload,
            "status": status,
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "command": command,
        }
    except FileNotFoundError:
        return {
            **payload,
            "status": "failed",
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "exit_code": 127,
            "stdout": "",
            "stderr": f"Command not found: {command[0]}",
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            **payload,
            "status": "failed",
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "exit_code": 124,
            "stdout": (exc.stdout or "")[-12000:],
            "stderr": (exc.stderr or "")[-12000:],
            "command": command,
            "error": "timeout",
        }


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
