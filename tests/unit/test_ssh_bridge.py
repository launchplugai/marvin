#!/usr/bin/env python3
"""
Unit tests for SSH Exec Bridge
"""

import io
import os
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vps.ssh_bridge import SSHExecBridge, ExecResult, HAS_PARAMIKO

# Skip all tests if paramiko not installed
pytestmark = pytest.mark.skipif(not HAS_PARAMIKO, reason="paramiko not installed")


# ── ExecResult Tests ─────────────────────────────────────────────

class TestExecResult:

    def test_success_result(self):
        r = ExecResult(
            command="ls", exit_code=0, stdout="file.txt",
            stderr="", success=True, duration_ms=12.5, host="1.2.3.4",
        )
        assert r.success is True
        assert r.exit_code == 0

    def test_failure_result(self):
        r = ExecResult(
            command="bad_cmd", exit_code=127, stdout="",
            stderr="not found", success=False, duration_ms=5.0,
        )
        assert r.success is False
        assert r.exit_code == 127

    def test_to_dict(self):
        r = ExecResult(
            command="ls", exit_code=0, stdout="out",
            stderr="", success=True, duration_ms=10,
        )
        d = r.to_dict()
        assert d["command"] == "ls"
        assert d["success"] is True


# ── SSHExecBridge Init Tests ─────────────────────────────────────

class TestSSHBridgeInit:

    @patch("vps.ssh_bridge.paramiko")
    def test_init_with_host(self, mock_paramiko):
        bridge = SSHExecBridge(host="1.2.3.4", username="root")
        assert bridge.host == "1.2.3.4"
        assert bridge.username == "root"
        assert bridge.port == 22

    @patch("vps.ssh_bridge.paramiko")
    def test_init_from_env(self, mock_paramiko):
        with patch.dict(os.environ, {"VPS_HOST": "5.6.7.8", "VPS_USER": "admin"}):
            bridge = SSHExecBridge()
            assert bridge.host == "5.6.7.8"

    @patch("vps.ssh_bridge.paramiko")
    def test_repr(self, mock_paramiko):
        bridge = SSHExecBridge(host="1.2.3.4")
        r = repr(bridge)
        assert "1.2.3.4" in r
        assert "disconnected" in r

    @patch("vps.ssh_bridge.paramiko")
    def test_not_connected_initially(self, mock_paramiko):
        bridge = SSHExecBridge(host="1.2.3.4")
        assert bridge.connected is False


# ── Connection Tests ─────────────────────────────────────────────

class TestSSHConnection:

    @patch("vps.ssh_bridge.paramiko")
    def test_connect_no_host(self, mock_paramiko):
        bridge = SSHExecBridge(host="")
        assert bridge.connect() is False

    @patch("vps.ssh_bridge.paramiko")
    def test_connect_no_key(self, mock_paramiko):
        bridge = SSHExecBridge(host="1.2.3.4")
        bridge._key = None
        assert bridge.connect() is False

    @patch("vps.ssh_bridge.paramiko")
    def test_connect_success(self, mock_paramiko):
        mock_key = MagicMock()
        bridge = SSHExecBridge(host="1.2.3.4")
        bridge._key = mock_key

        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy.return_value = MagicMock()

        assert bridge.connect() is True
        mock_client.connect.assert_called_once()

    @patch("vps.ssh_bridge.paramiko")
    def test_connect_auth_failure(self, mock_paramiko):
        import paramiko as real_paramiko
        mock_key = MagicMock()
        bridge = SSHExecBridge(host="1.2.3.4")
        bridge._key = mock_key

        mock_client = MagicMock()
        mock_client.connect.side_effect = real_paramiko.AuthenticationException("denied")
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy.return_value = MagicMock()
        mock_paramiko.AuthenticationException = real_paramiko.AuthenticationException
        mock_paramiko.SSHException = real_paramiko.SSHException

        assert bridge.connect() is False

    @patch("vps.ssh_bridge.paramiko")
    def test_close(self, mock_paramiko):
        bridge = SSHExecBridge(host="1.2.3.4")
        bridge._client = MagicMock()
        bridge.close()
        assert bridge._client is None


# ── Execution Tests ──────────────────────────────────────────────

class TestSSHExec:

    def _make_bridge(self):
        """Create a bridge with mocked SSH client."""
        bridge = SSHExecBridge.__new__(SSHExecBridge)
        bridge.host = "1.2.3.4"
        bridge.username = "root"
        bridge.port = 22
        bridge.timeout = 30
        bridge._key = MagicMock()
        bridge._exec_log = []

        # Mock connected client
        mock_client = MagicMock()
        mock_transport = MagicMock()
        mock_transport.is_active.return_value = True
        mock_client.get_transport.return_value = mock_transport
        bridge._client = mock_client

        return bridge, mock_client

    def test_exec_success(self):
        bridge, mock_client = self._make_bridge()

        # Mock exec_command return
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b"container-abc\n"
        mock_stderr.read.return_value = b""
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

        result = bridge.exec("docker ps")

        assert result.success is True
        assert result.exit_code == 0
        assert "container-abc" in result.stdout
        assert result.host == "1.2.3.4"
        assert result.duration_ms > 0

    def test_exec_failure(self):
        bridge, mock_client = self._make_bridge()

        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b""
        mock_stderr.read.return_value = b"command not found"
        mock_stdout.channel.recv_exit_status.return_value = 127
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

        result = bridge.exec("nonexistent")

        assert result.success is False
        assert result.exit_code == 127
        assert "not found" in result.stderr

    def test_exec_not_connected(self):
        bridge = SSHExecBridge.__new__(SSHExecBridge)
        bridge.host = ""
        bridge.username = "root"
        bridge.port = 22
        bridge.timeout = 30
        bridge._key = None
        bridge._exec_log = []
        bridge._client = None

        result = bridge.exec("ls")
        assert result.success is False
        assert "connection failed" in result.stderr.lower()

    def test_exec_logs_to_history(self):
        bridge, mock_client = self._make_bridge()

        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b"ok"
        mock_stderr.read.return_value = b""
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

        bridge.exec("cmd1")
        bridge.exec("cmd2")

        assert len(bridge._exec_log) == 2
        log = bridge.get_exec_log()
        assert len(log) == 2

    def test_exec_exception_handling(self):
        bridge, mock_client = self._make_bridge()
        mock_client.exec_command.side_effect = Exception("network error")

        result = bridge.exec("ls")
        assert result.success is False
        assert "network error" in result.stderr


