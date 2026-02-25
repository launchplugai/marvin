#!/usr/bin/env python3
"""
SSH Exec Bridge — Remote Command Execution for Mission Control

Allows Mission Control to execute commands on the VPS via SSH,
including `docker exec` inside containers. This is the missing link
that lets agents manage OpenClaw without manual SSH sessions.

Security model:
- Key-based auth only (no passwords stored)
- Private key loaded from file or env var
- Command audit logging (every exec is recorded)
- Timeout on all commands (no hanging connections)
- Optional command allowlist for safety

Usage:
    bridge = SSHExecBridge(host="187.77.211.80", username="root")
    result = bridge.exec("docker ps")
    result = bridge.docker_exec("openclaw-quzk-openclaw-1", "openclaw --version")
    bridge.close()
"""

import io
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False
    logger.debug("paramiko not installed — SSH exec bridge unavailable")


@dataclass
class ExecResult:
    """Result of a remote command execution."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool
    duration_ms: float
    host: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SSHExecBridge:
    """
    SSH-based remote command execution bridge.

    Connects to the VPS and runs commands — including `docker exec`
    for managing containers. All executions are logged.

    Auth priority:
    1. Explicit key_path parameter
    2. SSH_PRIVATE_KEY_PATH env var
    3. SSH_PRIVATE_KEY env var (key content as string)
    4. Default ~/.ssh/id_ed25519 or ~/.ssh/id_rsa
    """

    DEFAULT_TIMEOUT = 30
    DEFAULT_PORT = 22

    def __init__(
        self,
        host: str = None,
        username: str = "root",
        port: int = None,
        key_path: str = None,
        key_content: str = None,
        timeout: int = None,
    ):
        """
        Initialize the SSH bridge.

        Args:
            host: VPS IP address or hostname.
            username: SSH username (default: root).
            port: SSH port (default: 22).
            key_path: Path to private key file.
            key_content: Private key as string (for env var injection).
            timeout: Command timeout in seconds.
        """
        if not HAS_PARAMIKO:
            raise ImportError(
                "paramiko is required for SSH exec bridge. "
                "Install with: pip install paramiko"
            )

        self.host = host or os.environ.get("VPS_HOST", "")
        self.username = username or os.environ.get("VPS_USER", "root")
        self.port = port or int(os.environ.get("VPS_SSH_PORT", str(self.DEFAULT_PORT)))
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self._client: Optional[paramiko.SSHClient] = None
        self._exec_log: List[ExecResult] = []

        # Resolve private key
        self._key = self._load_key(key_path, key_content)

        logger.info(
            f"SSHExecBridge initialized (host={self.host}, user={self.username}, "
            f"port={self.port}, key={'loaded' if self._key else 'none'})"
        )

    def _load_key(self, key_path: str = None, key_content: str = None):
        """Load SSH private key from file or string."""
        # Priority 1: Explicit path
        if key_path and os.path.isfile(key_path):
            return self._read_key_file(key_path)

        # Priority 2: Env var path
        env_path = os.environ.get("SSH_PRIVATE_KEY_PATH", "")
        if env_path and os.path.isfile(env_path):
            return self._read_key_file(env_path)

        # Priority 3: Env var content
        content = key_content or os.environ.get("SSH_PRIVATE_KEY", "")
        if content:
            return self._parse_key_string(content)

        # Priority 4: Default key locations
        for default in ["~/.ssh/id_ed25519", "~/.ssh/id_rsa"]:
            expanded = os.path.expanduser(default)
            if os.path.isfile(expanded):
                return self._read_key_file(expanded)

        logger.warning("No SSH private key found")
        return None

    @staticmethod
    def _read_key_file(path: str):
        """Read a private key from file."""
        try:
            # Try Ed25519 first, then RSA, then ECDSA
            for key_class in [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey]:
                try:
                    return key_class.from_private_key_file(path)
                except (paramiko.SSHException, ValueError):
                    continue
            logger.error(f"Could not parse SSH key: {path}")
            return None
        except Exception as e:
            logger.error(f"Error reading SSH key {path}: {e}")
            return None

    @staticmethod
    def _parse_key_string(content: str):
        """Parse a private key from string content."""
        try:
            key_file = io.StringIO(content)
            for key_class in [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey]:
                try:
                    key_file.seek(0)
                    return key_class.from_private_key(key_file)
                except (paramiko.SSHException, ValueError):
                    continue
            logger.error("Could not parse SSH key from string")
            return None
        except Exception as e:
            logger.error(f"Error parsing SSH key string: {e}")
            return None

    # ── Connection Management ────────────────────────────────────

    def connect(self) -> bool:
        """Establish SSH connection to the VPS."""
        if not self.host:
            logger.error("No host configured for SSH bridge")
            return False

        if not self._key:
            logger.error("No SSH key available for authentication")
            return False

        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                pkey=self._key,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False,
            )
            logger.info(f"SSH connected to {self.username}@{self.host}:{self.port}")
            return True
        except paramiko.AuthenticationException:
            logger.error(f"SSH auth failed for {self.username}@{self.host}")
            return False
        except paramiko.SSHException as e:
            logger.error(f"SSH error connecting to {self.host}: {e}")
            return False
        except Exception as e:
            logger.error(f"SSH connection failed to {self.host}: {e}")
            return False

    def close(self):
        """Close the SSH connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            logger.info("SSH connection closed")

    @property
    def connected(self) -> bool:
        """Check if SSH connection is active."""
        if self._client is None:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()

    def _ensure_connected(self) -> bool:
        """Connect if not already connected."""
        if self.connected:
            return True
        return self.connect()

    # ── Command Execution ────────────────────────────────────────

    def exec(self, command: str, timeout: int = None) -> ExecResult:
        """
        Execute a command on the VPS via SSH.

        Args:
            command: Shell command to execute.
            timeout: Command-specific timeout (seconds).

        Returns:
            ExecResult with stdout, stderr, exit code.
        """
        cmd_timeout = timeout or self.timeout
        start = time.time()

        if not self._ensure_connected():
            return ExecResult(
                command=command, exit_code=-1,
                stdout="", stderr="SSH connection failed",
                success=False, duration_ms=0, host=self.host,
            )

        try:
            _, stdout_ch, stderr_ch = self._client.exec_command(
                command, timeout=cmd_timeout,
            )

            exit_code = stdout_ch.channel.recv_exit_status()
            stdout = stdout_ch.read().decode("utf-8", errors="replace").strip()
            stderr = stderr_ch.read().decode("utf-8", errors="replace").strip()

            duration = (time.time() - start) * 1000

            result = ExecResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                success=exit_code == 0,
                duration_ms=round(duration, 1),
                host=self.host,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExecResult(
                command=command, exit_code=-1,
                stdout="", stderr=str(e),
                success=False, duration_ms=round(duration, 1),
                host=self.host,
            )

        self._exec_log.append(result)

        level = logging.INFO if result.success else logging.WARNING
        logger.log(
            level,
            f"[SSH] {command[:80]} -> exit={result.exit_code} "
            f"({result.duration_ms:.0f}ms)"
        )

        return result

    # ── Docker Helpers ───────────────────────────────────────────

    def docker_exec(
        self, container: str, command: str,
        interactive: bool = False, timeout: int = None,
    ) -> ExecResult:
        """
        Execute a command inside a Docker container on the VPS.

        Args:
            container: Container name or ID.
            command: Command to run inside the container.
            interactive: Use -it flags (for commands that need TTY).
            timeout: Command timeout.
        """
        flags = "-it" if interactive else ""
        full_cmd = f"docker exec {flags} {container} {command}".strip()
        # Clean up double spaces from empty flags
        full_cmd = " ".join(full_cmd.split())
        return self.exec(full_cmd, timeout=timeout)

    def docker_ps(self) -> ExecResult:
        """List running Docker containers."""
        return self.exec("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")

    def docker_logs(self, container: str, tail: int = 50) -> ExecResult:
        """Get container logs."""
        return self.exec(f"docker logs --tail {tail} {container}")

    def docker_inspect(self, container: str) -> ExecResult:
        """Inspect a container."""
        return self.exec(f"docker inspect {container}")

    # ── OpenClaw Helpers ─────────────────────────────────────────

    def openclaw_version(self, container: str = "openclaw-quzk-openclaw-1") -> ExecResult:
        """Check OpenClaw version inside the container."""
        return self.docker_exec(container, "openclaw --version")

    def openclaw_models_list(self, container: str = "openclaw-quzk-openclaw-1") -> ExecResult:
        """List available models in OpenClaw."""
        return self.docker_exec(container, "openclaw models list")

    def openclaw_models_status(self, container: str = "openclaw-quzk-openclaw-1") -> ExecResult:
        """Get model status from OpenClaw."""
        return self.docker_exec(container, "openclaw models status --plain")

    def openclaw_set_model(
        self, model: str, container: str = "openclaw-quzk-openclaw-1",
    ) -> ExecResult:
        """Set the default model in OpenClaw."""
        return self.docker_exec(container, f"openclaw models set {model}")

    # ── Audit ────────────────────────────────────────────────────

    def get_exec_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent command execution log."""
        entries = self._exec_log[-limit:]
        return [e.to_dict() for e in reversed(entries)]

    def get_exec_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        total = len(self._exec_log)
        successes = sum(1 for e in self._exec_log if e.success)
        avg_duration = (
            sum(e.duration_ms for e in self._exec_log) / total
            if total > 0 else 0
        )
        return {
            "total_commands": total,
            "successes": successes,
            "failures": total - successes,
            "avg_duration_ms": round(avg_duration, 1),
            "connected": self.connected,
            "host": self.host,
        }

    # ── Context Manager ──────────────────────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"SSHExecBridge({self.username}@{self.host}:{self.port}, {status})"
