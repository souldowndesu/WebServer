from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from control_plane.proxy import MihomoClient, ProxyError
from control_plane.server import create_server
from control_plane.shared import SharedStore
from control_plane.storage import AccountStore


ADMIN_PASSWORD = "Correct horse battery 123!"
USER_PASSWORD = "Useful account password 456!"
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"safe-test-image").decode("ascii")


class FakeProxy:
    def __init__(self) -> None:
        self.mode = "rule"
        self.selection = "AUTO"
        self.refreshes = 0

    def status(self):
        return {
            "status": "online",
            "mode": self.mode,
            "selection": self.selection,
            "auto_selection": "Fast node",
            "nodes": [{"name": "Fast node", "type": "ss", "alive": True, "latency_ms": 80}],
        }

    def set_mode(self, mode):
        if mode not in {"rule", "global", "direct"}:
            raise ProxyError("invalid_mode", 400)
        self.mode = mode

    def set_selection(self, name):
        if name not in {"AUTO", "Fast node"}:
            raise ProxyError("invalid_selection", 400)
        self.selection = name

    def refresh_provider(self):
        self.refreshes += 1


class FixtureMihomoClient(MihomoClient):
    def __init__(self):
        pass

    def _request(self, method, path, payload=None):
        fixtures = {
            "/configs": {"mode": "rule", "secret": "never-leak"},
            "/proxies/GITHUB": {"now": "AUTO", "all": ["AUTO", "Fast node"]},
            "/proxies/AUTO": {"now": "Fast node"},
            "/providers/proxies/subscription": {
                "updatedAt": "2026-08-24T00:00:00Z",
                "subscriptionInfo": {"Upload": 1},
                "proxies": [
                    {
                        "name": "Fast node",
                        "type": "ss",
                        "alive": True,
                        "server": "never-leak.example",
                        "password": "never-leak",
                        "history": [{"delay": 72}],
                    }
                ],
            },
        }
        return fixtures[path]


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ui_root = self.root / "operator-ui"
        self.ui_root.mkdir()
        (self.ui_root / "index.html").write_text("<!doctype html><title>测试</title><main>进入你的服务器工作空间</main><script src='/static/app.js'></script>", "utf-8")
        (self.ui_root / "app.css").write_text("html{font:14px sans-serif}", "utf-8")
        (self.ui_root / "app.js").write_text("function renderPlanner(){}", "utf-8")
        self.accounts = AccountStore(self.root / "data")
        self.admin = self.accounts.bootstrap_admin("admin", ADMIN_PASSWORD)
        self.alice = self.accounts.create_account("alice", USER_PASSWORD)
        self.bob = self.accounts.create_account("bob", USER_PASSWORD)
        self.shared = SharedStore(
            self.accounts.shared_root / "platform.sqlite3",
            conversation_max_messages=10,
            conversation_max_bytes=2_000,
            account_message_max_bytes=4_000,
            global_message_max_bytes=8_000,
            worker_lease_seconds=30,
        )
        self.proxy = FakeProxy()
        self.server = create_server(
            "127.0.0.1",
            0,
            accounts=self.accounts,
            shared=self.shared,
            proxy_controller=self.proxy,
            ui_root=self.ui_root,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.admin_token = self.login("admin", ADMIN_PASSWORD)["session"]["token"]
        self.alice_token = self.login("alice", USER_PASSWORD)["session"]["token"]
        self.bob_token = self.login("bob", USER_PASSWORD)["session"]["token"]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload=None,
        token: str | None = None,
        scheme: str = "Bearer",
        origin: str | None = None,
        cookie: str | None = None,
        csrf: str | None = None,
    ):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"{scheme} {token}"
        if origin:
            headers["Origin"] = origin
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                body = json.loads(raw) if raw and response.headers.get_content_type() == "application/json" else raw
                return response.status, body, response.headers
        except HTTPError as error:
            raw = error.read()
            body = json.loads(raw) if raw and error.headers.get_content_type() == "application/json" else raw
            return error.code, body, error.headers

    def login(self, username, password):
        status, body, _headers = self.request(
            "/api/v1/auth/login", method="POST", payload={"username": username, "password": password}
        )
        self.assertEqual(status, 200, body)
        return body

    def connect_alice_and_bob(self):
        status, body, _ = self.request(
            "/api/v1/connections/requests",
            method="POST",
            payload={"account_id": self.bob["id"]},
            token=self.alice_token,
        )
        self.assertEqual(status, 201, body)
        status, body, _ = self.request(
            f"/api/v1/connections/{self.alice['id']}/accept",
            method="POST",
            payload={},
            token=self.bob_token,
        )
        self.assertEqual(status, 200, body)

    def test_root_replaces_clock_and_public_chat(self):
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")
        self.assertIn("进入你的服务器工作空间", html)
        self.assertNotIn("clock", html.lower())
        self.assertNotIn("公共聊天", html)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        status, body, _ = self.request("/api/v1/meta")
        self.assertEqual(status, 200)
        self.assertTrue(body["ui_bundled"])
        status, css, _ = self.request("/static/app.css")
        self.assertEqual(status, 200)
        self.assertIn(b"font:14px", css)
        status, javascript, _ = self.request("/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"renderPlanner", javascript)
        status, body, _ = self.request("/api/messages")
        self.assertEqual(status, 404)

    def test_api_only_default_does_not_bundle_operator_ui(self):
        api_only = create_server(
            "127.0.0.1",
            0,
            accounts=self.accounts,
            shared=self.shared,
            proxy_controller=self.proxy,
        )
        thread = threading.Thread(target=api_only.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{api_only.server_address[1]}/", timeout=5) as response:
                body = json.loads(response.read())
            self.assertFalse(body["ui_bundled"])
        finally:
            api_only.shutdown()
            api_only.server_close()
            thread.join(timeout=2)

    def test_account_pool_is_sibling_isolated_and_passwords_are_hashed(self):
        account_directories = sorted(path.name for path in (self.root / "data" / "accounts").iterdir() if path.is_dir())
        self.assertEqual(account_directories, sorted([self.admin["id"], self.alice["id"], self.bob["id"]]))
        identity_text = (self.root / "data" / "accounts" / self.alice["id"] / "identity.json").read_text("utf-8")
        self.assertNotIn(USER_PASSWORD, identity_text)
        self.assertIn('"algorithm": "scrypt"', identity_text)
        with self.assertRaisesRegex(ValueError, "已初始化"):
            self.accounts.bootstrap_admin("secondadmin", ADMIN_PASSWORD)

    def test_admin_manages_accounts_without_password_readback(self):
        status, body, _ = self.request(
            "/api/v1/admin/accounts",
            method="POST",
            payload={"username": "charlie", "password": "Another strong password 789!"},
            token=self.alice_token,
        )
        self.assertEqual(status, 403)
        status, body, _ = self.request(
            "/api/v1/admin/accounts",
            method="POST",
            payload={"username": "charlie", "password": "Another strong password 789!"},
            token=self.admin_token,
        )
        self.assertEqual(status, 201, body)
        self.assertNotIn("password", body["account"])
        account_id = body["account"]["id"]
        status, body, _ = self.request(
            f"/api/v1/admin/accounts/{account_id}/password",
            method="POST",
            payload={"password": "Reset password is secure 123!"},
            token=self.admin_token,
        )
        self.assertEqual(status, 200, body)
        self.login("charlie", "Reset password is secure 123!")

    def test_profile_avatar_settings_and_remarks_are_private_per_account(self):
        status, body, _ = self.request(
            "/api/v1/me/profile",
            method="PATCH",
            payload={"nickname": "Alice 的工作台", "avatar_data_url": PNG_DATA_URL},
            token=self.alice_token,
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["profile"]["nickname"], "Alice 的工作台")
        status, body, _ = self.request(
            "/api/v1/me/settings",
            method="PATCH",
            payload={"theme": "dark", "proxy": {"preferred_mode": "direct", "preferred_selection": "Fast node"}},
            token=self.alice_token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "unknown_setting")
        status, _body, _ = self.request(
            "/api/v1/me/settings",
            method="PATCH",
            payload={"theme": "dark"},
            token=self.alice_token,
        )
        self.assertEqual(status, 200)
        self.assertNotIn("proxy", self.accounts.settings(self.alice["id"]))
        status, body, _ = self.request(
            f"/api/v1/users/{self.bob['id']}/remark",
            method="PUT",
            payload={"remark": "设计协作者"},
            token=self.alice_token,
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("/api/v1/users", token=self.alice_token)
        bob = next(item for item in body["users"] if item["id"] == self.bob["id"])
        self.assertEqual(bob["remark"], "设计协作者")
        status, body, _ = self.request("/api/v1/me", token=self.bob_token)
        self.assertEqual(body["settings"]["theme"], "system")
        self.assertEqual(body["profile"]["nickname"], "bob")
        status, image, headers = self.request(f"/api/v1/users/{self.alice['id']}/avatar", token=self.bob_token)
        self.assertEqual(status, 200)
        self.assertTrue(image.startswith(b"\x89PNG"))
        self.assertEqual(headers.get_content_type(), "image/png")

    def test_planner_web_is_read_only_and_device_updates_are_isolated(self):
        status, body, _ = self.request(
            "/api/v1/me/devices",
            method="POST",
            payload={"name": "IrohaWalendar desktop", "scope": "planner_sync"},
            token=self.alice_token,
        )
        self.assertEqual(status, 201, body)
        device_token = body["device"]["token"]
        snapshot = {
            "version": 5,
            "revision": 1,
            "source_updated_at": "2026-08-24T10:00:00Z",
            "goals": [{"id": "goal-1", "name": "学习"}],
            "actions": [],
            "routineCategories": [],
            "routines": [],
            "plans": [],
            "completionRecords": [],
            "settings": {"view": "week", "dayStartMinute": 300, "apiToken": "must-not-sync"},
        }
        status, body, _ = self.request(
            "/api/v1/planner/snapshot", method="PUT", payload=snapshot, token=self.alice_token
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "device_token_required")
        status, body, _ = self.request(
            "/api/v1/planner/snapshot", method="PUT", payload=snapshot, token=device_token, scheme="Device"
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("/api/v1/planner/snapshot", token=self.alice_token)
        self.assertTrue(body["read_only"])
        self.assertEqual(body["snapshot"]["goals"][0]["name"], "学习")
        self.assertEqual(body["snapshot"]["settings"], {"dayStartMinute": 300})
        status, body, _ = self.request("/api/v1/planner/snapshot", token=self.bob_token)
        self.assertEqual(body["snapshot"]["goals"], [])
        status, body, _ = self.request("/api/v1/me/devices", token=self.alice_token)
        self.assertEqual(len(body["devices"]), 1)
        device_id = body["devices"][0]["id"]
        status, body, _ = self.request(
            f"/api/v1/me/devices/{device_id}", method="DELETE", payload={}, token=self.alice_token
        )
        self.assertEqual(status, 200, body)
        snapshot["revision"] = 2
        status, body, _ = self.request(
            "/api/v1/planner/snapshot", method="PUT", payload=snapshot, token=device_token, scheme="Device"
        )
        self.assertEqual(status, 401)

    def test_connections_gate_private_messages(self):
        status, body, _ = self.request(
            f"/api/v1/conversations/{self.bob['id']}/messages",
            method="POST",
            payload={"text": "before connection"},
            token=self.alice_token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "not_connected")
        self.connect_alice_and_bob()
        status, body, _ = self.request(
            f"/api/v1/conversations/{self.bob['id']}/messages",
            method="POST",
            payload={"text": "hello from Alice"},
            token=self.alice_token,
        )
        self.assertEqual(status, 201, body)
        status, body, _ = self.request(
            f"/api/v1/conversations/{self.alice['id']}/messages", token=self.bob_token
        )
        self.assertEqual(body["messages"][0]["text"], "hello from Alice")
        status, body, _ = self.request(
            f"/api/v1/conversations/{self.alice['id']}/messages", token=self.admin_token
        )
        self.assertEqual(status, 400)

    def test_message_store_prunes_oldest_under_hard_quota(self):
        quota_store = SharedStore(
            self.accounts.shared_root / "quota.sqlite3",
            conversation_max_messages=100,
            conversation_max_bytes=12,
            account_message_max_bytes=20,
            global_message_max_bytes=20,
        )
        quota_store.request_connection(self.alice["id"], self.bob["id"])
        quota_store.act_on_connection(self.bob["id"], self.alice["id"], "accept")
        quota_store.send_message(self.alice["id"], self.bob["id"], "1234567890")
        quota_store.send_message(self.bob["id"], self.alice["id"], "abcdefghij")
        messages = quota_store.messages(self.alice["id"], self.bob["id"])
        self.assertEqual([item["text"] for item in messages], ["abcdefghij"])
        self.assertLessEqual(quota_store.message_usage()["bytes"], 12)

    def test_structured_blog_and_reviewed_custom_page(self):
        status, body, _ = self.request(
            "/api/v1/blog/me",
            method="PUT",
            payload={
                "title": "Alice 的博客",
                "summary": "图像与文本",
                "blocks": [
                    {"type": "text", "text": "第一篇内容"},
                    {"type": "image", "data_url": PNG_DATA_URL, "alt": "测试图"},
                ],
            },
            token=self.alice_token,
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request(f"/api/v1/blogs/{self.alice['id']}", token=self.bob_token)
        self.assertEqual(body["blog"]["title"], "Alice 的博客")
        status, body, _ = self.request(
            "/api/v1/blog/me/custom",
            method="POST",
            payload={"html": "<!doctype html><html><body><script>alert(1)</script></body></html>"},
            token=self.alice_token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "unsafe_blog_html")
        safe_html = "<!doctype html><html lang='zh-CN'><head><title>A</title><style>body{color:#222}</style></head><body><main><h1>自定义页面</h1><p>安全内容</p></main></body></html>"
        status, body, _ = self.request(
            "/api/v1/blog/me/custom", method="POST", payload={"html": safe_html}, token=self.alice_token
        )
        self.assertEqual(status, 202, body)
        revision = body["review"]["revision_id"]
        status, body, _ = self.request(
            f"/api/v1/admin/blog-reviews/{self.alice['id']}/{revision}",
            method="POST",
            payload={"decision": "approved", "note": "无脚本与外链"},
            token=self.admin_token,
        )
        self.assertEqual(status, 200, body)
        status, page, headers = self.request(
            f"/blogs/{self.alice['id']}/custom/{revision}", token=self.bob_token
        )
        self.assertEqual(status, 200)
        self.assertIn("自定义页面", page.decode("utf-8"))
        self.assertIn("sandbox", headers["Content-Security-Policy"])

    def test_inference_dispatch_has_worker_lease_and_owner_isolation(self):
        status, body, _ = self.request(
            "/api/v1/inference/tasks",
            method="POST",
            payload={
                "instruction": "为这段文本安排离线推理",
                "priority": 7,
                "parameters": {"model": "local-model", "temperature": 0.7, "max_tokens": 512, "precision": "fp16"},
            },
            token=self.alice_token,
        )
        self.assertEqual(status, 202, body)
        task_id = body["task"]["id"]
        status, body, _ = self.request(
            "/api/v1/admin/workers",
            method="POST",
            payload={"name": "Desktop inference monitor"},
            token=self.admin_token,
        )
        self.assertEqual(status, 201, body)
        worker_token = body["worker"]["token"]
        status, body, _ = self.request(
            "/api/v1/workers/tasks/claim", method="POST", payload={}, token=worker_token, scheme="Worker"
        )
        self.assertEqual(status, 200, body)
        lease = body["task"]["lease_token"]
        self.assertEqual(body["task"]["id"], task_id)
        status, body, _ = self.request(
            f"/api/v1/workers/tasks/{task_id}/progress",
            method="POST",
            payload={"lease_token": lease, "progress": 0.5, "phase_label": "正在推理"},
            token=worker_token,
            scheme="Worker",
        )
        self.assertEqual(body["task"]["progress"], 0.5)
        status, body, _ = self.request(
            f"/api/v1/workers/tasks/{task_id}/complete",
            method="POST",
            payload={"lease_token": lease, "result": {"text": "生成内容", "artifacts": []}},
            token=worker_token,
            scheme="Worker",
        )
        self.assertEqual(body["task"]["status"], "succeeded")
        status, body, _ = self.request(f"/api/v1/inference/tasks/{task_id}", token=self.alice_token)
        self.assertEqual(body["task"]["result"]["text"], "生成内容")
        status, _body, _ = self.request(f"/api/v1/inference/tasks/{task_id}", token=self.bob_token)
        self.assertEqual(status, 404)

    def test_proxy_is_integrated_and_mutation_is_admin_only(self):
        status, body, _ = self.request("/api/v1/proxy/status", token=self.alice_token)
        self.assertEqual(status, 403)
        status, body, _ = self.request("/api/v1/proxy/status", token=self.admin_token)
        self.assertEqual(status, 200)
        self.assertEqual(body["proxy"]["mode"], "rule")
        status, _body, _ = self.request(
            "/api/v1/proxy/mode", method="POST", payload={"mode": "direct"}, token=self.alice_token
        )
        self.assertEqual(status, 403)
        status, body, _ = self.request(
            "/api/v1/proxy/mode", method="POST", payload={"mode": "direct"}, token=self.admin_token
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(self.proxy.mode, "direct")
        encoded = json.dumps(FixtureMihomoClient().status())
        self.assertNotIn("never-leak", encoded)
        self.assertNotIn("subscriptionInfo", encoded)

    def test_unexpected_internal_errors_are_sanitized(self):
        def broken_status():
            raise RuntimeError("internal detail must not leak")

        self.proxy.status = broken_status
        status, body, _ = self.request("/api/v1/proxy/status", token=self.admin_token)
        self.assertEqual(status, 500, body)
        self.assertEqual(body["error"]["code"], "internal_error")
        self.assertNotIn("internal detail", json.dumps(body))
        status, body, _ = self.request("/api/v1/health")
        self.assertEqual(status, 200, body)

    def test_cross_origin_and_cookie_csrf_are_rejected(self):
        status, body, _ = self.request(
            "/api/v1/me/settings",
            method="PATCH",
            payload={"theme": "dark"},
            token=self.alice_token,
            origin="https://attacker.example",
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "origin_not_allowed")
        status, login, login_headers = self.request(
            "/api/v1/auth/login", method="POST", payload={"username": "alice", "password": USER_PASSWORD}
        )
        self.assertEqual(status, 200, login)
        cookies = login_headers.get_all("Set-Cookie")
        self.assertTrue(any(item.startswith("cp_session=") and "HttpOnly" in item for item in cookies))
        self.assertTrue(any(item.startswith("cp_csrf=") and "HttpOnly" not in item for item in cookies))
        status, body, _ = self.request(
            "/api/v1/me/settings",
            method="PATCH",
            payload={"theme": "dark"},
            cookie=f"cp_session={login['session']['token']}",
        )
        self.assertEqual(status, 401)
        status, body, _ = self.request(
            "/api/v1/me/settings",
            method="PATCH",
            payload={"theme": "dark"},
            cookie=f"cp_session={login['session']['token']}",
            csrf=login["session"]["csrf_token"],
        )
        self.assertEqual(status, 200, body)


if __name__ == "__main__":
    unittest.main()
