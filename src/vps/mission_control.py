#!/usr/bin/env python3
"""
Mission Control — Ira's Infrastructure Command Center

Unified orchestrator for VPS management via the Hostinger API.
No SSH required — everything runs through the API.

Capabilities:
- Real-time VPS status dashboard
- Docker container deployment and lifecycle management
- Firewall automation (auto-open ports for deployments)
- Health monitoring with self-healing actions
- Full audit trail of all operations

Usage:
    mc = MissionControl()
    status = mc.status()          # Full system overview
    mc.deploy("redis", REDIS_COMPOSE)  # Deploy a service
    mc.heal()                     # Auto-fix detected issues
"""

import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any, List

from .hostinger import HostingerVPSClient, VMInfo, ActionResult

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────

class Severity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ContainerHealth(Enum):
    """Container health states."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    UNKNOWN = "unknown"


@dataclass
class ContainerStatus:
    """Status of a single Docker container."""
    name: str
    image: str
    state: str
    health: str
    port_mappings: List[Dict[str, Any]] = field(default_factory=list)
    project: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemStatus:
    """Complete system status snapshot."""
    timestamp: float = field(default_factory=time.time)
    vm_id: Optional[int] = None
    vm_state: str = "unknown"
    hostname: str = ""
    ip_address: str = ""
    cpus: Optional[int] = None
    memory_mb: Optional[int] = None
    disk_gb: Optional[int] = None
    os_name: str = ""
    containers: List[ContainerStatus] = field(default_factory=list)
    containers_running: int = 0
    containers_total: int = 0
    firewall_active: bool = False
    firewall_rules: int = 0
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    api_healthy: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["containers"] = [c.to_dict() if isinstance(c, ContainerStatus) else c
                           for c in self.containers]
        return d

    @property
    def healthy(self) -> bool:
        return (
            self.vm_state == "running"
            and self.api_healthy
            and not any(a.get("severity") == "critical" for a in self.alerts)
        )


@dataclass
class AuditEntry:
    """Record of an action taken by Mission Control."""
    timestamp: float = field(default_factory=time.time)
    action: str = ""
    target: str = ""
    success: bool = True
    detail: str = ""
    triggered_by: str = "manual"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Mission Control ──────────────────────────────────────────────

class MissionControl:
    """
    Ira's command center for managing the Hostinger VPS.

    All operations go through the Hostinger API — no SSH needed.
    Maintains an audit log and supports automated healing.
    """

    def __init__(
        self,
        api_token: str = None,
        vm_id: int = None,
        auto_discover: bool = True,
    ):
        """
        Initialize Mission Control.

        Args:
            api_token: Hostinger API token (or from env).
            vm_id: Target VM ID. If None and auto_discover=True,
                   uses the first VM found on the account.
            auto_discover: Auto-detect VM ID if not provided.
        """
        self.client = HostingerVPSClient(api_token=api_token)
        self.vm_id = vm_id
        self._audit_log: List[AuditEntry] = []
        self._last_status: Optional[SystemStatus] = None

        if self.vm_id is None and auto_discover:
            self._discover_vm()

        logger.info(
            f"Mission Control online (vm_id={self.vm_id}, "
            f"token={'ok' if self.client.api_token else 'missing'})"
        )

    def _discover_vm(self):
        """Auto-discover the VM ID from the account."""
        vms = self.client.list_vms()
        if vms:
            self.vm_id = vms[0].id
            logger.info(f"Auto-discovered VM: {vms[0].hostname} (id={self.vm_id})")
        else:
            logger.warning("No VMs found on account")

    def _audit(self, action: str, target: str, success: bool,
               detail: str = "", triggered_by: str = "manual"):
        """Record an action in the audit log."""
        entry = AuditEntry(
            action=action, target=target, success=success,
            detail=detail, triggered_by=triggered_by,
        )
        self._audit_log.append(entry)
        level = logging.INFO if success else logging.WARNING
        logger.log(level, f"[AUDIT] {action} {target}: {'ok' if success else 'FAIL'} {detail}")

    # ── Status Dashboard ─────────────────────────────────────────

    def status(self) -> SystemStatus:
        """
        Get complete system status — VM, containers, firewall, alerts.
        This is the primary "what's going on" method for Ira.
        """
        ss = SystemStatus()

        # VM info
        vm = self.client.get_vm(self.vm_id) if self.vm_id else None
        if vm:
            ss.vm_id = vm.id
            ss.vm_state = vm.state
            ss.hostname = vm.hostname
            ss.ip_address = vm.ip_address or ""
            ss.cpus = vm.cpus
            ss.memory_mb = vm.memory_mb
            ss.disk_gb = vm.disk_gb
            ss.os_name = vm.os or ""
            ss.api_healthy = True
        else:
            ss.api_healthy = self.vm_id is None  # No VM configured isn't an API failure
            ss.alerts.append({
                "severity": Severity.CRITICAL.value,
                "message": "Cannot reach VM via API",
            })

        # Docker containers
        if self.vm_id:
            projects = self.client.list_docker_projects(self.vm_id)
            for proj in projects:
                for container in proj.get("containers", []):
                    cs = ContainerStatus(
                        name=container.get("name", ""),
                        image=container.get("image", ""),
                        state=container.get("state", "unknown"),
                        health=container.get("health", ""),
                        port_mappings=container.get("ports", []),
                        project=proj.get("name", ""),
                    )
                    ss.containers.append(cs)
                    ss.containers_total += 1
                    if cs.state == "running":
                        ss.containers_running += 1

            # Generate container alerts
            for c in ss.containers:
                if c.state != "running":
                    ss.alerts.append({
                        "severity": Severity.WARNING.value,
                        "message": f"Container {c.name} is {c.state}",
                        "container": c.name,
                    })
                if c.health == "unhealthy":
                    ss.alerts.append({
                        "severity": Severity.CRITICAL.value,
                        "message": f"Container {c.name} is unhealthy",
                        "container": c.name,
                    })

        # Firewall
        if self.vm_id:
            firewalls = self.client.list_firewalls()
            for fw in firewalls:
                if fw.get("is_synced"):
                    ss.firewall_active = True
                    ss.firewall_rules = len(fw.get("rules", []))
                    break

        # VM state alert
        if vm and vm.state != "running":
            ss.alerts.append({
                "severity": Severity.CRITICAL.value,
                "message": f"VM is {vm.state} (not running)",
            })

        self._last_status = ss
        return ss

    def quick_status(self) -> Dict[str, Any]:
        """Compact status summary for quick checks."""
        ss = self.status()
        return {
            "healthy": ss.healthy,
            "vm": ss.vm_state,
            "containers": f"{ss.containers_running}/{ss.containers_total}",
            "firewall": "active" if ss.firewall_active else "inactive",
            "alerts": len(ss.alerts),
            "critical": sum(1 for a in ss.alerts if a.get("severity") == "critical"),
        }

    # ── Docker Deployment ────────────────────────────────────────

    def deploy(
        self,
        project_name: str,
        compose_yaml: str,
        env_vars: Dict[str, str] = None,
        open_ports: List[Dict[str, str]] = None,
    ) -> ActionResult:
        """
        Deploy a Docker Compose project to the VPS.

        Args:
            project_name: Name for the project.
            compose_yaml: Docker Compose YAML content.
            env_vars: Optional environment variables.
            open_ports: Optional list of {"port": "8080", "protocol": "TCP"}
                       to auto-open in the firewall.
        """
        if not self.vm_id:
            return ActionResult(success=False, action="deploy", message="No VM configured")

        # Deploy the container
        result = self.client.deploy_docker_project(
            self.vm_id, compose_yaml, project_name, env_vars,
        )

        self._audit("deploy", project_name, result.success,
                     result.message, "mission_control")

        # Auto-open firewall ports if deployment succeeded
        if result.success and open_ports:
            for port_spec in open_ports:
                self._ensure_firewall_port(
                    port_spec.get("port", ""),
                    port_spec.get("protocol", "TCP"),
                )

        return result

    def remove(self, project_name: str) -> ActionResult:
        """Remove a Docker project from the VPS."""
        if not self.vm_id:
            return ActionResult(success=False, action="remove", message="No VM configured")

        result = self.client.remove_docker_project(self.vm_id, project_name)
        self._audit("remove", project_name, result.success,
                     result.message, "mission_control")
        return result

    def list_services(self) -> List[Dict[str, Any]]:
        """List all running Docker services with their ports."""
        if not self.vm_id:
            return []

        services = []
        projects = self.client.list_docker_projects(self.vm_id)
        for proj in projects:
            ports = []
            running = 0
            total = 0
            for container in proj.get("containers", []):
                total += 1
                if container.get("state") == "running":
                    running += 1
                for p in container.get("ports", []):
                    if p.get("type") == "published":
                        ports.append(f"{p.get('host_port', '?')}:{p.get('container_port', '?')}")

            services.append({
                "name": proj.get("name", ""),
                "state": proj.get("state", "unknown"),
                "containers": f"{running}/{total}",
                "ports": ports,
                "path": proj.get("path", ""),
            })
        return services

    # ── Firewall Management ──────────────────────────────────────

    def _ensure_firewall_port(self, port: str, protocol: str = "TCP"):
        """Ensure a port is open in the firewall. Creates firewall if needed."""
        if not port:
            return

        firewalls = self.client.list_firewalls()

        # Find active firewall or create one
        fw_id = None
        for fw in firewalls:
            # Check if rule already exists
            for rule in fw.get("rules", []):
                if rule.get("port") == port and rule.get("protocol", "").upper() == protocol.upper():
                    logger.info(f"Firewall rule already exists for {protocol}/{port}")
                    return
            fw_id = fw.get("id")
            break

        if fw_id is None:
            result = self.client.create_firewall("mission-control")
            if not result.success:
                self._audit("firewall_create", "mission-control", False,
                            result.message, "auto")
                return
            fw_id = result.data.get("id") if result.data else None
            if fw_id is None:
                return

        # Add the rule
        result = self.client.create_firewall_rule(
            fw_id, protocol=protocol, port=port,
        )
        self._audit("firewall_open_port", f"{protocol}/{port}",
                     result.success, result.message, "auto")

        # Activate on VM if needed
        if result.success and self.vm_id:
            self.client.activate_firewall(fw_id, self.vm_id)

    def lockdown(self, keep_ports: List[str] = None):
        """
        Lock down the firewall — remove all rules except specified ports.

        Args:
            keep_ports: List of port strings to keep open (e.g., ["22", "443"]).
                       Defaults to ["22"] (SSH only).
        """
        keep_ports = keep_ports or ["22"]
        firewalls = self.client.list_firewalls()

        for fw in firewalls:
            fw_id = fw.get("id")
            for rule in fw.get("rules", []):
                if rule.get("port") not in keep_ports:
                    result = self.client.delete_firewall_rule(fw_id, rule["id"])
                    self._audit("firewall_close_port", f"{rule.get('protocol')}/{rule.get('port')}",
                                result.success, result.message, "lockdown")

    # ── Health & Self-Healing ────────────────────────────────────

    def heal(self) -> List[Dict[str, Any]]:
        """
        Diagnose and attempt to fix detected issues.
        Returns a list of actions taken.

        Healing strategies:
        - VM not running → attempt power-on
        - Container unhealthy/stopped → log for manual review
          (auto-restart via redeploy would need the compose file)
        """
        actions = []
        ss = self.status()

        # Heal: VM not running
        if ss.vm_state and ss.vm_state != "running" and self.vm_id:
            if ss.vm_state in ("stopped", "shutdown"):
                result = self.client.start_vm(self.vm_id)
                action = {
                    "action": "power_on_vm",
                    "success": result.success,
                    "detail": result.message,
                }
                actions.append(action)
                self._audit("heal_power_on", f"vm:{self.vm_id}",
                            result.success, result.message, "auto_heal")
            elif ss.vm_state == "error":
                result = self.client.restart_vm(self.vm_id)
                action = {
                    "action": "restart_vm",
                    "success": result.success,
                    "detail": result.message,
                }
                actions.append(action)
                self._audit("heal_restart", f"vm:{self.vm_id}",
                            result.success, result.message, "auto_heal")

        # Report: Container issues (can't auto-fix without compose files)
        for c in ss.containers:
            if c.state != "running" or c.health == "unhealthy":
                action = {
                    "action": "container_alert",
                    "container": c.name,
                    "project": c.project,
                    "state": c.state,
                    "health": c.health,
                    "detail": "Manual intervention needed — redeploy via mc.deploy()",
                }
                actions.append(action)
                self._audit("heal_alert", c.name, True,
                            f"state={c.state} health={c.health}", "auto_heal")

        if not actions:
            actions.append({"action": "no_issues", "detail": "All systems nominal"})

        return actions

    # ── VM Power Management ──────────────────────────────────────

    def power_on(self) -> ActionResult:
        """Power on the VPS."""
        if not self.vm_id:
            return ActionResult(success=False, action="power_on", message="No VM configured")
        result = self.client.start_vm(self.vm_id)
        self._audit("power_on", f"vm:{self.vm_id}", result.success, result.message)
        return result

    def power_off(self) -> ActionResult:
        """Power off the VPS."""
        if not self.vm_id:
            return ActionResult(success=False, action="power_off", message="No VM configured")
        result = self.client.stop_vm(self.vm_id)
        self._audit("power_off", f"vm:{self.vm_id}", result.success, result.message)
        return result

    def reboot(self) -> ActionResult:
        """Reboot the VPS."""
        if not self.vm_id:
            return ActionResult(success=False, action="reboot", message="No VM configured")
        result = self.client.restart_vm(self.vm_id)
        self._audit("reboot", f"vm:{self.vm_id}", result.success, result.message)
        return result

    # ── Snapshot Management ──────────────────────────────────────

    def snapshot(self) -> ActionResult:
        """Create a snapshot of the current VPS state."""
        if not self.vm_id:
            return ActionResult(success=False, action="snapshot", message="No VM configured")
        result = self.client.create_snapshot(self.vm_id)
        self._audit("snapshot", f"vm:{self.vm_id}", result.success, result.message)
        return result

    def rollback(self) -> ActionResult:
        """Restore VPS from the last snapshot."""
        if not self.vm_id:
            return ActionResult(success=False, action="rollback", message="No VM configured")
        result = self.client.restore_snapshot(self.vm_id)
        self._audit("rollback", f"vm:{self.vm_id}", result.success, result.message)
        return result

    # ── SSH Key Management ───────────────────────────────────────

    def register_ssh_key(self, name: str, public_key: str) -> ActionResult:
        """Register an SSH key and attach it to the VM."""
        result = self.client.create_public_key(name, public_key)
        if not result.success:
            self._audit("register_key", name, False, result.message)
            return result

        # Attach to VM
        key_id = result.data.get("id") if result.data else None
        if key_id and self.vm_id:
            attach = self.client.attach_public_key(self.vm_id, [key_id])
            self._audit("attach_key", name, attach.success, attach.message)
            return attach

        self._audit("register_key", name, True, "Key registered (not attached)")
        return result

    # ── Audit Log ────────────────────────────────────────────────

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent audit entries."""
        entries = self._audit_log[-limit:]
        return [e.to_dict() for e in reversed(entries)]

    def get_audit_summary(self) -> Dict[str, Any]:
        """Summarize the audit log."""
        total = len(self._audit_log)
        successes = sum(1 for e in self._audit_log if e.success)
        failures = total - successes
        actions = {}
        for e in self._audit_log:
            actions[e.action] = actions.get(e.action, 0) + 1

        return {
            "total_actions": total,
            "successes": successes,
            "failures": failures,
            "actions_by_type": actions,
        }

    # ── Convenience ──────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"MissionControl(vm_id={self.vm_id}, actions={len(self._audit_log)})"


