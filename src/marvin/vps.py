"""Hostinger VPS API client for Marvin orchestration."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class HostingerConfig:
    api_token: str
    api_base: str = "https://developers.hostinger.com/api/vps/v1"
    vm_id: Optional[str] = None


class HostingerVPSClient:
    """Minimal Hostinger VPS client with safe error handling."""

    def __init__(self, config: HostingerConfig):
        self.config = config

    @classmethod
    def from_env(cls) -> "HostingerVPSClient | None":
        token = os.environ.get("HOSTINGER_API_TOKEN")
        if not token:
            return None
        return cls(
            HostingerConfig(
                api_token=token,
                api_base=os.environ.get("HOSTINGER_API_BASE", "https://developers.hostinger.com/api/vps/v1"),
                vm_id=os.environ.get("HOSTINGER_VM_ID"),
            )
        )

    def is_configured(self) -> bool:
        return bool(self.config.api_token)

    def list_virtual_machines(self) -> Dict[str, Any]:
        return self._request("GET", "/virtual-machines")

    def get_virtual_machine(self, vm_id: Optional[str] = None) -> Dict[str, Any]:
        target_vm = vm_id or self.config.vm_id
        if not target_vm:
            return {"ok": False, "error": "No VM ID configured"}
        return self._request("GET", f"/virtual-machines/{target_vm}")

    def get_status_snapshot(self) -> Dict[str, Any]:
        """Return best-effort VM status for orchestration decisions."""
        if self.config.vm_id:
            vm = self.get_virtual_machine(self.config.vm_id)
            if vm.get("ok"):
                return vm

        listed = self.list_virtual_machines()
        if not listed.get("ok"):
            return listed

        data = listed.get("data", listed.get("result", listed))
        return {"ok": True, "data": data}

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.config.api_base.rstrip('/')}{path}"
        headers = {
            "Authorization": f"Bearer {self.config.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url=url, method=method, headers=headers, data=body)

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
            return {"ok": True, "data": parsed, "status_code": getattr(response, "status", 200)}
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8") if exc.fp else ""
            return {
                "ok": False,
                "error": f"HTTP {exc.code}",
                "details": error_body[:500],
                "status_code": exc.code,
            }
        except urllib.error.URLError as exc:
            return {"ok": False, "error": "Connection error", "details": str(exc.reason)}
        except TimeoutError:
            return {"ok": False, "error": "Timeout", "details": "Request timed out"}
        except json.JSONDecodeError:
            return {"ok": False, "error": "Invalid JSON", "details": "Could not decode API response"}
