"""
Dispatcher — Tool execution engine for Marvin agents.

Agents don't just talk — they do things. The dispatcher provides
safe, audited execution of:
  - Shell commands (git, npm, python, etc.)
  - Hostinger VPS API calls (container management)
  - File operations (read/write project files)

Every action is logged. Dangerous commands are blocked.
"""

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger(__name__)


# Commands that are never allowed
BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    ":(){:|:&};:",
    "dd if=/dev/",
    "> /dev/sda",
    "chmod -R 777 /",
]

# Patterns that require explicit allowlisting
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\b",
    r"git\s+push\s+.*--force",
    r"git\s+reset\s+--hard",
    r"DROP\s+TABLE",
    r"DROP\s+DATABASE",
]


class ActionType(Enum):
    SHELL = "shell"
    API = "api"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"


@dataclass
class ActionResult:
    success: bool
    output: str
    action_type: str
    duration_ms: int
    command: str = ""


@dataclass
class AuditEntry:
    timestamp: int
    action_type: str
    command: str
    success: bool
    duration_ms: int
    output_preview: str


class Dispatcher:
    """
    Executes actions on behalf of agents with safety checks and audit logging.
    """

    def __init__(self, work_dir: str = None, hostinger_token: str = None,
                 vm_id: str = "1405440"):
        self.work_dir = work_dir or os.path.expanduser("~/projects")
        self.hostinger_token = hostinger_token or os.environ.get("HOSTINGER_API_TOKEN")
        self.vm_id = vm_id
        self.api_base = "https://developers.hostinger.com/api/vps/v1"
        self.audit_log: List[AuditEntry] = []

        # Shell commands that agents are allowed to run
        self.allowed_commands = [
            "git", "python", "python3", "pip", "pip3",
            "npm", "npx", "node",
            "pytest", "ls", "cat", "head", "tail", "wc",
            "grep", "find", "diff", "echo",
            "curl", "docker",
        ]

    def run_shell(self, command: str, cwd: str = None,
                  timeout: int = 60) -> ActionResult:
        """Run a shell command with safety checks."""
        # Safety: block dangerous commands
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ActionResult(
                    success=False, output=f"BLOCKED: dangerous command '{blocked}'",
                    action_type="shell", duration_ms=0, command=command,
                )

        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return ActionResult(
                    success=False,
                    output=f"BLOCKED: matches dangerous pattern '{pattern}'",
                    action_type="shell", duration_ms=0, command=command,
                )

        # Safety: only allow known command prefixes
        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word not in self.allowed_commands:
            return ActionResult(
                success=False,
                output=f"BLOCKED: '{first_word}' not in allowed commands: {self.allowed_commands}",
                action_type="shell", duration_ms=0, command=command,
            )

        start = time.time()
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or self.work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = int((time.time() - start) * 1000)
            output = result.stdout + result.stderr
            success = result.returncode == 0

            self._audit("shell", command, success, duration, output)
            return ActionResult(
                success=success, output=output.strip(),
                action_type="shell", duration_ms=duration, command=command,
            )

        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            self._audit("shell", command, False, duration, "TIMEOUT")
            return ActionResult(
                success=False, output=f"Command timed out after {timeout}s",
                action_type="shell", duration_ms=duration, command=command,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._audit("shell", command, False, duration, str(e))
            return ActionResult(
                success=False, output=str(e),
                action_type="shell", duration_ms=duration, command=command,
            )

    def read_file(self, path: str) -> ActionResult:
        """Read a file from the project directory."""
        start = time.time()
        full_path = os.path.join(self.work_dir, path) if not os.path.isabs(path) else path
        try:
            with open(full_path) as f:
                content = f.read()
            duration = int((time.time() - start) * 1000)
            self._audit("file_read", path, True, duration, f"{len(content)} bytes")
            return ActionResult(
                success=True, output=content,
                action_type="file_read", duration_ms=duration, command=path,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._audit("file_read", path, False, duration, str(e))
            return ActionResult(
                success=False, output=str(e),
                action_type="file_read", duration_ms=duration, command=path,
            )

    def write_file(self, path: str, content: str) -> ActionResult:
        """Write a file to the project directory."""
        start = time.time()
        full_path = os.path.join(self.work_dir, path) if not os.path.isabs(path) else path
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            duration = int((time.time() - start) * 1000)
            self._audit("file_write", path, True, duration, f"{len(content)} bytes")
            return ActionResult(
                success=True, output=f"Written {len(content)} bytes to {path}",
                action_type="file_write", duration_ms=duration, command=path,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._audit("file_write", path, False, duration, str(e))
            return ActionResult(
                success=False, output=str(e),
                action_type="file_write", duration_ms=duration, command=path,
            )

    def vps_api(self, method: str, endpoint: str,
                body: Dict = None) -> ActionResult:
        """Call the Hostinger VPS API."""
        if not self.hostinger_token:
            return ActionResult(
                success=False, output="HOSTINGER_API_TOKEN not configured",
                action_type="api", duration_ms=0, command=endpoint,
            )

        url = f"{self.api_base}{endpoint}"
        headers = {"Authorization": f"Bearer {self.hostinger_token}"}

        start = time.time()
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "POST":
                headers["Content-Type"] = "application/json"
                resp = requests.post(url, headers=headers, json=body or {}, timeout=30)
            elif method.upper() == "DELETE":
                resp = requests.delete(url, headers=headers, timeout=30)
            else:
                return ActionResult(
                    success=False, output=f"Unsupported method: {method}",
                    action_type="api", duration_ms=0, command=endpoint,
                )

            duration = int((time.time() - start) * 1000)
            success = 200 <= resp.status_code < 300

            try:
                output = json.dumps(resp.json(), indent=2)
            except ValueError:
                output = resp.text

            self._audit("api", f"{method} {endpoint}", success, duration, output[:200])
            return ActionResult(
                success=success, output=output,
                action_type="api", duration_ms=duration,
                command=f"{method} {endpoint}",
            )

        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self._audit("api", f"{method} {endpoint}", False, duration, str(e))
            return ActionResult(
                success=False, output=str(e),
                action_type="api", duration_ms=duration,
                command=f"{method} {endpoint}",
            )

    def container_status(self) -> ActionResult:
        """Get status of all Docker containers on the VPS."""
        return self.vps_api("GET", f"/virtual-machines/{self.vm_id}/docker")

    def container_logs(self, name: str) -> ActionResult:
        """Get logs from a specific container."""
        return self.vps_api("GET", f"/virtual-machines/{self.vm_id}/docker/{name}/logs")

    def container_restart(self, name: str) -> ActionResult:
        """Restart a container."""
        return self.vps_api("POST", f"/virtual-machines/{self.vm_id}/docker/{name}/restart")

    def _audit(self, action_type: str, command: str, success: bool,
               duration_ms: int, output: str):
        entry = AuditEntry(
            timestamp=int(time.time()),
            action_type=action_type,
            command=command,
            success=success,
            duration_ms=duration_ms,
            output_preview=output[:200],
        )
        self.audit_log.append(entry)
        level = logging.INFO if success else logging.WARNING
        logger.log(level, f"[{action_type}] {command} -> {'OK' if success else 'FAIL'} ({duration_ms}ms)")

    def get_audit_log(self, limit: int = 20) -> List[Dict]:
        entries = self.audit_log[-limit:]
        return [
            {
                "time": e.timestamp,
                "type": e.action_type,
                "command": e.command,
                "ok": e.success,
                "ms": e.duration_ms,
                "preview": e.output_preview,
            }
            for e in entries
        ]
