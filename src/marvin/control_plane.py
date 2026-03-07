"""Remote control-plane primitives for Codex brain orchestration."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Instruction:
    instruction_id: str
    instruction: str
    target: str
    mode: str
    status: str
    created_at: str


class ControlPlane:
    """File-backed instruction queue + Docker container control helpers."""

    def __init__(self, root_dir: str = "/control"):
        self.root = Path(root_dir)
        self.inbox = self.root / "inbox"
        self.results = self.root / "results"
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)

    def enqueue_instruction(self, instruction: str, target: str = "codex-brain", mode: str = "codex") -> Dict[str, Any]:
        instruction_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "instruction_id": instruction_id,
            "instruction": instruction,
            "target": target,
            "mode": mode,
            "status": "queued",
            "created_at": now,
        }
        (self.inbox / f"{instruction_id}.json").write_text(json.dumps(payload, indent=2))
        return payload

    def get_instruction_status(self, instruction_id: str) -> Dict[str, Any]:
        result_file = self.results / f"{instruction_id}.json"
        if result_file.exists():
            return json.loads(result_file.read_text())

        inbox_file = self.inbox / f"{instruction_id}.json"
        if inbox_file.exists():
            return json.loads(inbox_file.read_text())

        return {"instruction_id": instruction_id, "status": "not_found"}

    def list_containers(self) -> Dict[str, Any]:
        return self._docker(["ps", "--format", "{{json .}}"], multiline=True)

    def container_action(self, name: str, action: str) -> Dict[str, Any]:
        allowed = {"start", "stop", "restart", "logs"}
        if action not in allowed:
            return {"ok": False, "error": f"Unsupported action: {action}"}

        args = [action, name]
        if action == "logs":
            args = ["logs", "--tail", "200", name]

        return self._docker(args, multiline=True)

    def _docker(self, args: List[str], multiline: bool = False) -> Dict[str, Any]:
        command = [os.environ.get("DOCKER_BIN", "docker"), *args]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        except FileNotFoundError:
            return {"ok": False, "error": "docker CLI not found"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "docker command timeout"}

        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or "docker command failed"}

        if multiline:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            parsed: List[Any] = []
            for line in lines:
                try:
                    parsed.append(json.loads(line))
                except json.JSONDecodeError:
                    parsed.append(line)
            return {"ok": True, "data": parsed}

        return {"ok": True, "data": result.stdout.strip()}
