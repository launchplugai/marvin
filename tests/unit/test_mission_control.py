#!/usr/bin/env python3
"""
Unit tests for Mission Control — Ira's Infrastructure Command Center
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vps.mission_control import (
    MissionControl, SystemStatus, ContainerStatus, AuditEntry,
    Severity, ContainerHealth,
)
from vps.hostinger import VMInfo, ActionResult


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def mock_client():
    """Create a MissionControl with a mocked Hostinger client."""
    with patch("vps.mission_control.HostingerVPSClient") as MockClient:
        instance = MockClient.return_value
        instance.api_token = "test-token"
        instance._request_count = 0
        instance._error_count = 0

        # Default: list_vms returns one VM (auto-discover)
        instance.list_vms.return_value = [
            VMInfo(id=1405440, hostname="srv1405440.hstgr.cloud",
                   state="running", ip_address="187.77.211.80",
                   cpus=2, memory_mb=8192, disk_gb=102400,
                   os="Ubuntu 24.04 with Docker")
        ]

        mc = MissionControl(api_token="test-token")
        yield mc, instance


@pytest.fixture
def mc_no_vm():
    """MissionControl with no VM discovered."""
    with patch("vps.mission_control.HostingerVPSClient") as MockClient:
        instance = MockClient.return_value
        instance.api_token = "test-token"
        instance.list_vms.return_value = []

        mc = MissionControl(api_token="test-token")
        yield mc, instance


# ── Initialization Tests ─────────────────────────────────────────

class TestMissionControlInit:

    def test_auto_discover_vm(self, mock_client):
        mc, client = mock_client
        assert mc.vm_id == 1405440
        client.list_vms.assert_called_once()

    def test_explicit_vm_id(self):
        with patch("vps.mission_control.HostingerVPSClient"):
            mc = MissionControl(api_token="tok", vm_id=999, auto_discover=False)
            assert mc.vm_id == 999

    def test_no_vm_found(self, mc_no_vm):
        mc, _ = mc_no_vm
        assert mc.vm_id is None

    def test_audit_log_starts_empty(self, mock_client):
        mc, _ = mock_client
        assert mc.get_audit_log() == []

    def test_repr(self, mock_client):
        mc, _ = mock_client
        assert "MissionControl" in repr(mc)
        assert "1405440" in repr(mc)


# ── Status Dashboard Tests ───────────────────────────────────────

class TestStatus:

    def test_full_status_healthy(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv1405440.hstgr.cloud",
            state="running", ip_address="187.77.211.80",
            cpus=2, memory_mb=8192, disk_gb=102400,
            os="Ubuntu 24.04 with Docker",
        )
        client.list_docker_projects.return_value = [
            {
                "name": "ollama",
                "state": "running",
                "containers": [{
                    "name": "ollama-1",
                    "image": "ollama/ollama:latest",
                    "state": "running",
                    "health": "healthy",
                    "ports": [{"type": "published", "host_port": 32768,
                               "container_port": 11434}],
                }],
            },
        ]
        client.list_firewalls.return_value = [
            {"id": 1, "is_synced": True, "rules": [{"id": 10, "port": "22"}]},
        ]

        ss = mc.status()

        assert ss.healthy
        assert ss.vm_state == "running"
        assert ss.hostname == "srv1405440.hstgr.cloud"
        assert ss.ip_address == "187.77.211.80"
        assert ss.containers_running == 1
        assert ss.containers_total == 1
        assert ss.firewall_active is True
        assert ss.firewall_rules == 1
        assert len(ss.alerts) == 0

    def test_status_vm_stopped(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="stopped",
        )
        client.list_docker_projects.return_value = []
        client.list_firewalls.return_value = []

        ss = mc.status()

        assert not ss.healthy
        assert ss.vm_state == "stopped"
        assert any(a["severity"] == "critical" for a in ss.alerts)

    def test_status_unhealthy_container(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="running",
        )
        client.list_docker_projects.return_value = [
            {
                "name": "app",
                "containers": [{
                    "name": "app-1",
                    "image": "myapp:latest",
                    "state": "running",
                    "health": "unhealthy",
                    "ports": [],
                }],
            },
        ]
        client.list_firewalls.return_value = []

        ss = mc.status()

        assert any("unhealthy" in a["message"] for a in ss.alerts)

    def test_status_stopped_container(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="running",
        )
        client.list_docker_projects.return_value = [
            {
                "name": "db",
                "containers": [{
                    "name": "db-1",
                    "image": "postgres:16",
                    "state": "exited",
                    "health": "",
                    "ports": [],
                }],
            },
        ]
        client.list_firewalls.return_value = []

        ss = mc.status()

        assert ss.containers_running == 0
        assert ss.containers_total == 1
        assert any("exited" in a["message"] for a in ss.alerts)

    def test_status_api_unreachable(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = None
        client.list_docker_projects.return_value = []
        client.list_firewalls.return_value = []

        ss = mc.status()

        assert not ss.healthy
        assert any("Cannot reach VM" in a["message"] for a in ss.alerts)

    def test_status_no_vm_configured(self, mc_no_vm):
        mc, client = mc_no_vm
        client.list_docker_projects.return_value = []
        client.list_firewalls.return_value = []

        ss = mc.status()

        assert ss.containers_total == 0

    def test_quick_status(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="running",
        )
        client.list_docker_projects.return_value = [
            {"name": "app", "containers": [
                {"name": "a", "image": "i", "state": "running",
                 "health": "healthy", "ports": []},
            ]},
        ]
        client.list_firewalls.return_value = []

        qs = mc.quick_status()

        assert qs["healthy"] is True
        assert qs["vm"] == "running"
        assert qs["containers"] == "1/1"
        assert qs["alerts"] == 0

    def test_system_status_to_dict(self):
        ss = SystemStatus(vm_id=1, vm_state="running", hostname="test")
        d = ss.to_dict()
        assert d["vm_id"] == 1
        assert d["vm_state"] == "running"


# ── Docker Deployment Tests ──────────────────────────────────────

REDIS_COMPOSE = """
version: '3'
services:
  redis:
    image: redis:7
    ports:
      - "6379:6379"
