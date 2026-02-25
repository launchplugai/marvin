"""
Marvin VPS API Layer
Phase 1: VPS management for Ira (Infrastructure Guardian)

Provides health checks, service management, deployment,
and monitoring capabilities for VPS infrastructure.

Supports:
- Generic VPS API (VPSClient) — custom API on your server
- Hostinger API (HostingerVPSClient) — developers.hostinger.com
"""

from .client import VPSClient, VPSStatus, ServiceInfo, DeployResult
from .hostinger import HostingerVPSClient, VMInfo, ActionResult

__all__ = [
    'VPSClient', 'VPSStatus', 'ServiceInfo', 'DeployResult',
    'HostingerVPSClient', 'VMInfo', 'ActionResult',
]
