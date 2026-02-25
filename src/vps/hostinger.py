#!/usr/bin/env python3
"""
Hostinger VPS API Client — Infrastructure Management for Ira
Wraps the Hostinger public API (developers.hostinger.com) for VPS operations.

Implements:
- list_vms() -> list[VMInfo]
- get_vm(vm_id) -> VMInfo
- start_vm(vm_id) -> ActionResult
- stop_vm(vm_id) -> ActionResult
- restart_vm(vm_id) -> ActionResult
- create_snapshot(vm_id) -> ActionResult
- restore_snapshot(vm_id) -> ActionResult
- delete_snapshot(vm_id) -> ActionResult
- get_snapshot(vm_id) -> dict
- list_firewalls() -> list[dict]
- get_firewall(fw_id) -> dict
- create_firewall(name) -> ActionResult
- delete_firewall(fw_id) -> ActionResult
- activate_firewall(fw_id, vm_id) -> ActionResult
- deactivate_firewall(fw_id, vm_id) -> ActionResult
- create_firewall_rule(fw_id, ...) -> ActionResult
- delete_firewall_rule(fw_id, rule_id) -> ActionResult
- get_backups(vm_id) -> list[dict]
- get_data_centers() -> list[dict]
- set_root_password(vm_id, password) -> ActionResult
- attach_public_key(vm_id, key_ids) -> ActionResult
"""

import logging
import os
import time
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

BASE_URL = "https://developers.hostinger.com"


