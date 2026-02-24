#!/usr/bin/env python3
"""
Unit tests for Marvin VPS API Client
Phase 1: Health checks, service management, deployment
"""

import pytest
import json
import time
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vps.client import VPSClient, VPSStatus, ServiceInfo, DeployResult, ServiceState


class TestVPSClientInit:
    """Test VPS client initialization and configuration."""

    def test_init_with_explicit_params(self):
        """Test: client initializes with explicit base_url and api_key."""
        client = VPSClient(base_url="https://vps.example.com/api", api_key="test-key")

        assert client.base_url == "https://vps.example.com/api"
        assert client.api_key == "test-key"
        assert client.timeout == VPSClient.DEFAULT_TIMEOUT

    def test_init_strips_trailing_slash(self):
        """Test: trailing slash is stripped from base_url."""
        client = VPSClient(base_url="https://vps.example.com/api/", api_key="key")
        assert client.base_url == "https://vps.example.com/api"

    def test_init_from_env_vars(self):
        """Test: client reads from environment variables."""
        with patch.dict("os.environ", {
            "VPS_BASE_URL": "https://env-vps.example.com",
            "VPS_API_KEY": "env-key-123",
        }):
            client = VPSClient()
            assert client.base_url == "https://env-vps.example.com"
            assert client.api_key == "env-key-123"

    def test_init_explicit_overrides_env(self):
        """Test: explicit params take precedence over env vars."""
        with patch.dict("os.environ", {
            "VPS_BASE_URL": "https://env.example.com",
            "VPS_API_KEY": "env-key",
        }):
            client = VPSClient(base_url="https://explicit.example.com", api_key="explicit-key")
            assert client.base_url == "https://explicit.example.com"
            assert client.api_key == "explicit-key"

    def test_init_custom_timeout(self):
        """Test: custom timeout is respected."""
        client = VPSClient(base_url="https://vps.example.com", api_key="key", timeout=60)
        assert client.timeout == 60

    def test_init_counters_start_at_zero(self):
        """Test: request and error counters start at zero."""
        client = VPSClient(base_url="https://vps.example.com", api_key="key")
        assert client._request_count == 0
        assert client._error_count == 0
        assert client._last_health is None


