from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from proxy_control.server import MihomoClient, MihomoError, create_server


class FakeController:
    def __init__(self) -> None:
        self.mode = "rule"
        self.selection = "AUTO"
        self.refreshes = 0

    def status(self) -> dict:
        return {
            "status": "online",
            "checked_at": "2026-08-24T02:10:00Z",
            "mode": self.mode,
            "selection": self.selection,
            "auto_selection": "Hong Kong 01",
            "provider_updated_at": "2026-08-24T02:00:00Z",
            "nodes": [
                {"name": "Hong Kong 01", "type": "ss", "alive": True, "latency_ms": 88},
                {"name": "Long unavailable node name", "type": "vmess", "alive": False, "latency_ms": None},
            ],
        }

    def set_mode(self, mode: str) -> None:
        if mode not in {"rule", "global", "direct"}:
            raise MihomoError("invalid_mode", 400)
        self.mode = mode

    def set_selection(self, name: str) -> None:
        if name not in {"AUTO", "Hong Kong 01"}:
            raise MihomoError("invalid_selection", 400)
        self.selection = name

    def refresh_provider(self) -> None:
        self.refreshes += 1


class FixtureMihomoClient(MihomoClient):
    def __init__(self) -> None:
        pass

    def _request(self, method: str, path: str, payload=None):  # type: ignore[override]
        fixtures = {
            "/configs": {"mode": "rule", "secret": "must-not-leak"},
            "/proxies/GITHUB": {"now": "AUTO", "all": ["AUTO", "Fast node"]},
            "/proxies/AUTO": {"now": "Fast node"},
            "/providers/proxies/subscription": {
                "updatedAt": "2026-08-24T02:00:00Z",
                "subscriptionInfo": {"Upload": 1, "Download": 2},
                "proxies": [
                    {
                        "name": "Fast node",
                        "type": "ss",
                        "alive": True,
                        "server": "must-not-leak.example",
                        "password": "must-not-leak",
                        "history": [{"time": "now", "delay": 72}],
                    },
                    {"name": "Not in selector", "type": "ss", "alive": True},
                ],
            },
        }
        return fixtures[path]


class ProxyControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.controller = FakeController()
        cls.server = create_server("127.0.0.1", 0, controller=cls.controller)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.origin = cls.base_url

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        origin: str | None = None,
        content_type: str = "application/json",
    ) -> tuple[int, dict]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = content_type
        if origin is not None:
            headers["Origin"] = origin
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_home_page_and_security_headers(self) -> None:
        with urlopen(self.base_url + "/", timeout=3) as response:
            content = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn('id="node-list"', content)
            self.assertIn('id="mode-dialog"', content)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_status_endpoint(self) -> None:
        status, body = self.request_json("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(body["mode"], "rule")
        self.assertEqual(len(body["nodes"]), 2)

    def test_favicon_is_no_content(self) -> None:
        with urlopen(self.base_url + "/favicon.ico", timeout=3) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.read(), b"")

    def test_mode_change_requires_same_origin(self) -> None:
        status, body = self.request_json(
            "/api/mode", method="POST", payload={"mode": "direct"}, origin="https://attacker.example"
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "origin_not_allowed")
        self.assertEqual(self.controller.mode, "rule")

        status, body = self.request_json(
            "/api/mode", method="POST", payload={"mode": "direct"}, origin=self.origin
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(self.controller.mode, "direct")
        self.controller.mode = "rule"

    def test_rejects_invalid_mode_and_content_type(self) -> None:
        status, body = self.request_json(
            "/api/mode", method="POST", payload={"mode": "invalid"}, origin=self.origin
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "invalid_mode")

        status, body = self.request_json(
            "/api/mode",
            method="POST",
            payload={"mode": "rule"},
            origin=self.origin,
            content_type="text/plain",
        )
        self.assertEqual(status, 415)
        self.assertEqual(body["error"], "json_required")

    def test_selection_and_refresh(self) -> None:
        status, _ = self.request_json(
            "/api/selection", method="POST", payload={"name": "Hong Kong 01"}, origin=self.origin
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.controller.selection, "Hong Kong 01")

        status, _ = self.request_json(
            "/api/refresh", method="POST", payload={}, origin=self.origin
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.controller.refreshes, 1)
        self.controller.selection = "AUTO"

    def test_mihomo_status_is_allowlisted(self) -> None:
        status = FixtureMihomoClient().status()
        encoded = json.dumps(status)
        self.assertEqual(status["nodes"], [{"name": "Fast node", "type": "ss", "alive": True, "latency_ms": 72}])
        self.assertNotIn("must-not-leak", encoded)
        self.assertNotIn("subscriptionInfo", encoded)

    def test_unknown_route_is_json_404(self) -> None:
        status, body = self.request_json("/missing")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
