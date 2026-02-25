"""
Marvin VPS API Layer — Infrastructure Management for Ira

Provides:
- Generic VPS API (VPSClient) — custom API on your server
- Hostinger API (HostingerVPSClient) — developers.hostinger.com
- Mission Control (MissionControl) — unified orchestrator for Ira
- State Engine (StateEngine) — persistent SQLite ledger
- Context Chain (ContextChain) — constitutional recovery chain
- SSH Exec Bridge (SSHExecBridge) — remote command execution
"""

from .client import VPSClient, VPSStatus, ServiceInfo, DeployResult
from .hostinger import HostingerVPSClient, VMInfo, ActionResult
from .mission_control import (
    MissionControl, SystemStatus, ContainerStatus,
    AuditEntry, Severity, ContainerHealth,
)
from .state import StateEngine, Event, AgentSnapshot
from .context_chain import ContextChain, ChainLink
from .ssh_bridge import SSHExecBridge, ExecResult

__all__ = [
    'VPSClient', 'VPSStatus', 'ServiceInfo', 'DeployResult',
    'HostingerVPSClient', 'VMInfo', 'ActionResult',
    'MissionControl', 'SystemStatus', 'ContainerStatus',
    'AuditEntry', 'Severity', 'ContainerHealth',
    'StateEngine', 'Event', 'AgentSnapshot',
    'ContextChain', 'ChainLink',
    'SSHExecBridge', 'ExecResult',
]