# ── Docker Helper Tests ──────────────────────────────────────────

class TestDockerHelpers:

    def _make_bridge(self):
        bridge, mock_client = TestSSHExec()._make_bridge()

        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b"ok"
        mock_stderr.read.return_value = b""
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

        return bridge, mock_client

    def test_docker_exec(self):
        bridge, mock_client = self._make_bridge()
        result = bridge.docker_exec("mycontainer", "ls /app")

        assert result.success is True
        cmd = mock_client.exec_command.call_args[0][0]
        assert "docker exec" in cmd
        assert "mycontainer" in cmd
        assert "ls /app" in cmd

    def test_docker_exec_interactive(self):
        bridge, mock_client = self._make_bridge()
        bridge.docker_exec("mycontainer", "bash", interactive=True)

        cmd = mock_client.exec_command.call_args[0][0]
        assert "-it" in cmd

    def test_docker_ps(self):
        bridge, mock_client = self._make_bridge()
        result = bridge.docker_ps()
        assert result.success is True
        cmd = mock_client.exec_command.call_args[0][0]
        assert "docker ps" in cmd

    def test_docker_logs(self):
        bridge, mock_client = self._make_bridge()
        bridge.docker_logs("mycontainer", tail=20)
        cmd = mock_client.exec_command.call_args[0][0]
        assert "docker logs" in cmd
        assert "--tail 20" in cmd


# ── OpenClaw Helper Tests ────────────────────────────────────────

class TestOpenClawHelpers:

    def _make_bridge(self):
        return TestDockerHelpers()._make_bridge()

    def test_openclaw_version(self):
        bridge, mock_client = self._make_bridge()
        bridge.openclaw_version()
        cmd = mock_client.exec_command.call_args[0][0]
        assert "openclaw --version" in cmd
        assert "openclaw-quzk-openclaw-1" in cmd

    def test_openclaw_models_list(self):
        bridge, mock_client = self._make_bridge()
        bridge.openclaw_models_list()
        cmd = mock_client.exec_command.call_args[0][0]
        assert "openclaw models list" in cmd

    def test_openclaw_set_model(self):
        bridge, mock_client = self._make_bridge()
        bridge.openclaw_set_model("openai-codex/gpt-5.3-codex")
        cmd = mock_client.exec_command.call_args[0][0]
        assert "openclaw models set openai-codex/gpt-5.3-codex" in cmd

    def test_openclaw_custom_container(self):
        bridge, mock_client = self._make_bridge()
        bridge.openclaw_version(container="my-custom-container")
        cmd = mock_client.exec_command.call_args[0][0]
        assert "my-custom-container" in cmd


# ── Audit & Stats Tests ──────────────────────────────────────────

class TestAuditStats:

    def test_exec_stats(self):
        bridge = SSHExecBridge.__new__(SSHExecBridge)
        bridge.host = "1.2.3.4"
        bridge._client = None
        bridge._exec_log = [
            ExecResult("cmd1", 0, "ok", "", True, 100.0),
            ExecResult("cmd2", 1, "", "err", False, 200.0),
        ]

        stats = bridge.get_exec_stats()
        assert stats["total_commands"] == 2
        assert stats["successes"] == 1
        assert stats["failures"] == 1
        assert stats["avg_duration_ms"] == 150.0

    def test_exec_log_limit(self):
        bridge = SSHExecBridge.__new__(SSHExecBridge)
        bridge._exec_log = [
            ExecResult(f"cmd{i}", 0, "", "", True, 10.0)
            for i in range(10)
        ]

        log = bridge.get_exec_log(limit=3)
        assert len(log) == 3

    def test_context_manager(self):
        """Test that the bridge works as a context manager."""
        with patch("vps.ssh_bridge.paramiko"):
            bridge = SSHExecBridge(host="1.2.3.4")
            bridge._key = MagicMock()
            bridge._client = MagicMock()
            transport = MagicMock()
            transport.is_active.return_value = True
            bridge._client.get_transport.return_value = transport

            # Test __enter__ and __exit__
            with patch.object(bridge, 'connect', return_value=True) as mock_connect:
                with bridge as b:
                    assert b is bridge
                    mock_connect.assert_called_once()
            # After exit, close should have been called
            assert bridge._client is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
