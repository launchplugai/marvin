"""HTTP control-plane server for sending instructions to Codex container."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from marvin.control_plane import ControlPlane


CONTROL_TOKEN = os.environ.get("CONTROL_API_TOKEN", "")
PLANE = ControlPlane(os.environ.get("CONTROL_PLANE_DIR", "/control"))


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    if not CONTROL_TOKEN:
        return True
    value = handler.headers.get("Authorization", "")
    return value == f"Bearer {CONTROL_TOKEN}"


class ControlHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if not _authorized(self):
            _json(self, HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            _json(self, HTTPStatus.OK, {"ok": True, "service": "marvin-control"})
            return

        if path == "/metrics":
            _json(self, HTTPStatus.OK, PLANE.get_metrics())
            return

        if path == "/results":
            limit = int(query.get("limit", ["20"])[0])
            _json(self, HTTPStatus.OK, PLANE.list_recent_results(limit=limit))
            return

        if path == "/containers":
            response = PLANE.list_containers()
            _json(self, HTTPStatus.OK if response.get("ok") else HTTPStatus.BAD_GATEWAY, response)
            return

        if path.startswith("/instructions/"):
            instruction_id = path.split("/")[-1]
            _json(self, HTTPStatus.OK, PLANE.get_instruction_status(instruction_id))
            return

        _json(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        if not _authorized(self):
            _json(self, HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return

        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            _json(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
            return

        if path == "/instructions":
            instruction = str(payload.get("instruction", "")).strip()
            if not instruction:
                _json(self, HTTPStatus.BAD_REQUEST, {"error": "instruction is required"})
                return

            created = PLANE.enqueue_instruction(
                instruction=instruction,
                target=str(payload.get("target", "codex-brain")),
                mode=str(payload.get("mode", "codex")),
            )
            _json(self, HTTPStatus.ACCEPTED, created)
            return

        if path.startswith("/containers/") and "/actions/" in path:
            parts = [p for p in path.split("/") if p]
            if len(parts) == 4 and parts[0] == "containers" and parts[2] == "actions":
                name = parts[1]
                action = parts[3]
                response = PLANE.container_action(name, action)
                code = HTTPStatus.OK if response.get("ok") else HTTPStatus.BAD_REQUEST
                _json(self, code, response)
                return

        _json(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, format, *args):  # noqa: A003
        return


def serve() -> None:
    host = os.environ.get("CONTROL_API_HOST", "0.0.0.0")
    port = int(os.environ.get("CONTROL_API_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), ControlHandler)
    server.serve_forever()


if __name__ == "__main__":
    serve()