@dataclass
class VMInfo:
    """Virtual machine information from Hostinger API."""
    id: int
    hostname: str
    state: str
    cpus: Optional[int] = None
    memory_mb: Optional[int] = None
    disk_gb: Optional[int] = None
    os: Optional[str] = None
    ip_address: Optional[str] = None
    data_center: Optional[str] = None
    created_at: Optional[str] = None
    raw: Optional[Dict[str, Any]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        return d


@dataclass
class ActionResult:
    """Result of a Hostinger API action."""
    success: bool
    action: str
    vm_id: Optional[int] = None
    message: str = ""
    status_code: Optional[int] = None
    data: Optional[Dict[str, Any]] = field(default=None, repr=False)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("data", None)
        return d


class HostingerVPSClient:
    """
    Hostinger VPS API client.

    Used by Ira (Infrastructure Guardian) for:
    - VM lifecycle management (start/stop/restart)
    - Snapshot creation and restoration
    - Firewall configuration
    - Backup retrieval
    - Root password and SSH key management

    Auth: Bearer token from HOSTINGER_API_TOKEN env var or constructor arg.
    """

    DEFAULT_TIMEOUT = 30
    VPS_PREFIX = "/api/vps/v1"

    def __init__(self, api_token: str = None, timeout: int = None):
        self.api_token = api_token or os.environ.get("HOSTINGER_API_TOKEN") or os.environ.get("API_TOKEN")
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        if not self.api_token:
            logger.warning("No Hostinger API token configured. Set HOSTINGER_API_TOKEN env var.")

        self._request_count = 0
        self._error_count = 0

        logger.info(
            f"HostingerVPSClient initialized "
            f"(token={'configured' if self.api_token else 'missing'})"
        )

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _request(
        self, method: str, path: str, **kwargs
    ) -> Optional[requests.Response]:
        """Make authenticated request to Hostinger API. Returns None on failure."""
        url = f"{BASE_URL}{self.VPS_PREFIX}{path}"
        self._request_count += 1

        try:
            resp = requests.request(
                method, url,
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )
            if resp.status_code >= 400:
                logger.warning(
                    f"Hostinger API error: {method} {path} -> "
                    f"{resp.status_code} {resp.text[:300]}"
                )
                self._error_count += 1
            return resp
        except requests.Timeout:
            logger.error(f"Hostinger API timeout: {method} {path}")
            self._error_count += 1
            return None
        except requests.ConnectionError:
            logger.error(f"Hostinger API connection error: {method} {path}")
            self._error_count += 1
            return None
        except Exception as e:
            logger.error(f"Hostinger API unexpected error: {method} {path}: {e}")
            self._error_count += 1
            return None

    def _action(
        self, method: str, path: str, action_name: str,
        vm_id: int = None, **kwargs
    ) -> ActionResult:
        """Execute an API action and return standardized result."""
        resp = self._request(method, path, **kwargs)
        if resp is None:
            return ActionResult(
                success=False, action=action_name, vm_id=vm_id,
                message="Connection failed",
            )

        success = resp.status_code < 400
        try:
            data = resp.json()
        except ValueError:
            data = None

        return ActionResult(
            success=success,
            action=action_name,
            vm_id=vm_id,
            message=data.get("message", "") if data else resp.text[:200],
            status_code=resp.status_code,
            data=data,
        )

    # ── VM Lifecycle ─────────────────────────────────────────────

    def list_vms(self) -> List[VMInfo]:
        """List all virtual machines on the account."""
        resp = self._request("GET", "/virtual-machines")
        if resp is None or resp.status_code != 200:
            return []
        try:
            vms = []
            for vm in resp.json():
                vms.append(self._parse_vm(vm))
            logger.info(f"Listed {len(vms)} virtual machines")
            return vms
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Failed to parse VM list: {e}")
            return []

    def get_vm(self, vm_id: int) -> Optional[VMInfo]:
        """Get details of a specific virtual machine."""
        resp = self._request("GET", f"/virtual-machines/{vm_id}")
        if resp is None or resp.status_code != 200:
            return None
        try:
            return self._parse_vm(resp.json())
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Failed to parse VM {vm_id}: {e}")
            return None

    def start_vm(self, vm_id: int) -> ActionResult:
        """Start a virtual machine."""
        return self._action("POST", f"/virtual-machines/{vm_id}/start", "start", vm_id)

    def stop_vm(self, vm_id: int) -> ActionResult:
        """Stop a virtual machine."""
        return self._action("POST", f"/virtual-machines/{vm_id}/stop", "stop", vm_id)

    def restart_vm(self, vm_id: int) -> ActionResult:
        """Restart a virtual machine."""
        return self._action("POST", f"/virtual-machines/{vm_id}/restart", "restart", vm_id)

    # ── Snapshots ────────────────────────────────────────────────

    def get_snapshot(self, vm_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve snapshot info for a VM."""
        resp = self._request("GET", f"/virtual-machines/{vm_id}/snapshot")
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def create_snapshot(self, vm_id: int) -> ActionResult:
        """Create a snapshot (overwrites existing)."""
        return self._action(
            "POST", f"/virtual-machines/{vm_id}/snapshot",
            "create_snapshot", vm_id,
        )

    def restore_snapshot(self, vm_id: int) -> ActionResult:
        """Restore VM from its snapshot."""
        return self._action(
            "POST", f"/virtual-machines/{vm_id}/snapshot/restore",
            "restore_snapshot", vm_id,
        )

    def delete_snapshot(self, vm_id: int) -> ActionResult:
        """Delete the snapshot for a VM."""
        return self._action(
            "DELETE", f"/virtual-machines/{vm_id}/snapshot",
            "delete_snapshot", vm_id,
        )

    # ── Firewalls ────────────────────────────────────────────────

    def list_firewalls(self) -> List[Dict[str, Any]]:
        """List all firewalls."""
        resp = self._request("GET", "/firewalls")
        if resp is None or resp.status_code != 200:
            return []
        try:
            return resp.json()
        except ValueError:
            return []

    def get_firewall(self, firewall_id: int) -> Optional[Dict[str, Any]]:
        """Get firewall details and rules."""
        resp = self._request("GET", f"/firewalls/{firewall_id}")
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def create_firewall(self, name: str) -> ActionResult:
        """Create a new firewall."""
        return self._action(
            "POST", "/firewalls", "create_firewall",
            json={"name": name},
        )

    def delete_firewall(self, firewall_id: int) -> ActionResult:
        """Delete a firewall."""
        return self._action("DELETE", f"/firewalls/{firewall_id}", "delete_firewall")

    def activate_firewall(self, firewall_id: int, vm_id: int) -> ActionResult:
        """Activate a firewall on a VM."""
        return self._action(
            "POST", f"/firewalls/{firewall_id}/activate/{vm_id}",
            "activate_firewall", vm_id,
        )

    def deactivate_firewall(self, firewall_id: int, vm_id: int) -> ActionResult:
        """Deactivate a firewall on a VM."""
        return self._action(
            "POST", f"/firewalls/{firewall_id}/deactivate/{vm_id}",
            "deactivate_firewall", vm_id,
        )

    def sync_firewall(self, firewall_id: int, vm_id: int) -> ActionResult:
        """Sync firewall rules to a VM."""
        return self._action(
            "POST", f"/firewalls/{firewall_id}/sync/{vm_id}",
            "sync_firewall", vm_id,
        )

    def create_firewall_rule(
        self, firewall_id: int, protocol: str,
        port: str, source: str = "0.0.0.0/0",
        action: str = "accept",
    ) -> ActionResult:
        """Create a firewall rule. Default drops all, so add accept rules."""
        return self._action(
            "POST", f"/firewalls/{firewall_id}/rules",
            "create_firewall_rule",
            json={
                "protocol": protocol,
                "port": port,
                "source": source,
                "action": action,
            },
        )

    def update_firewall_rule(
        self, firewall_id: int, rule_id: int,
        protocol: str = None, port: str = None,
        source: str = None, action: str = None,
    ) -> ActionResult:
        """Update a firewall rule."""
        payload = {}
        if protocol is not None:
            payload["protocol"] = protocol
        if port is not None:
            payload["port"] = port
        if source is not None:
            payload["source"] = source
        if action is not None:
            payload["action"] = action
        return self._action(
            "PUT", f"/firewalls/{firewall_id}/rules/{rule_id}",
            "update_firewall_rule",
            json=payload,
        )

    def delete_firewall_rule(self, firewall_id: int, rule_id: int) -> ActionResult:
        """Delete a firewall rule."""
        return self._action(
            "DELETE", f"/firewalls/{firewall_id}/rules/{rule_id}",
            "delete_firewall_rule",
        )

    # ── Docker Management ─────────────────────────────────────────

    def list_docker_projects(self, vm_id: int) -> List[Dict[str, Any]]:
        """List all Docker Compose projects on a VM."""
        resp = self._request("GET", f"/virtual-machines/{vm_id}/docker")
        if resp is None or resp.status_code != 200:
            return []
        try:
            return resp.json()
        except ValueError:
            return []

    def get_docker_project(self, vm_id: int, project_name: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific Docker Compose project."""
        resp = self._request("GET", f"/virtual-machines/{vm_id}/docker/{project_name}")
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def deploy_docker_project(
        self, vm_id: int, compose_content: str,
        project_name: str = None, env_vars: Dict[str, str] = None,
    ) -> ActionResult:
        """
        Deploy a Docker Compose project to a VM.

        Args:
            vm_id: Target virtual machine ID.
            compose_content: Docker Compose YAML content.
            project_name: Optional project name.
            env_vars: Optional environment variables for the compose file.
        """
        payload = {"compose": compose_content}
        if project_name:
            payload["project_name"] = project_name
        if env_vars:
            payload["env"] = env_vars
        return self._action(
            "POST", f"/virtual-machines/{vm_id}/docker",
            "deploy_docker", vm_id, json=payload,
        )

    def remove_docker_project(self, vm_id: int, project_name: str) -> ActionResult:
        """Remove (docker-compose down) a project from a VM."""
        return self._action(
            "DELETE", f"/virtual-machines/{vm_id}/docker/{project_name}/down",
            "remove_docker", vm_id,
        )

    # ── Public Keys ──────────────────────────────────────────────

    def list_public_keys(self) -> List[Dict[str, Any]]:
        """List all SSH public keys on the account."""
        resp = self._request("GET", "/public-keys")
        if resp is None or resp.status_code != 200:
            return []
        try:
            data = resp.json()
            return data.get("data", data) if isinstance(data, dict) else data
        except ValueError:
            return []

    def create_public_key(self, name: str, key: str) -> ActionResult:
        """Register a new SSH public key."""
        return self._action(
            "POST", "/public-keys", "create_public_key",
            json={"name": name, "key": key},
        )

    def delete_public_key(self, key_id: int) -> ActionResult:
        """Delete an SSH public key."""
        return self._action("DELETE", f"/public-keys/{key_id}", "delete_public_key")

    # ── Backups & Metrics ────────────────────────────────────────

    def get_backups(self, vm_id: int) -> List[Dict[str, Any]]:
        """Get available backups for a VM."""
        resp = self._request("GET", f"/virtual-machines/{vm_id}/backups")
        if resp is None or resp.status_code != 200:
            return []
        try:
            return resp.json()
        except ValueError:
            return []

    def get_metrics(self, vm_id: int) -> Dict[str, Any]:
        """Get historical metrics for a VM."""
        resp = self._request("GET", f"/virtual-machines/{vm_id}/metrics")
        if resp is None or resp.status_code != 200:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}

    def get_data_centers(self) -> List[Dict[str, Any]]:
        """List available data centers."""
        resp = self._request("GET", "/data-centers")
        if resp is None or resp.status_code != 200:
            return []
        try:
            return resp.json()
        except ValueError:
            return []

    # ── Access Management ────────────────────────────────────────

    def set_root_password(self, vm_id: int, password: str) -> ActionResult:
        """Set root password for a VM."""
        return self._action(
            "POST", f"/virtual-machines/{vm_id}/root-password",
            "set_root_password", vm_id,
            json={"password": password},
        )

    def attach_public_key(self, vm_id: int, key_ids: List[int]) -> ActionResult:
        """Attach SSH public keys to a VM."""
        return self._action(
            "POST", f"/virtual-machines/{vm_id}/public-keys",
            "attach_public_key", vm_id,
            json={"ids": key_ids},
        )

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _parse_vm(data: Dict[str, Any]) -> VMInfo:
        """Parse API response into VMInfo."""
        return VMInfo(
            id=data.get("id", 0),
            hostname=data.get("hostname", ""),
            state=data.get("state", "unknown"),
            cpus=data.get("cpus"),
            memory_mb=data.get("memory_mb"),
            disk_gb=data.get("disk_gb"),
            os=data.get("template", {}).get("name") if isinstance(data.get("template"), dict) else data.get("os"),
            ip_address=(
                data.get("ip_address")
                or (data.get("ips", [{}])[0].get("address") if data.get("ips") else None)
            ),
            data_center=data.get("data_center", {}).get("name") if isinstance(data.get("data_center"), dict) else data.get("data_center"),
            created_at=data.get("created_at"),
            raw=data,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get client-side stats."""
        return {
            "token_configured": bool(self.api_token),
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "error_rate_percent": (
                round(self._error_count / self._request_count * 100, 1)
                if self._request_count > 0 else 0
            ),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    client = HostingerVPSClient()

    # List VMs
    vms = client.list_vms()
    print(f"\nVirtual Machines ({len(vms)}):")
    for vm in vms:
        print(f"  - [{vm.id}] {vm.hostname}: {vm.state} ({vm.ip_address})")

    # Stats
    import json
    print(f"\nClient stats: {json.dumps(client.get_stats(), indent=2)}")