# ── Standalone runner ────────────────────────────────────────────

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    mc = MissionControl()

    # Full status
    ss = mc.status()
    print("\n=== MISSION CONTROL STATUS ===")
    print(f"VM: {ss.hostname} ({ss.vm_state})")
    print(f"IP: {ss.ip_address}")
    print(f"Resources: {ss.cpus} CPUs, {ss.memory_mb}MB RAM, {ss.disk_gb}GB disk")
    print(f"OS: {ss.os_name}")
    print(f"Containers: {ss.containers_running}/{ss.containers_total}")
    print(f"Firewall: {'active' if ss.firewall_active else 'inactive'} ({ss.firewall_rules} rules)")

    if ss.containers:
        print("\n--- Services ---")
        for c in ss.containers:
            ports = ", ".join(
                f"{p.get('host_port')}:{p.get('container_port')}"
                for p in c.port_mappings if p.get("type") == "published"
            )
            print(f"  [{c.state}] {c.name} ({c.image}) {ports}")

    if ss.alerts:
        print("\n--- Alerts ---")
        for a in ss.alerts:
            print(f"  [{a['severity'].upper()}] {a['message']}")

    print(f"\nHealthy: {ss.healthy}")
    print(f"\nQuick: {json.dumps(mc.quick_status(), indent=2)}")