class TestVPSHealthCheck:
    """Test VPS health check functionality."""

    @pytest.fixture
    def client(self):
        return VPSClient(base_url="https://vps.example.com/api", api_key="test-key")

    @patch("vps.client.requests.request")
    def test_health_check_success(self, mock_request, client):
        """Test: successful health check returns VPSStatus."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "healthy": True,
            "uptime_seconds": 86400,
            "cpu_percent": 15.2,
            "memory_percent": 42.8,
            "disk_percent": 60.1,
            "services_running": 3,
            "services_total": 3,
        }
        mock_request.return_value = mock_response

        status = client.health_check()

        assert status.healthy is True
        assert status.uptime_seconds == 86400
        assert status.cpu_percent == 15.2
        assert status.memory_percent == 42.8
        assert status.disk_percent == 60.1
        assert status.services_running == 3
        assert status.services_total == 3
        assert status.response_time_ms >= 0
        assert status.error is None

    @patch("vps.client.requests.request")
    def test_health_check_connection_failure(self, mock_request, client):
        """Test: connection failure returns unhealthy status."""
        import requests as req
        mock_request.side_effect = req.ConnectionError("Connection refused")

        status = client.health_check()

        assert status.healthy is False
        assert status.error == "Connection failed"
        assert client._error_count == 1

    @patch("vps.client.requests.request")
    def test_health_check_timeout(self, mock_request, client):
        """Test: timeout returns unhealthy status."""
        import requests as req
        mock_request.side_effect = req.Timeout("Request timed out")

        status = client.health_check()

        assert status.healthy is False
        assert status.error == "Connection failed"

    @patch("vps.client.requests.request")
    def test_health_check_http_error(self, mock_request, client):
        """Test: non-200 response returns unhealthy status."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_request.return_value = mock_response

        status = client.health_check()

        assert status.healthy is False
        assert "503" in status.error

    @patch("vps.client.requests.request")
    def test_health_check_caches_last_result(self, mock_request, client):
        """Test: last health check result is cached on client."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"healthy": True}
        mock_request.return_value = mock_response

        status = client.health_check()
        assert client._last_health is status

    def test_health_check_no_base_url(self):
        """Test: health check fails gracefully without base URL."""
        client = VPSClient(api_key="key")
        status = client.health_check()
        assert status.healthy is False


class TestVPSListServices:
    """Test VPS service listing."""

    @pytest.fixture
    def client(self):
        return VPSClient(base_url="https://vps.example.com/api", api_key="test-key")

    @patch("vps.client.requests.request")
    def test_list_services_success(self, mock_request, client):
        """Test: list services returns ServiceInfo objects."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "services": [
                {"name": "bets-api", "state": "running", "port": 8080, "pid": 1234},
                {"name": "nginx", "state": "running", "port": 80, "pid": 5678},
                {"name": "redis", "state": "stopped"},
            ]
        }
        mock_request.return_value = mock_response

        services = client.list_services()

        assert len(services) == 3
        assert services[0].name == "bets-api"
        assert services[0].state == "running"
        assert services[0].port == 8080
        assert services[2].state == "stopped"

    @patch("vps.client.requests.request")
    def test_list_services_empty(self, mock_request, client):
        """Test: empty service list returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"services": []}
        mock_request.return_value = mock_response

        services = client.list_services()
        assert services == []

    @patch("vps.client.requests.request")
    def test_list_services_failure(self, mock_request, client):
        """Test: API failure returns empty list."""
        import requests as req
        mock_request.side_effect = req.ConnectionError()

        services = client.list_services()
        assert services == []


class TestVPSRestartService:
    """Test VPS service restart."""

    @pytest.fixture
    def client(self):
        return VPSClient(base_url="https://vps.example.com/api", api_key="test-key")

    @patch("vps.client.requests.request")
    def test_restart_success_200(self, mock_request, client):
        """Test: 200 response means restart succeeded."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        assert client.restart_service("bets-api") is True

    @patch("vps.client.requests.request")
    def test_restart_success_202(self, mock_request, client):
        """Test: 202 (accepted) response means restart initiated."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_request.return_value = mock_response

        assert client.restart_service("bets-api") is True

    @patch("vps.client.requests.request")
    def test_restart_failure(self, mock_request, client):
        """Test: non-2xx response means restart failed."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Service not found"
        mock_request.return_value = mock_response

        assert client.restart_service("nonexistent") is False

    @patch("vps.client.requests.request")
    def test_restart_connection_failure(self, mock_request, client):
        """Test: connection failure returns False."""
        import requests as req
        mock_request.side_effect = req.ConnectionError()

        assert client.restart_service("bets-api") is False


