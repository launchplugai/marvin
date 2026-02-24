#!/usr/bin/env python3
"""
VPS API Client — Infrastructure Management for Ira
Phase 1: Health checks, service management, deployment triggers

Implements:
- health_check() -> VPSStatus
- list_services() -> list[ServiceInfo]
- restart_service(name) -> bool
- deploy(project, ref) -> DeployResult
- get_metrics() -> dict
- get_logs(service, lines) -> list[str]
"""

import json
import logging
import os
import time
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    """Possible states for a VPS service."""
    RUNNING = "running"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class VPSStatus:
    """VPS health check result."""
    healthy: bool
    response_time_ms: float
    uptime_seconds: Optional[int] = None
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    services_running: int = 0
    services_total: int = 0
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ServiceInfo:
    """Information about a running VPS service."""
    name: str
    state: str
    port: Optional[int] = None
    pid: Optional[int] = None
    uptime_seconds: Optional[int] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeployResult:
    """Result of a deployment operation."""
    success: bool
    project: str
    ref: str
    message: str
    deploy_id: Optional[str] = None
    duration_seconds: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VPSClient:
    """
    VPS API client for infrastructure management.

    Used by Ira (Infrastructure Guardian) for:
    - Health monitoring and status checks
    - Service management (list, restart, logs)
    - Deployment triggers
    - Resource metrics collection

    Design principles:
    - API key from environment variable only (never hardcoded)
    - Graceful degradation: failures return error objects, not exceptions
    - All operations logged for audit trail
    - Timeout defaults prevent hanging on unresponsive VPS
    """

    DEFAULT_TIMEOUT = 30  # seconds
    HEALTH_ENDPOINT = "/health"
    SERVICES_ENDPOINT = "/services"
    DEPLOY_ENDPOINT = "/deploy"
    METRICS_ENDPOINT = "/metrics"
    LOGS_ENDPOINT = "/logs"

    def __init__(self, base_url: str = None, api_key: str = None, timeout: int = None):
        """
        Initialize VPS client.

        Args:
            base_url: VPS API base URL (or VPS_BASE_URL env var)
            api_key: VPS API key (or VPS_API_KEY env var)
            timeout: Request timeout in seconds
        """
        self.base_url = (base_url or os.environ.get("VPS_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("VPS_API_KEY")
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        if not self.api_key:
            logger.warning("No VPS API key configured. Set VPS_API_KEY environment variable.")

        if not self.base_url:
            logger.warning("No VPS base URL configured. Set VPS_BASE_URL environment variable.")

        self._request_count = 0
        self._error_count = 0
        self._last_health: Optional[VPSStatus] = None

        logger.info(
            f"VPSClient initialized (base_url={'configured' if self.base_url else 'missing'}, "
            f"api_key={'configured' if self.api_key else 'missing'})"
        )

    def _headers(self) -> Dict[str, str]:
        """Build request headers with auth."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """
        Make an authenticated request to the VPS API.

        Returns response on success, None on failure.
        All errors are logged, never raised.
        """
        if not self.base_url:
            logger.error("Cannot make request: no VPS_BASE_URL configured")
            return None

        url = f"{self.base_url}{endpoint}"
        self._request_count += 1

        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )

            if response.status_code >= 400:
                logger.warning(
                    f"VPS API error: {method} {endpoint} -> {response.status_code} "
                    f"{response.text[:200]}"
                )
                self._error_count += 1

            return response

        except requests.Timeout:
            logger.error(f"VPS API timeout: {method} {endpoint} (>{self.timeout}s)")
            self._error_count += 1
            return None
        except requests.ConnectionError:
            logger.error(f"VPS API connection error: {method} {endpoint}")
            self._error_count += 1
            return None
        except Exception as e:
            logger.error(f"VPS API unexpected error: {method} {endpoint}: {e}")
            self._error_count += 1
            return None

    def health_check(self) -> VPSStatus:
        """
        Check VPS health and resource usage.

        Returns:
            VPSStatus with health info, or error status on failure.
        """
        start = time.time()
        response = self._request("GET", self.HEALTH_ENDPOINT)
        elapsed_ms = (time.time() - start) * 1000

        if response is None:
            status = VPSStatus(
                healthy=False,
                response_time_ms=elapsed_ms,
                error="Connection failed",
            )
            self._last_health = status
            return status

        if response.status_code != 200:
            status = VPSStatus(
                healthy=False,
                response_time_ms=elapsed_ms,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )
            self._last_health = status
            return status

        try:
            data = response.json()
            status = VPSStatus(
                healthy=data.get("healthy", True),
                response_time_ms=elapsed_ms,
                uptime_seconds=data.get("uptime_seconds"),
                cpu_percent=data.get("cpu_percent"),
                memory_percent=data.get("memory_percent"),
                disk_percent=data.get("disk_percent"),
                services_running=data.get("services_running", 0),
                services_total=data.get("services_total", 0),
            )
        except (ValueError, KeyError) as e:
            status = VPSStatus(
                healthy=True,  # Server responded, assume healthy
                response_time_ms=elapsed_ms,
                error=f"Unexpected response format: {e}",
            )

        self._last_health = status
        logger.info(
            f"Health check: {'healthy' if status.healthy else 'UNHEALTHY'} "
            f"({status.response_time_ms:.0f}ms)"
        )
        return status

    def list_services(self) -> List[ServiceInfo]:
        """
        List all services running on the VPS.

        Returns:
            List of ServiceInfo, or empty list on failure.
        """
        response = self._request("GET", self.SERVICES_ENDPOINT)

        if response is None or response.status_code != 200:
            logger.warning("Failed to list services")
            return []

        try:
            data = response.json()
            services = []
            for svc in data.get("services", []):
                services.append(ServiceInfo(
                    name=svc.get("name", "unknown"),
                    state=svc.get("state", ServiceState.UNKNOWN.value),
                    port=svc.get("port"),
                    pid=svc.get("pid"),
                    uptime_seconds=svc.get("uptime_seconds"),
                    memory_mb=svc.get("memory_mb"),
                    cpu_percent=svc.get("cpu_percent"),
                ))
            logger.info(f"Listed {len(services)} services")
            return services
        except (ValueError, KeyError) as e:
            logger.error(f"Failed to parse services response: {e}")
            return []

    def restart_service(self, service_name: str) -> bool:
        """
        Restart a service on the VPS.

        Args:
            service_name: Name of the service to restart.

        Returns:
            True on success, False on failure.
        """
        logger.info(f"Restarting service: {service_name}")
        response = self._request(
            "POST",
            f"{self.SERVICES_ENDPOINT}/{service_name}/restart",
        )

        if response is None:
            return False

        success = response.status_code in (200, 202)
        if success:
            logger.info(f"Service {service_name} restart initiated")
        else:
            logger.error(
                f"Service {service_name} restart failed: "
                f"{response.status_code} {response.text[:200]}"
            )
        return success

    def deploy(self, project: str, ref: str = "main") -> DeployResult:
        """
        Trigger a deployment on the VPS.

        Args:
            project: Project name to deploy.
            ref: Git ref (branch, tag, or commit SHA) to deploy.

        Returns:
            DeployResult with outcome details.
        """
        logger.info(f"Deploying {project}@{ref}")
        start = time.time()

        response = self._request(
            "POST",
            self.DEPLOY_ENDPOINT,
            json={"project": project, "ref": ref},
        )

        duration = time.time() - start

        if response is None:
            return DeployResult(
                success=False,
                project=project,
                ref=ref,
                message="Connection failed",
                duration_seconds=duration,
            )

        if response.status_code not in (200, 201, 202):
            return DeployResult(
                success=False,
                project=project,
                ref=ref,
                message=f"HTTP {response.status_code}: {response.text[:200]}",
                duration_seconds=duration,
            )

        try:
            data = response.json()
            result = DeployResult(
                success=True,
                project=project,
                ref=ref,
                message=data.get("message", "Deployment initiated"),
                deploy_id=data.get("deploy_id"),
                duration_seconds=duration,
            )
        except (ValueError, KeyError):
            result = DeployResult(
                success=True,
                project=project,
                ref=ref,
                message="Deployment initiated (no details returned)",
                duration_seconds=duration,
            )

        logger.info(
            f"Deploy {project}@{ref}: "
            f"{'success' if result.success else 'FAILED'} "
            f"({result.duration_seconds:.1f}s)"
        )
        return result

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get VPS resource metrics.

        Returns:
            Dict of metrics, or empty dict on failure.
        """
        response = self._request("GET", self.METRICS_ENDPOINT)

        if response is None or response.status_code != 200:
            return {}

        try:
            return response.json()
        except ValueError:
            return {}

    def get_logs(self, service_name: str, lines: int = 100) -> List[str]:
        """
        Get recent log lines for a service.

        Args:
            service_name: Name of the service.
            lines: Number of recent lines to retrieve.

        Returns:
            List of log lines, or empty list on failure.
        """
        response = self._request(
            "GET",
            f"{self.LOGS_ENDPOINT}/{service_name}",
            params={"lines": lines},
        )

        if response is None or response.status_code != 200:
            return []

        try:
            data = response.json()
            return data.get("lines", [])
        except ValueError:
            # Try plain text
            return response.text.strip().splitlines()

    def get_stats(self) -> Dict[str, Any]:
        """Get client-side statistics."""
        return {
            "base_url_configured": bool(self.base_url),
            "api_key_configured": bool(self.api_key),
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "error_rate_percent": (
                round(self._error_count / self._request_count * 100, 1)
                if self._request_count > 0 else 0
            ),
            "last_health": self._last_health.to_dict() if self._last_health else None,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    client = VPSClient()

    # Health check
    status = client.health_check()
    print(f"\nHealth: {'OK' if status.healthy else 'FAIL'} ({status.response_time_ms:.0f}ms)")
    if status.error:
        print(f"  Error: {status.error}")

    # List services
    services = client.list_services()
    print(f"\nServices ({len(services)}):")
    for svc in services:
        print(f"  - {svc.name}: {svc.state}")

    # Stats
    stats = client.get_stats()
    print(f"\nClient stats: {json.dumps(stats, indent=2)}")
