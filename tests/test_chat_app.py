from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from chat_app.server import create_server


class ChatAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server("127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_address[1]

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
        payload: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_home_page_contains_clock_and_chat(self) -> None:
        with urlopen(self.base_url + "/", timeout=3) as response:
            content = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn('id="clock"', content)
            self.assertIn('id="chat-form"', content)

    def test_health_endpoint(self) -> None:
        status, body = self.request_json("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("server_time", body)

    def test_post_and_fetch_message(self) -> None:
        status, body = self.request_json(
            "/api/messages",
            method="POST",
            payload={"author": "test-client", "text": "connection check"},
        )
        self.assertEqual(status, 201)
        created = body["message"]
        self.assertNotIn("source", created)

        status, body = self.request_json(
            "/api/messages?after=%d" % (created["id"] - 1)
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["messages"][-1]["text"], "connection check")
        self.assertEqual(body["messages"][-1]["author"], "test-client")

    def test_rejects_empty_message(self) -> None:
        status, body = self.request_json(
            "/api/messages",
            method="POST",
            payload={"author": "test-client", "text": "  "},
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "author_and_text_are_required")

    def test_unknown_route_is_json_404(self) -> None:
        status, body = self.request_json("/missing")
