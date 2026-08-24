#!/usr/bin/env python3
"""Serve a loopback-only web UI for safe Mihomo mode and node control."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import socket
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
MAX_BODY_BYTES = 4_096
MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_MODES = frozenset({"rule", "global", "direct"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class MihomoError(RuntimeError):
    """A safe, non-secret representation of a Mihomo control failure."""

    def __init__(self, code: str, status: int = HTTPStatus.BAD_GATEWAY) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 5.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(self.socket_path)
        self.sock = connection


class MihomoClient:
    """Small client that exposes only the non-secret controller data the UI needs."""

    def __init__(self, socket_path: str, timeout: float = 5.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"

        connection = UnixHTTPConnection(self.socket_path, timeout=self.timeout)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, http.client.HTTPException, TimeoutError) as error:
            raise MihomoError("controller_unavailable") from error
        finally:
            connection.close()

        if len(raw) > MAX_RESPONSE_BYTES:
            raise MihomoError("controller_response_too_large")
        if not 200 <= response.status < 300:
            raise MihomoError("controller_request_failed")
        if not raw:
            return None
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise MihomoError("controller_invalid_response") from error
        if not isinstance(decoded, dict):
            raise MihomoError("controller_invalid_response")
        return decoded

    def status(self) -> dict[str, Any]:
        configs = self._request("GET", "/configs") or {}
        selector = self._request("GET", "/proxies/GITHUB") or {}
        auto = self._request("GET", "/proxies/AUTO") or {}
        provider = self._request("GET", "/providers/proxies/subscription") or {}

        allowed_names = selector.get("all", [])
        if not isinstance(allowed_names, list):
            allowed_names = []
        allowed = {name for name in allowed_names if isinstance(name, str)}

        nodes: list[dict[str, Any]] = []
        provider_nodes = provider.get("proxies", [])
        if not isinstance(provider_nodes, list):
            provider_nodes = []
        for item in provider_nodes:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name or name not in allowed:
                continue
            history = item.get("history", [])
            latest_delay: int | None = None
            if isinstance(history, list):
                for sample in reversed(history):
                    if not isinstance(sample, dict):
                        continue
                    delay = sample.get("delay")
                    if isinstance(delay, int) and delay > 0:
                        latest_delay = delay
                        break
            node_type = item.get("type")
            nodes.append(
                {
                    "name": name,
                    "type": node_type if isinstance(node_type, str) else "unknown",
                    "alive": bool(item.get("alive")),
                    "latency_ms": latest_delay,
                }
            )

        nodes.sort(
            key=lambda item: (
                not item["alive"],
                item["latency_ms"] is None,
                item["latency_ms"] or 0,
                item["name"].casefold(),
            )
        )

        mode = configs.get("mode")
        selected = selector.get("now")
        auto_selected = auto.get("now")
        updated_at = provider.get("updatedAt")
        return {
            "status": "online",
            "checked_at": utc_now(),
            "mode": mode if mode in ALLOWED_MODES else "unknown",
            "selection": selected if isinstance(selected, str) else "",
            "auto_selection": auto_selected if isinstance(auto_selected, str) else "",
            "provider_updated_at": updated_at if isinstance(updated_at, str) else None,
            "nodes": nodes,
        }

    def set_mode(self, mode: str) -> None:
        if mode not in ALLOWED_MODES:
            raise MihomoError("invalid_mode", HTTPStatus.BAD_REQUEST)
        self._request("PATCH", "/configs", {"mode": mode})

    def set_selection(self, name: str) -> None:
        selector = self._request("GET", "/proxies/GITHUB") or {}
        allowed = selector.get("all", [])
        if not isinstance(allowed, list) or name not in allowed:
            raise MihomoError("invalid_selection", HTTPStatus.BAD_REQUEST)
        self._request("PUT", "/proxies/GITHUB", {"name": name})

    def refresh_provider(self) -> None:
        self._request("PUT", "/providers/proxies/subscription")


class ProxyControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], controller: Any) -> None:
        super().__init__(address, ProxyControlHandler)
        self.controller = controller


class ProxyControlHandler(BaseHTTPRequestHandler):
    server: ProxyControlServer
    server_version = "ProxyControl/1.0"

    STATIC_FILES = {
        "/": (STATIC_DIR / "index.html", "text/html; charset=utf-8"),
        "/app.css": (STATIC_DIR / "app.css", "text/css; charset=utf-8"),
        "/app.js": (STATIC_DIR / "app.js", "text/javascript; charset=utf-8"),
    }

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_host"})
            return
        path = urlsplit(self.path).path
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self._security_headers()
            self.end_headers()
            return
        if path in self.STATIC_FILES:
            file_path, content_type = self.STATIC_FILES[path]
            self._serve_file(file_path, content_type)
            return
        if path == "/api/status":
            try:
                self._send_json(HTTPStatus.OK, self.server.controller.status())
            except MihomoError as error:
                self._send_json(error.status, {"status": "unavailable", "error": error.code})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._valid_host() or not self._valid_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "origin_not_allowed"})
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "json_required"})
            return
        payload = self._read_json()
        if payload is None:
            return

        path = urlsplit(self.path).path
        try:
            if path == "/api/mode":
                mode = payload.get("mode")
                if not isinstance(mode, str):
                    raise MihomoError("invalid_mode", HTTPStatus.BAD_REQUEST)
                self.server.controller.set_mode(mode)
            elif path == "/api/selection":
                name = payload.get("name")
                if not isinstance(name, str) or not name or len(name) > 240:
                    raise MihomoError("invalid_selection", HTTPStatus.BAD_REQUEST)
                self.server.controller.set_selection(name)
            elif path == "/api/refresh":
                self.server.controller.refresh_provider()
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
        except MihomoError as error:
            self._send_json(error.status, {"status": "error", "error": error.code})
            return

        self._send_json(HTTPStatus.OK, {"status": "ok"})

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "")
        if not host:
            return False
        try:
            parsed = urlsplit("//" + host)
        except ValueError:
            return False
        return parsed.hostname in LOOPBACK_HOSTS

    def _valid_origin(self) -> bool:
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        if not origin or not host:
            return False
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and parsed.hostname in LOOPBACK_HOSTS
            and parsed.netloc == host
        )

    def _read_json(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
            return None
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "json_object_required"})
            return None
        return payload

    def _serve_file(self, path: Path, content_type: str) -> None:
        try:
            content = path.read_bytes()
        except OSError:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "asset_unavailable"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: int | HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")


def create_server(
    host: str,
    port: int,
    controller: Any | None = None,
    socket_path: str = "/run/mihomo/controller.sock",
) -> ProxyControlServer:
    return ProxyControlServer((host, port), controller or MihomoClient(socket_path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("PROXY_CONTROL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PROXY_CONTROL_PORT", "8790")))
    parser.add_argument(
        "--socket",
        default=os.environ.get("MIHOMO_CONTROL_SOCKET", "/run/mihomo/controller.sock"),
    )
    args = parser.parse_args()

    server = create_server(args.host, args.port, socket_path=args.socket)
    stop_event = threading.Event()

    def request_shutdown(_signum: int, _frame: object) -> None:
        if not stop_event.is_set():
            stop_event.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    host, port = server.server_address[:2]
    print("Proxy control listening on http://%s:%s" % (host, port), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
