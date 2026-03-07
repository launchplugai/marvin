import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from marvin.vps import HostingerConfig, HostingerVPSClient


class DummyResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_virtual_machine_success(monkeypatch):
    client = HostingerVPSClient(HostingerConfig(api_token="test", vm_id="123"))

    def fake_urlopen(request, timeout=0):
        assert request.full_url.endswith("/virtual-machines/123")
        assert request.headers["Authorization"] == "Bearer test"
        return DummyResponse({"id": "123", "status": "running"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = client.get_virtual_machine()
    assert result["ok"] is True
    assert result["data"]["id"] == "123"


def test_vm_id_required():
    client = HostingerVPSClient(HostingerConfig(api_token="test"))
    result = client.get_virtual_machine()
    assert result["ok"] is False
    assert "No VM ID" in result["error"]