class TestVPSDeploy:
    """Test VPS deployment."""

    @pytest.fixture
    def client(self):
        return VPSClient(base_url="https://vps.example.com/api", api_key="test-key")

    @patch("vps.client.requests.request")
    def test_deploy_success(self, mock_request, client):
        """Test: successful deployment returns DeployResult."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Deployed successfully",
            "deploy_id": "d-12345",
        }
        mock_request.return_value = mock_response

        result = client.deploy("betapp", ref="v2.1.0")

        assert result.success is True
        assert result.project == "betapp"
        assert result.ref == "v2.1.0"
        assert result.deploy_id == "d-12345"
        assert result.duration_seconds >= 0

    @patch("vps.client.requests.request")
    def test_deploy_default_ref(self, mock_request, client):
        """Test: default ref is 'main'."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "ok"}
        mock_request.return_value = mock_response

        result = client.deploy("betapp")
        assert result.ref == "main"

    @patch("vps.client.requests.request")
    def test_deploy_failure(self, mock_request, client):
        """Test: failed deployment returns failure result."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_request.return_value = mock_response

        result = client.deploy("betapp")

        assert result.success is False
        assert "500" in result.message

    @patch("vps.client.requests.request")
    def test_deploy_connection_failure(self, mock_request, client):
        """Test: connection failure returns failure result."""
        import requests as req
        mock_request.side_effect = req.ConnectionError()

        result = client.deploy("betapp")
        assert result.success is False
        assert result.message == "Connection failed"


class TestVPSGetLogs:
    """Test VPS log retrieval."""

    @pytest.fixture
    def client(self):
        return VPSClient(base_url="https://vps.example.com/api", api_key="test-key")

    @patch("vps.client.requests.request")
    def test_get_logs_json_response(self, mock_request, client):
        """Test: JSON log response is parsed correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "lines": [
                "2026-02-24 10:00:00 INFO Server started",
                "2026-02-24 10:00:01 INFO Listening on :8080",
            ]
        }
        mock_request.return_value = mock_response

        logs = client.get_logs("bets-api", lines=50)
        assert len(logs) == 2
        assert "Server started" in logs[0]

    @patch("vps.client.requests.request")
    def test_get_logs_plain_text_fallback(self, mock_request, client):
        """Test: plain text response is split into lines."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "line 1\nline 2\nline 3"
        mock_request.return_value = mock_response

        logs = client.get_logs("bets-api")
        assert len(logs) == 3

    @patch("vps.client.requests.request")
    def test_get_logs_failure(self, mock_request, client):
        """Test: failure returns empty list."""
        import requests as req
        mock_request.side_effect = req.ConnectionError()

        logs = client.get_logs("bets-api")
        assert logs == []


class TestVPSGetMetrics:
    """Test VPS metrics retrieval."""

    @pytest.fixture
    def client(self):
        return VPSClient(base_url="https://vps.example.com/api", api_key="test-key")

    @patch("vps.client.requests.request")
    def test_get_metrics_success(self, mock_request, client):
        """Test: metrics are returned as dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cpu": {"percent": 12.5, "cores": 4},
            "memory": {"used_mb": 2048, "total_mb": 4096},
        }
        mock_request.return_value = mock_response

        metrics = client.get_metrics()
        assert metrics["cpu"]["percent"] == 12.5
        assert metrics["memory"]["total_mb"] == 4096

    @patch("vps.client.requests.request")
    def test_get_metrics_failure(self, mock_request, client):
        """Test: failure returns empty dict."""
        import requests as req
        mock_request.side_effect = req.ConnectionError()

        metrics = client.get_metrics()
        assert metrics == {}


class TestVPSClientStats:
    """Test client-side statistics tracking."""

    def test_stats_initial(self):
        """Test: initial stats are clean."""
        client = VPSClient(base_url="https://vps.example.com/api", api_key="key")
        stats = client.get_stats()

        assert stats["base_url_configured"] is True
        assert stats["api_key_configured"] is True
        assert stats["total_requests"] == 0
        assert stats["total_errors"] == 0
        assert stats["error_rate_percent"] == 0
        assert stats["last_health"] is None

    @patch("vps.client.requests.request")
    def test_stats_after_requests(self, mock_request):
        """Test: stats reflect request activity."""
        client = VPSClient(base_url="https://vps.example.com/api", api_key="key")

        # Successful request
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"healthy": True}
        mock_request.return_value = mock_response

        client.health_check()

        # Failed request
        import requests as req
        mock_request.side_effect = req.ConnectionError()
        client.health_check()

        stats = client.get_stats()
        assert stats["total_requests"] == 2
        assert stats["total_errors"] == 1
        assert stats["error_rate_percent"] == 50.0
        assert stats["last_health"] is not None


class TestDataclasses:
    """Test dataclass serialization."""

    def test_vps_status_to_dict(self):
        """Test: VPSStatus serializes to dict."""
        status = VPSStatus(healthy=True, response_time_ms=42.5)
        d = status.to_dict()
        assert d["healthy"] is True
        assert d["response_time_ms"] == 42.5

    def test_service_info_to_dict(self):
        """Test: ServiceInfo serializes to dict."""
        svc = ServiceInfo(name="api", state="running", port=8080)
        d = svc.to_dict()
        assert d["name"] == "api"
        assert d["port"] == 8080

    def test_deploy_result_to_dict(self):
        """Test: DeployResult serializes to dict."""
        result = DeployResult(success=True, project="app", ref="main", message="ok")
        d = result.to_dict()
        assert d["success"] is True
        assert d["project"] == "app"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
