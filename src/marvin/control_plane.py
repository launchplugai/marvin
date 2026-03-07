"""Remote control-plane primitives for Codex brain orchestration."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class ControlPlane:
    """File-backed instruction queue + Docker container control helpers."""

    def __init__(self, root_dir: str = "/control"):
        self.root = Path(root_dir)
        self.inbox = self.root / "inbox"
        self.results = self.root / "results"
        self.audit_log = self.root / "audit.jsonl"
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
            "token_estimate_in": self._estimate_tokens(instruction),
        }
        self._write_json(self.inbox / f"{instruction_id}.json", payload)
        self._append_audit({"event": "queued", "instruction_id": instruction_id, "at": now, "mode": mode})
        return payload

    def get_instruction_status(self, instruction_id: str) -> Dict[str, Any]:
        result_file = self.results / f"{instruction_id}.json"
        if result_file.exists():
            return json.loads(result_file.read_text())

        inbox_file = self.inbox / f"{instruction_id}.json"
        if inbox_file.exists():
            return json.loads(inbox_file.read_text())

        return {"instruction_id": instruction_id, "status": "not_found"}

    def get_metrics(self) -> Dict[str, Any]:
        queued = len(list(self.inbox.glob("*.json")))
        results = [json.loads(p.read_text()) for p in self.results.glob("*.json")]

        completed = [r for r in results if r.get("status") == "completed"]
        failed = [r for r in results if r.get("status") == "failed"]

        durations = [float(r.get("duration_seconds", 0.0)) for r in results if r.get("duration_seconds") is not None]
        avg_duration = round(sum(durations) / len(durations), 3) if durations else 0.0

        token_in = sum(int(r.get("token_estimate_in", 0)) for r in results)
        token_out = sum(int(r.get("token_estimate_out", 0)) for r in results)

        return {
            "ok": True,
            "queued": queued,
            "completed": len(completed),
            "failed": len(failed),
            "processed": len(results),
            "avg_duration_seconds": avg_duration,
            "token_estimate_in": token_in,
            "token_estimate_out": token_out,
            "audit_log": str(self.audit_log),
        }

    def record_result(self, result: Dict[str, Any]) -> None:
        instruction_id = result.get("instruction_id", "unknown")
        status = result.get("status", "unknown")
        now = datetime.now(timezone.utc).isoformat()
        self._append_audit(
            {
                "event": "finished",
                "instruction_id": instruction_id,
                "status": status,
                "duration_seconds": result.get("duration_seconds"),
                "token_estimate_in": result.get("token_estimate_in"),
                "token_estimate_out": result.get("token_estimate_out"),
                "at": now,
            }
        )

    def list_recent_results(self, limit: int = 20) -> Dict[str, Any]:
        files = sorted(self.results.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        data = [json.loads(path.read_text()) for path in files]
        return {"ok": True, "data": data}

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

    def _append_audit(self, event: Dict[str, Any]) -> None:
        with self.audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2))
