import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from marvin.control_plane import ControlPlane


class DummyResult:
    def __init__(self, code=0, out="", err=""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


def test_enqueue_and_read_status(tmp_path):
    plane = ControlPlane(str(tmp_path))
    created = plane.enqueue_instruction("do thing", target="codex-brain", mode="codex")

    status = plane.get_instruction_status(created["instruction_id"])
    assert status["status"] == "queued"
    assert status["instruction"] == "do thing"


def test_list_containers_parses_json(monkeypatch, tmp_path):
    plane = ControlPlane(str(tmp_path))

    def fake_run(command, capture_output, text, timeout):
        _ = (command, capture_output, text, timeout)
        line = json.dumps({"Names": "ollama", "State": "running"})
        return DummyResult(code=0, out=f"{line}\n")

    monkeypatch.setattr("subprocess.run", fake_run)

    response = plane.list_containers()
    assert response["ok"] is True
    assert response["data"][0]["Names"] == "ollama"


def test_container_action_rejects_unknown(tmp_path):
    plane = ControlPlane(str(tmp_path))
    response = plane.container_action("ollama", "destroy")
    assert response["ok"] is False
