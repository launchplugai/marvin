#!/usr/bin/env python3
"""
Unit tests for Hostinger VPS API Client
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vps.hostinger import HostingerVPSClient, VMInfo, ActionResult, BASE_URL


class TestHostingerClientInit:
    """Test Hostinger client initialization."""

    def test_init_with_explicit_token(self):
        client = HostingerVPSClient(api_token="tok-123")
        assert client.api_token == "tok-123"
        assert client.timeout == HostingerVPSClient.DEFAULT_TIMEOUT

    def test_init_from_env_hostinger_token(self):
        with patch.dict("os.environ", {"HOSTINGER_API_TOKEN": "env-tok"}):
            client = HostingerVPSClient()
            assert client.api_token == "env-tok"

    def test_init_from_env_api_token_fallback(self):
        with patch.dict("os.environ", {"API_TOKEN": "fallback-tok"}, clear=False):
            # Clear HOSTINGER_API_TOKEN if set
            import os
            os.environ.pop("HOSTINGER_API_TOKEN", None)
            client = HostingerVPSClient()
            assert client.api_token == "fallback-tok"

    def test_init_counters_zero(self):
        client = HostingerVPSClient(api_token="tok")
        assert client._request_count == 0
        assert client._error_count == 0

    def test_custom_timeout(self):
        client = HostingerVPSClient(api_token="tok", timeout=60)
        assert client.timeout == 60


class TestHostingerHeaders:

    def test_headers_include_bearer_token(self):
        client = HostingerVPSClient(api_token="my-token")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer my-token"
        assert headers["Content-Type"] == "application/json"

    def test_headers_no_auth_without_token(self):
        client = HostingerVPSClient(api_token=None)
        client.api_token = None
        headers = client._headers()
        assert "Authorization" not in headers


class TestListVMs:

    @pytest.fixture
    def client(self):
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_list_vms_success(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": 101,
                "hostname": "marvin-prod",
                "state": "running",
                "cpus": 4,
                "memory_mb": 8192,
                "disk_gb": 160,
                "ips": [{"address": "123.45.67.89"}],
                "data_center": {"name": "eu-west"},
            },
            {
                "id": 102,
                "hostname": "marvin-staging",
                "state": "stopped",
                "cpus": 2,
                "memory_mb": 4096,
                "ips": [],
            },
        ]
        mock_req.return_value = mock_resp

        vms = client.list_vms()

        assert len(vms) == 2
        assert vms[0].id == 101
        assert vms[0].hostname == "marvin-prod"
        assert vms[0].state == "running"
        assert vms[0].ip_address == "123.45.67.89"
        assert vms[0].data_center == "eu-west"
        assert vms[1].state == "stopped"

    @patch("vps.hostinger.requests.request")
    def test_list_vms_connection_error(self, mock_req, client):
        import requests as req
        mock_req.side_effect = req.ConnectionError()
        assert client.list_vms() == []

    @patch("vps.hostinger.requests.request")
    def test_list_vms_401(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_req.return_value = mock_resp
        assert client.list_vms() == []


class TestGetVM:

    @pytest.fixture
    def client(self):
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_get_vm_success(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 101,
            "hostname": "marvin-prod",
            "state": "running",
            "cpus": 4,
            "ip_address": "10.0.0.1",
        }
        mock_req.return_value = mock_resp

        vm = client.get_vm(101)

        assert vm is not None
        assert vm.id == 101
        assert vm.hostname == "marvin-prod"

    @patch("vps.hostinger.requests.request")
    def test_get_vm_not_found(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        mock_req.return_value = mock_resp

        assert client.get_vm(999) is None


class TestVMLifecycle:

    @pytest.fixture
    def client(self):
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_start_vm(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "VM started"}
        mock_req.return_value = mock_resp

        result = client.start_vm(101)
        assert result.success is True
        assert result.action == "start"
        assert result.vm_id == 101

    @patch("vps.hostinger.requests.request")
    def test_stop_vm(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "VM stopped"}
        mock_req.return_value = mock_resp

        result = client.stop_vm(101)
        assert result.success is True
        assert result.action == "stop"

    @patch("vps.hostinger.requests.request")
    def test_restart_vm(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "VM restarted"}
        mock_req.return_value = mock_resp

        result = client.restart_vm(101)
        assert result.success is True
        assert result.action == "restart"

    @patch("vps.hostinger.requests.request")
    def test_start_vm_failure(self, mock_req, client):
        import requests as req
        mock_req.side_effect = req.ConnectionError()

        result = client.start_vm(101)
        assert result.success is False
        assert result.message == "Connection failed"


class TestSnapshots:

    @pytest.fixture
    def client(self):
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_get_snapshot(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 50, "created_at": "2026-02-24T12:00:00Z"
        }
        mock_req.return_value = mock_resp

        snap = client.get_snapshot(101)
        assert snap is not None
        assert snap["id"] == 50

    @patch("vps.hostinger.requests.request")
    def test_create_snapshot(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Snapshot created"}
        mock_req.return_value = mock_resp

        result = client.create_snapshot(101)
        assert result.success is True
        assert result.action == "create_snapshot"

    @patch("vps.hostinger.requests.request")
    def test_restore_snapshot(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Snapshot restored"}
        mock_req.return_value = mock_resp

        result = client.restore_snapshot(101)
        assert result.success is True
        assert result.action == "restore_snapshot"

    @patch("vps.hostinger.requests.request")
    def test_delete_snapshot(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Snapshot deleted"}
        mock_req.return_value = mock_resp

        result = client.delete_snapshot(101)
        assert result.success is True


class TestFirewalls:

    @pytest.fixture
    def client(self):
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_list_firewalls(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "name": "default"},
            {"id": 2, "name": "strict"},
        ]
        mock_req.return_value = mock_resp

        fws = client.list_firewalls()
        assert len(fws) == 2

    @patch("vps.hostinger.requests.request")
    def test_create_firewall(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Firewall created", "id": 3}
        mock_req.return_value = mock_resp

        result = client.create_firewall("marvin-fw")
        assert result.success is True

    @patch("vps.hostinger.requests.request")
    def test_activate_firewall(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Firewall activated"}
        mock_req.return_value = mock_resp

        result = client.activate_firewall(1, 101)
        assert result.success is True
        assert result.vm_id == 101

    @patch("vps.hostinger.requests.request")
    def test_create_firewall_rule(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Rule created"}
        mock_req.return_value = mock_resp

        result = client.create_firewall_rule(
            firewall_id=1, protocol="tcp", port="22",
            source="0.0.0.0/0", action="accept",
        )
        assert result.success is True

    @patch("vps.hostinger.requests.request")
    def test_delete_firewall_rule(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Rule deleted"}
        mock_req.return_value = mock_resp

        result = client.delete_firewall_rule(1, 42)
        assert result.success is True


class TestBackupsAndMetrics:

    @pytest.fixture
    def client(self):
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_get_backups(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "created_at": "2026-02-23"},
            {"id": 2, "created_at": "2026-02-24"},
        ]
        mock_req.return_value = mock_resp

        backups = client.get_backups(101)
        assert len(backups) == 2

    @patch("vps.hostinger.requests.request")
    def test_get_metrics(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "cpu": [{"timestamp": 1, "value": 15.2}],
            "memory": [{"timestamp": 1, "value": 42.0}],
        }
        mock_req.return_value = mock_resp

        metrics = client.get_metrics(101)
        assert "cpu" in metrics

    @patch("vps.hostinger.requests.request")
    def test_get_data_centers(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "name": "eu-west", "location": "Netherlands"},
        ]
        mock_req.return_value = mock_resp

        dcs = client.get_data_centers()
        assert len(dcs) == 1
        assert dcs[0]["name"] == "eu-west"


class TestAccessManagement:

    @pytest.fixture
    def client(self):
        return HostingerVPSClient(api_token="tok")

    @patch("vps.hostinger.requests.request")
    def test_set_root_password(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Password set"}
        mock_req.return_value = mock_resp

        result = client.set_root_password(101, "newpass123!")
        assert result.success is True
        assert result.action == "set_root_password"

    @patch("vps.hostinger.requests.request")
    def test_attach_public_key(self, mock_req, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "Keys attached"}
        mock_req.return_value = mock_resp

        result = client.attach_public_key(101, [1, 2])
        assert result.success is True


class TestClientStats:

    def test_initial_stats(self):
        client = HostingerVPSClient(api_token="tok")
        stats = client.get_stats()
        assert stats["token_configured"] is True
        assert stats["total_requests"] == 0
        assert stats["error_rate_percent"] == 0

    @patch("vps.hostinger.requests.request")
    def test_stats_after_mixed_requests(self, mock_req):
        client = HostingerVPSClient(api_token="tok")

        # Successful request
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_req.return_value = mock_resp
        client.list_vms()

        # Failed request
        import requests as req
        mock_req.side_effect = req.ConnectionError()
        client.list_vms()

        stats = client.get_stats()
        assert stats["total_requests"] == 2
        assert stats["total_errors"] == 1
        assert stats["error_rate_percent"] == 50.0


class TestDataclasses:

    def test_vminfo_to_dict(self):
        vm = VMInfo(id=1, hostname="test", state="running", ip_address="1.2.3.4")
        d = vm.to_dict()
        assert d["id"] == 1
        assert d["hostname"] == "test"
        assert "raw" not in d

    def test_action_result_to_dict(self):
        r = ActionResult(success=True, action="start", vm_id=1, message="ok")
        d = r.to_dict()
        assert d["success"] is True
        assert "data" not in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