"""


class TestDeploy:

    def test_deploy_success(self, mock_client):
        mc, client = mock_client
        client.deploy_docker_project.return_value = ActionResult(
            success=True, action="deploy_docker", vm_id=1405440,
            message="Deployed successfully",
        )

        result = mc.deploy("redis", REDIS_COMPOSE)

        assert result.success is True
        client.deploy_docker_project.assert_called_once_with(
            1405440, REDIS_COMPOSE, "redis", None,
        )

    def test_deploy_with_env_vars(self, mock_client):
        mc, client = mock_client
        client.deploy_docker_project.return_value = ActionResult(
            success=True, action="deploy_docker", vm_id=1405440,
        )

        mc.deploy("myapp", "compose: yaml", env_vars={"DB_URL": "postgres://..."})

        client.deploy_docker_project.assert_called_once_with(
            1405440, "compose: yaml", "myapp", {"DB_URL": "postgres://..."},
        )

    def test_deploy_with_auto_firewall(self, mock_client):
        mc, client = mock_client
        client.deploy_docker_project.return_value = ActionResult(
            success=True, action="deploy_docker", vm_id=1405440,
        )
        client.list_firewalls.return_value = [
            {"id": 1, "rules": []},
        ]
        client.create_firewall_rule.return_value = ActionResult(
            success=True, action="create_firewall_rule",
        )
        client.activate_firewall.return_value = ActionResult(
            success=True, action="activate_firewall",
        )

        result = mc.deploy(
            "redis", REDIS_COMPOSE,
            open_ports=[{"port": "6379", "protocol": "TCP"}],
        )

        assert result.success is True
        client.create_firewall_rule.assert_called_once()

    def test_deploy_no_firewall_on_failure(self, mock_client):
        mc, client = mock_client
        client.deploy_docker_project.return_value = ActionResult(
            success=False, action="deploy_docker", vm_id=1405440,
            message="Failed",
        )

        result = mc.deploy(
            "redis", REDIS_COMPOSE,
            open_ports=[{"port": "6379", "protocol": "TCP"}],
        )

        assert result.success is False
        client.create_firewall_rule.assert_not_called()

    def test_deploy_no_vm(self, mc_no_vm):
        mc, _ = mc_no_vm
        result = mc.deploy("redis", REDIS_COMPOSE)
        assert result.success is False
        assert "No VM" in result.message

    def test_deploy_creates_audit_entry(self, mock_client):
        mc, client = mock_client
        client.deploy_docker_project.return_value = ActionResult(
            success=True, action="deploy_docker", vm_id=1405440,
        )

        mc.deploy("redis", REDIS_COMPOSE)

        log = mc.get_audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "deploy"
        assert log[0]["target"] == "redis"
        assert log[0]["success"] is True


class TestRemove:

    def test_remove_success(self, mock_client):
        mc, client = mock_client
        client.remove_docker_project.return_value = ActionResult(
            success=True, action="remove_docker", vm_id=1405440,
        )

        result = mc.remove("redis")

        assert result.success is True
        client.remove_docker_project.assert_called_once_with(1405440, "redis")

    def test_remove_no_vm(self, mc_no_vm):
        mc, _ = mc_no_vm
        result = mc.remove("redis")
        assert result.success is False


class TestListServices:

    def test_list_services(self, mock_client):
        mc, client = mock_client
        client.list_docker_projects.return_value = [
            {
                "name": "ollama",
                "state": "running",
                "path": "/docker/ollama/docker-compose.yml",
                "containers": [
                    {"state": "running", "ports": [
                        {"type": "published", "host_port": 32768,
                         "container_port": 11434},
                    ]},
                ],
            },
            {
                "name": "openclaw",
                "state": "running",
                "path": "/docker/openclaw/docker-compose.yml",
                "containers": [
                    {"state": "running", "ports": [
                        {"type": "published", "host_port": 46282,
                         "container_port": 46282},
                    ]},
                ],
            },
        ]

        services = mc.list_services()

        assert len(services) == 2
        assert services[0]["name"] == "ollama"
        assert "32768:11434" in services[0]["ports"]
        assert services[1]["name"] == "openclaw"

    def test_list_services_no_vm(self, mc_no_vm):
        mc, _ = mc_no_vm
        assert mc.list_services() == []


# ── Firewall Tests ───────────────────────────────────────────────

class TestFirewall:

    def test_ensure_port_existing_rule(self, mock_client):
        mc, client = mock_client
        client.list_firewalls.return_value = [
            {"id": 1, "rules": [
                {"id": 10, "port": "22", "protocol": "TCP"},
            ]},
        ]

        mc._ensure_firewall_port("22", "TCP")

        # Should not create a new rule since it already exists
        client.create_firewall_rule.assert_not_called()

    def test_ensure_port_new_rule(self, mock_client):
        mc, client = mock_client
        client.list_firewalls.return_value = [
            {"id": 1, "rules": []},
        ]
        client.create_firewall_rule.return_value = ActionResult(
            success=True, action="create_firewall_rule",
        )
        client.activate_firewall.return_value = ActionResult(
            success=True, action="activate_firewall",
        )

        mc._ensure_firewall_port("8080", "TCP")

        client.create_firewall_rule.assert_called_once_with(
            1, protocol="TCP", port="8080",
        )

    def test_lockdown(self, mock_client):
        mc, client = mock_client
        client.list_firewalls.return_value = [
            {"id": 1, "rules": [
                {"id": 10, "port": "22", "protocol": "TCP"},
                {"id": 11, "port": "8080", "protocol": "TCP"},
                {"id": 12, "port": "3000", "protocol": "TCP"},
            ]},
        ]
        client.delete_firewall_rule.return_value = ActionResult(
            success=True, action="delete_firewall_rule",
        )

        mc.lockdown(keep_ports=["22"])

        # Should delete rules for ports 8080 and 3000, keep 22
        assert client.delete_firewall_rule.call_count == 2

    def test_lockdown_default_keeps_ssh(self, mock_client):
        mc, client = mock_client
        client.list_firewalls.return_value = [
            {"id": 1, "rules": [
                {"id": 10, "port": "22", "protocol": "TCP"},
                {"id": 11, "port": "80", "protocol": "TCP"},
            ]},
        ]
        client.delete_firewall_rule.return_value = ActionResult(
            success=True, action="delete_firewall_rule",
        )

        mc.lockdown()  # Default keeps port 22

        assert client.delete_firewall_rule.call_count == 1


# ── Health & Self-Healing Tests ──────────────────────────────────

class TestHeal:

    def test_heal_all_healthy(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="running",
        )
        client.list_docker_projects.return_value = [
            {"name": "app", "containers": [
                {"name": "a", "image": "i", "state": "running",
                 "health": "healthy", "ports": []},
            ]},
        ]
        client.list_firewalls.return_value = []

        actions = mc.heal()

        assert len(actions) == 1
        assert actions[0]["action"] == "no_issues"

    def test_heal_vm_stopped_powers_on(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="stopped",
        )
        client.list_docker_projects.return_value = []
        client.list_firewalls.return_value = []
        client.start_vm.return_value = ActionResult(
            success=True, action="start", vm_id=1405440,
            message="VM started",
        )

        actions = mc.heal()

        assert any(a["action"] == "power_on_vm" for a in actions)
        client.start_vm.assert_called_once_with(1405440)

    def test_heal_vm_error_restarts(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="error",
        )
        client.list_docker_projects.return_value = []
        client.list_firewalls.return_value = []
        client.restart_vm.return_value = ActionResult(
            success=True, action="restart", vm_id=1405440,
        )

        actions = mc.heal()

        assert any(a["action"] == "restart_vm" for a in actions)
        client.restart_vm.assert_called_once()

    def test_heal_unhealthy_container_alerts(self, mock_client):
        mc, client = mock_client
        client.get_vm.return_value = VMInfo(
            id=1405440, hostname="srv", state="running",
        )
        client.list_docker_projects.return_value = [
            {"name": "app", "containers": [
                {"name": "app-1", "image": "myapp", "state": "running",
                 "health": "unhealthy", "ports": []},
            ]},
        ]
        client.list_firewalls.return_value = []

        actions = mc.heal()

        assert any(a["action"] == "container_alert" for a in actions)
        assert any(a.get("container") == "app-1" for a in actions)


# ── Power Management Tests ───────────────────────────────────────

class TestPowerManagement:

    def test_power_on(self, mock_client):
        mc, client = mock_client
        client.start_vm.return_value = ActionResult(
            success=True, action="start", vm_id=1405440,
        )
        result = mc.power_on()
        assert result.success is True
        client.start_vm.assert_called_once_with(1405440)

    def test_power_off(self, mock_client):
        mc, client = mock_client
        client.stop_vm.return_value = ActionResult(
            success=True, action="stop", vm_id=1405440,
        )
        result = mc.power_off()
        assert result.success is True

    def test_reboot(self, mock_client):
        mc, client = mock_client
        client.restart_vm.return_value = ActionResult(
            success=True, action="restart", vm_id=1405440,
        )
        result = mc.reboot()
        assert result.success is True

    def test_power_no_vm(self, mc_no_vm):
        mc, _ = mc_no_vm
        assert mc.power_on().success is False
        assert mc.power_off().success is False
        assert mc.reboot().success is False


# ── Snapshot Tests ───────────────────────────────────────────────

class TestSnapshots:

    def test_snapshot(self, mock_client):
        mc, client = mock_client
        client.create_snapshot.return_value = ActionResult(
            success=True, action="create_snapshot", vm_id=1405440,
        )
        result = mc.snapshot()
        assert result.success is True

    def test_rollback(self, mock_client):
        mc, client = mock_client
        client.restore_snapshot.return_value = ActionResult(
            success=True, action="restore_snapshot", vm_id=1405440,
        )
        result = mc.rollback()
        assert result.success is True

    def test_snapshot_no_vm(self, mc_no_vm):
        mc, _ = mc_no_vm
        assert mc.snapshot().success is False
        assert mc.rollback().success is False


# ── SSH Key Tests ────────────────────────────────────────────────

class TestSSHKeys:

    def test_register_and_attach(self, mock_client):
        mc, client = mock_client
        client.create_public_key.return_value = ActionResult(
            success=True, action="create_public_key",
            data={"id": 42},
        )
        client.attach_public_key.return_value = ActionResult(
            success=True, action="attach_public_key", vm_id=1405440,
        )

        result = mc.register_ssh_key("my-key", "ssh-ed25519 AAAA...")

        assert result.success is True
        client.create_public_key.assert_called_once_with("my-key", "ssh-ed25519 AAAA...")
        client.attach_public_key.assert_called_once_with(1405440, [42])

    def test_register_key_fails(self, mock_client):
        mc, client = mock_client
        client.create_public_key.return_value = ActionResult(
            success=False, action="create_public_key",
            message="Invalid key format",
        )

        result = mc.register_ssh_key("bad-key", "not-a-key")

        assert result.success is False
        client.attach_public_key.assert_not_called()


# ── Audit Log Tests ──────────────────────────────────────────────

class TestAuditLog:

    def test_audit_trail(self, mock_client):
        mc, client = mock_client
        client.deploy_docker_project.return_value = ActionResult(
            success=True, action="deploy_docker", vm_id=1405440,
        )
        client.remove_docker_project.return_value = ActionResult(
            success=True, action="remove_docker", vm_id=1405440,
        )

        mc.deploy("redis", REDIS_COMPOSE)
        mc.remove("redis")

        log = mc.get_audit_log()
        assert len(log) == 2
        # Most recent first
        assert log[0]["action"] == "remove"
        assert log[1]["action"] == "deploy"

    def test_audit_summary(self, mock_client):
        mc, client = mock_client
        client.deploy_docker_project.return_value = ActionResult(
            success=True, action="deploy_docker", vm_id=1405440,
        )
        client.remove_docker_project.return_value = ActionResult(
            success=False, action="remove_docker", vm_id=1405440,
            message="Not found",
        )

        mc.deploy("app1", "yaml1")
        mc.deploy("app2", "yaml2")
        mc.remove("app3")

        summary = mc.get_audit_summary()
        assert summary["total_actions"] == 3
        assert summary["successes"] == 2
        assert summary["failures"] == 1
        assert summary["actions_by_type"]["deploy"] == 2
        assert summary["actions_by_type"]["remove"] == 1

    def test_audit_limit(self, mock_client):
        mc, client = mock_client
        client.start_vm.return_value = ActionResult(
            success=True, action="start", vm_id=1405440,
        )

        for _ in range(10):
            mc.power_on()

        log = mc.get_audit_log(limit=3)
        assert len(log) == 3


# ── Data Model Tests ─────────────────────────────────────────────

class TestDataModels:

    def test_container_status_to_dict(self):
        cs = ContainerStatus(
            name="redis-1", image="redis:7", state="running",
            health="healthy", project="cache",
        )
        d = cs.to_dict()
        assert d["name"] == "redis-1"
        assert d["project"] == "cache"

    def test_audit_entry_to_dict(self):
        ae = AuditEntry(action="deploy", target="redis", success=True)
        d = ae.to_dict()
        assert d["action"] == "deploy"
        assert d["success"] is True

    def test_system_status_healthy_property(self):
        ss = SystemStatus(vm_state="running", api_healthy=True)
        assert ss.healthy is True

        ss.alerts.append({"severity": "critical", "message": "bad"})
        assert ss.healthy is False

    def test_system_status_not_running(self):
        ss = SystemStatus(vm_state="stopped", api_healthy=True)
        assert ss.healthy is False

    def test_severity_enum(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_container_health_enum(self):
        assert ContainerHealth.HEALTHY.value == "healthy"
        assert ContainerHealth.UNHEALTHY.value == "unhealthy"


# ── Docker Endpoint Tests (Hostinger Client) ────────────────────

class TestHostingerDockerEndpoints:
    """Test the new Docker endpoints added to HostingerVPSClient."""

    @pytest.fixture
    def client(self):
        from vps.hostinger import HostingerVPSClient
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_list_docker_projects(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "ollama", "state": "running", "containers": []},
        ]
        mock_req.return_value = mock_resp

        projects = client.list_docker_projects(1405440)
        assert len(projects) == 1
        assert projects[0]["name"] == "ollama"

    @patch("vps.hostinger.requests.request")
    def test_get_docker_project(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "ollama", "state": "running",
            "containers": [{"name": "ollama-1", "state": "running"}],
        }
        mock_req.return_value = mock_resp

        proj = client.get_docker_project(1405440, "ollama")
        assert proj is not None
        assert proj["name"] == "ollama"

    @patch("vps.hostinger.requests.request")
    def test_deploy_docker_project(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Deployed"}
        mock_req.return_value = mock_resp

        result = client.deploy_docker_project(
            1405440, "version: '3'\nservices:\n  redis:\n    image: redis:7",
            "redis", {"REDIS_PASS": "secret"},
        )
        assert result.success is True

    @patch("vps.hostinger.requests.request")
    def test_remove_docker_project(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Removed"}
        mock_req.return_value = mock_resp

        result = client.remove_docker_project(1405440, "redis")
        assert result.success is True

    @patch("vps.hostinger.requests.request")
    def test_list_docker_connection_error(self, mock_req, client):
        import requests as req
        mock_req.side_effect = req.ConnectionError()
        assert client.list_docker_projects(1405440) == []

    @patch("vps.hostinger.requests.request")
    def test_list_public_keys(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"id": 1, "name": "my-key", "key": "ssh-ed25519 AAAA..."}],
        }
        mock_req.return_value = mock_resp

        keys = client.list_public_keys()
        assert len(keys) == 1
        assert keys[0]["name"] == "my-key"

    @patch("vps.hostinger.requests.request")
    def test_create_public_key(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 42, "name": "new-key"}
        mock_req.return_value = mock_resp

        result = client.create_public_key("new-key", "ssh-ed25519 AAAA...")
        assert result.success is True

    @patch("vps.hostinger.requests.request")
    def test_delete_public_key(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Deleted"}
        mock_req.return_value = mock_resp

        result = client.delete_public_key(42)
        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
