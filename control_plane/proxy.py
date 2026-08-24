"""Allowlisted Mihomo control adapter used by the authenticated control plane."""

from __future__ import annotations

import http.client
import json
import socket
from http import HTTPStatus
from typing import Any

from .security import utc_now


MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_MODES = frozenset({"rule", "global", "direct"})


class ProxyError(RuntimeError):
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
    def __init__(self, socket_path: str, timeout: float = 5.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
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
            raise ProxyError("controller_unavailable") from error
        finally:
            connection.close()
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProxyError("controller_response_too_large")
        if not 200 <= response.status < 300:
            raise ProxyError("controller_request_failed")
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ProxyError("controller_invalid_response") from error
        if not isinstance(value, dict):
            raise ProxyError("controller_invalid_response")
        return value

    def status(self) -> dict[str, Any]:
        configs = self._request("GET", "/configs") or {}
        selector = self._request("GET", "/proxies/GITHUB") or {}
        auto = self._request("GET", "/proxies/AUTO") or {}
        provider = self._request("GET", "/providers/proxies/subscription") or {}
        allowed_names = selector.get("all", [])
        allowed = {name for name in allowed_names if isinstance(name, str)} if isinstance(allowed_names, list) else set()
        nodes = []
        provider_nodes = provider.get("proxies", [])
        for item in provider_nodes if isinstance(provider_nodes, list) else []:
            if not isinstance(item, dict) or item.get("name") not in allowed:
                continue
            latest_delay = None
            history = item.get("history", [])
            for sample in reversed(history if isinstance(history, list) else []):
                if isinstance(sample, dict) and isinstance(sample.get("delay"), int) and sample["delay"] > 0:
                    latest_delay = sample["delay"]
                    break
            nodes.append(
                {
                    "name": item["name"],
                    "type": item.get("type") if isinstance(item.get("type"), str) else "unknown",
                    "alive": bool(item.get("alive")),
                    "latency_ms": latest_delay,
                }
            )
        nodes.sort(key=lambda item: (not item["alive"], item["latency_ms"] is None, item["latency_ms"] or 0, item["name"].casefold()))
        mode = configs.get("mode")
        return {
            "status": "online",
            "checked_at": utc_now(),
            "mode": mode if mode in ALLOWED_MODES else "unknown",
            "selection": selector.get("now") if isinstance(selector.get("now"), str) else "",
            "auto_selection": auto.get("now") if isinstance(auto.get("now"), str) else "",
            "provider_updated_at": provider.get("updatedAt") if isinstance(provider.get("updatedAt"), str) else None,
            "nodes": nodes,
        }

    def set_mode(self, mode: str) -> None:
        if mode not in ALLOWED_MODES:
            raise ProxyError("invalid_mode", HTTPStatus.BAD_REQUEST)
        self._request("PATCH", "/configs", {"mode": mode})

    def set_selection(self, name: str) -> None:
        selector = self._request("GET", "/proxies/GITHUB") or {}
        allowed = selector.get("all", [])
        if not isinstance(allowed, list) or name not in allowed:
            raise ProxyError("invalid_selection", HTTPStatus.BAD_REQUEST)
        self._request("PUT", "/proxies/GITHUB", {"name": name})

    def refresh_provider(self) -> None:
        self._request("PUT", "/providers/proxies/subscription")


__all__ = ["MihomoClient", "ProxyError"]
