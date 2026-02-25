"""
Marvin VPS API Layer — Infrastructure Management for Ira

Provides:
- Generic VPS API (VPSClient) — custom API on your server
- Hostinger API (HostingerVPSClient) — developers.hostinger.com
- Mission Control (MissionControl) — unified orchestrator for Ira
"""

from .client import VPSClient, VPSStatus, ServiceInfo, DeployResult
from .hostinger import HostingerVPSClient, VMInfo, ActionResult
from .mission_control import (
    MissionControl, SystemStatus, ContainerStatus,
    AuditEntry, Severity, ContainerHealth,
)

__all__ = [
    'VPSClient', 'VPSStatus', 'ServiceInfo', 'DeployResult',
    'HostingerVPSClient', 'VMInfo', 'ActionResult',
    'MissionControl', 'SystemStatus', 'ContainerStatus',
    'AuditEntry', 'Severity', 'ContainerHealth',
]
