#!/usr/bin/env python3
"""Serve the authenticated management API and an optional reviewed UI directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .blog import BlogManager
from .planner import validate_planner_snapshot
from .proxy import MihomoClient, ProxyError
from .security import ValidationError, compact_json_size, validate_json_shape
from .shared import SharedStore
from .storage import AccountStore


MAX_BODY_BYTES = 13 * 1024 * 1024
MAX_INFERENCE_RESULT_BYTES = 2 * 1024 * 1024
SESSION_COOKIE = "cp_session"
CSRF_COOKIE = "cp_csrf"
SESSION_MAX_AGE = 12 * 60 * 60
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 5
INFERENCE_PARAMETER_KEYS = {
    "model", "adapter", "temperature", "top_p", "max_tokens", "seed", "batch_size", "precision", "device", "extra"
}


class ManagementServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        accounts: AccountStore,
        shared: SharedStore,
        proxy_controller: Any,
        *,
        secure_cookie: bool = False,
        ui_root: str | Path | None = None,
    ) -> None:
        super().__init__(address, ManagementRequestHandler)
        self.accounts = accounts
        self.shared = shared
        self.blogs = BlogManager(accounts, shared)
        self.proxy_controller = proxy_controller
        self.secure_cookie = secure_cookie
        self.ui_root = Path(ui_root).resolve() if ui_root else None
        self.login_failures: dict[str, list[float]] = {}
        self.login_lock = threading.Lock()


class ManagementRequestHandler(BaseHTTPRequestHandler):
    server: ManagementServer
    server_version = "AccountControlPlane/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._security_headers()
        self.send_header("Allow", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _dispatch(self, method: str) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if method == "GET" and path == "/":
                if self.server.ui_root is None:
                    self._send_json(HTTPStatus.OK, self._meta_payload())
                else:
                    self._serve_ui_file("index.html", "text/html; charset=utf-8")
                return
            if method == "GET" and path == "/static/app.css":
                self._serve_ui_file("app.css", "text/css; charset=utf-8")
                return
            if method == "GET" and path == "/static/app.js":
                self._serve_ui_file("app.js", "text/javascript; charset=utf-8")
                return
            if method == "GET" and path == "/favicon.ico":
                self._send_empty(HTTPStatus.NO_CONTENT)
                return
            if method == "GET" and path == "/api/v1/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "initialized": bool(self.server.accounts.list_accounts()),
                        "message_usage": self.server.shared.message_usage(),
                    },
                )
                return
            if method == "GET" and path == "/api/v1/meta":
                self._send_json(
                    HTTPStatus.OK,
                    self._meta_payload(),
                )
                return
            if method == "POST" and path == "/api/v1/auth/login":
                self._login()
                return
            if method == "POST" and path == "/api/v1/auth/logout":
                user, token = self._require_user(mutation=True)
                self.server.accounts.revoke_session(token)
                self._send_json(HTTPStatus.OK, {"status": "ok"}, clear_cookie=True)
                return

            if method == "GET" and path == "/api/v1/me":
                user, _token = self._require_user()
                self._send_json(
                    HTTPStatus.OK,
                    {"account": user, "profile": self.server.accounts.profile(user["id"]), "settings": self.server.accounts.settings(user["id"])},
                )
                return
            if method == "PATCH" and path == "/api/v1/me/profile":
                user, _token = self._require_user(mutation=True)
                self._send_json(HTTPStatus.OK, {"profile": self.server.accounts.update_profile(user["id"], self._read_json())})
                return
            if method == "PATCH" and path == "/api/v1/me/settings":
                user, _token = self._require_user(mutation=True)
                self._send_json(HTTPStatus.OK, {"settings": self.server.accounts.update_settings(user["id"], self._read_json())})
                return
            if method == "GET" and path == "/api/v1/users":
                user, _token = self._require_user()
                self._list_users(user)
                return

            match = re.fullmatch(r"/api/v1/users/([0-9a-f]{32})/avatar", path)
            if method == "GET" and match:
                self._require_user()
                self._serve_avatar(match.group(1))
                return
            match = re.fullmatch(r"/api/v1/users/([0-9a-f]{32})/remark", path)
            if method == "PUT" and match:
                user, _token = self._require_user(mutation=True)
                remark = self.server.accounts.set_remark(user["id"], match.group(1), self._read_json().get("remark"))
                self._send_json(HTTPStatus.OK, {"account_id": match.group(1), "remark": remark})
                return

            if path == "/api/v1/admin/accounts" and method in {"GET", "POST"}:
                admin, _token = self._require_admin(mutation=method != "GET")
                if method == "GET":
                    self._send_json(HTTPStatus.OK, {"accounts": self.server.accounts.list_accounts()})
                else:
                    payload = self._read_json()
                    created = self.server.accounts.create_account(payload.get("username"), payload.get("password"), role=str(payload.get("role") or "user"))
                    self._send_json(HTTPStatus.CREATED, {"account": created})
                return
            match = re.fullmatch(r"/api/v1/admin/accounts/([0-9a-f]{32})", path)
            if method == "PATCH" and match:
                admin, _token = self._require_admin(mutation=True)
                payload = self._read_json()
                unknown = set(payload) - {"disabled", "role"}
                if unknown:
                    raise ValidationError("unknown_account_field", "账号更新包含不支持的字段。")
                updated = self.server.accounts.update_account(match.group(1), disabled=payload.get("disabled"), role=payload.get("role"))
                self._send_json(HTTPStatus.OK, {"account": updated})
                return
            match = re.fullmatch(r"/api/v1/admin/accounts/([0-9a-f]{32})/password", path)
            if method == "POST" and match:
                admin, _token = self._require_admin(mutation=True)
                self.server.accounts.reset_password(match.group(1), self._read_json().get("password"))
                self._send_json(HTTPStatus.OK, {"status": "password_reset"})
                return

            if path == "/api/v1/me/devices" and method in {"GET", "POST"}:
                user, _token = self._require_user(mutation=method == "POST")
                if method == "GET":
                    self._send_json(HTTPStatus.OK, {"devices": self.server.accounts.list_devices(user["id"])})
                    return
                payload = self._read_json()
                device = self.server.accounts.create_device(user["id"], payload.get("name"), str(payload.get("scope") or "planner_sync"))
                self._send_json(HTTPStatus.CREATED, {"device": device})
                return
            match = re.fullmatch(r"/api/v1/me/devices/([0-9a-f]{32})", path)
            if method == "DELETE" and match:
                user, _token = self._require_user(mutation=True)
                self.server.accounts.revoke_device(user["id"], match.group(1))
                self._send_json(HTTPStatus.OK, {"status": "revoked"})
                return
            if method == "GET" and path == "/api/v1/planner/snapshot":
                user, _token = self._require_user()
                self._send_json(HTTPStatus.OK, {"snapshot": self.server.accounts.planner(user["id"]), "read_only": True})
                return
            if method == "PUT" and path == "/api/v1/planner/snapshot":
                device = self._require_device("planner_sync")
                snapshot = validate_planner_snapshot(self._read_json())
                stored = self.server.accounts.write_planner(device["account_id"], snapshot)
                self._send_json(HTTPStatus.OK, {"revision": stored["revision"], "received_at": stored["received_at"]})
                return

            if method == "GET" and path == "/api/v1/connections":
                user, _token = self._require_user()
                self._send_json(HTTPStatus.OK, {"connections": self.server.shared.list_connections(user["id"])})
                return
            if method == "POST" and path == "/api/v1/connections/requests":
                user, _token = self._require_user(mutation=True)
                target = str(self._read_json().get("account_id") or "")
                if not self.server.accounts.account_exists(target):
                    raise ValidationError("account_not_found", "申请目标账号不存在。")
                record = self.server.shared.request_connection(user["id"], target)
                self._send_json(HTTPStatus.CREATED, {"connection": record})
                return
            match = re.fullmatch(r"/api/v1/connections/([0-9a-f]{32})/(accept|reject|cancel)", path)
            if method == "POST" and match:
                user, _token = self._require_user(mutation=True)
                record = self.server.shared.act_on_connection(user["id"], match.group(1), match.group(2))
                self._send_json(HTTPStatus.OK, {"connection": record})
                return
            match = re.fullmatch(r"/api/v1/conversations/([0-9a-f]{32})/messages", path)
            if match and method in {"GET", "POST"}:
                user, _token = self._require_user(mutation=method == "POST")
                target = match.group(1)
                if method == "GET":
                    query = parse_qs(parsed.query)
                    after = self._query_int(query, "after", 0)
                    limit = self._query_int(query, "limit", 100)
                    self._send_json(HTTPStatus.OK, {"messages": self.server.shared.messages(user["id"], target, after=after, limit=limit)})
                else:
                    message = self.server.shared.send_message(user["id"], target, self._read_json().get("text"))
                    self._send_json(HTTPStatus.CREATED, {"message": message})
                return

            if method == "PUT" and path == "/api/v1/blog/me":
                user, _token = self._require_user(mutation=True)
                manifest = self.server.blogs.publish_structured(user["id"], self._read_json())
                self._send_json(HTTPStatus.OK, {"blog": manifest})
                return
            if method == "POST" and path == "/api/v1/blog/me/custom":
                user, _token = self._require_user(mutation=True)
                review = self.server.blogs.submit_custom(user["id"], self._read_json().get("html"))
                self._send_json(HTTPStatus.ACCEPTED, {"review": review})
                return
            if method == "GET" and path == "/api/v1/blog/me/custom/reviews":
                user, _token = self._require_user()
                self._send_json(HTTPStatus.OK, {"reviews": self.server.shared.blog_reviews_for_account(user["id"])})
                return
            if method == "GET" and path == "/api/v1/admin/blog-reviews":
                self._require_admin()
                self._send_json(HTTPStatus.OK, {"reviews": self.server.shared.pending_blog_reviews()})
                return
            match = re.fullmatch(r"/api/v1/admin/blog-reviews/([0-9a-f]{32})/([0-9a-f]{32})", path)
            if method == "POST" and match:
                admin, _token = self._require_admin(mutation=True)
                payload = self._read_json()
                review = self.server.blogs.review(
                    admin["id"], match.group(1), match.group(2), str(payload.get("decision") or ""), str(payload.get("note") or "")
                )
                self._send_json(HTTPStatus.OK, {"review": review})
                return
            match = re.fullmatch(r"/api/v1/blogs/([0-9a-f]{32})", path)
            if method == "GET" and match:
                self._require_user()
                self._send_json(HTTPStatus.OK, {"blog": self.server.blogs.public_blog(match.group(1))})
                return
            match = re.fullmatch(r"/api/v1/blogs/([0-9a-f]{32})/assets/([0-9a-f]{32}\.(?:png|jpg|webp))", path)
            if method == "GET" and match:
                self._require_user()
                self._serve_blog_asset(match.group(1), match.group(2))
                return
            match = re.fullmatch(r"/blogs/([0-9a-f]{32})/custom/([0-9a-f]{32})", path)
            if method == "GET" and match:
                self._require_user()
                self._serve_custom_blog(match.group(1), match.group(2))
                return

            if path == "/api/v1/inference/tasks" and method in {"GET", "POST"}:
                user, _token = self._require_user(mutation=method == "POST")
                if method == "GET":
                    self._send_json(HTTPStatus.OK, {"tasks": self.server.shared.tasks_for_owner(user["id"])})
                else:
                    task = self._create_inference_task(user["id"], self._read_json())
                    self._send_json(HTTPStatus.ACCEPTED, {"task": task})
                return
            match = re.fullmatch(r"/api/v1/inference/tasks/([0-9a-f]{32})", path)
            if method == "GET" and match:
                user, _token = self._require_user()
                task = self.server.shared.task_for_owner(user["id"], match.group(1))
                if not task:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "task_not_found", "message": "推理任务不存在。"}})
                else:
                    self._send_json(HTTPStatus.OK, {"task": task})
                return
            match = re.fullmatch(r"/api/v1/inference/tasks/([0-9a-f]{32})/cancel", path)
            if method == "POST" and match:
                user, _token = self._require_user(mutation=True)
                self._send_json(HTTPStatus.OK, {"task": self.server.shared.cancel_task(user["id"], match.group(1))})
                return
            if method == "POST" and path == "/api/v1/admin/workers":
                self._require_admin(mutation=True)
                worker = self.server.shared.create_worker(self._read_json().get("name"))
                self._send_json(HTTPStatus.CREATED, {"worker": worker})
                return
            if method == "POST" and path == "/api/v1/workers/tasks/claim":
                worker = self._require_worker()
                self._send_json(HTTPStatus.OK, {"task": self.server.shared.claim_task(worker["id"])})
                return
            match = re.fullmatch(r"/api/v1/workers/tasks/([0-9a-f]{32})/(progress|complete)", path)
            if method == "POST" and match:
                worker = self._require_worker()
                payload = self._read_json()
                lease_token = str(payload.get("lease_token") or "")
                if match.group(2) == "progress":
                    progress = float(payload.get("progress", 0))
                    label = str(payload.get("phase_label") or "处理中").strip()
                    if not 0 <= progress <= 1 or not label or len(label) > 120:
                        raise ValidationError("invalid_progress", "任务进度或阶段说明无效。")
                    task = self.server.shared.update_task_progress(worker["id"], match.group(1), lease_token, progress, label)
                else:
                    result = payload.get("result")
                    error = str(payload.get("error") or "").strip() or None
                    if result is not None:
                        if not isinstance(result, dict):
                            raise ValidationError("invalid_result", "任务结果必须是 JSON 对象。")
                        validate_json_shape(result)
                        if compact_json_size(result) > MAX_INFERENCE_RESULT_BYTES:
                            raise ValidationError("result_too_large", "任务结果超过 2 MiB 限制。")
                    if error and len(error) > 2_000:
                        raise ValidationError("error_too_long", "错误信息过长。")
                    task = self.server.shared.complete_task(worker["id"], match.group(1), lease_token, result=result, error=error)
                self._send_json(HTTPStatus.OK, {"task": task})
                return

            if method == "GET" and path == "/api/v1/proxy/status":
                self._require_admin()
                self._send_json(HTTPStatus.OK, {"proxy": self.server.proxy_controller.status()})
                return
            if method == "POST" and path in {"/api/v1/proxy/mode", "/api/v1/proxy/selection", "/api/v1/proxy/refresh"}:
                self._require_admin(mutation=True)
                payload = self._read_json()
                if path.endswith("/mode"):
                    self.server.proxy_controller.set_mode(str(payload.get("mode") or ""))
                elif path.endswith("/selection"):
                    self.server.proxy_controller.set_selection(str(payload.get("name") or ""))
                else:
                    self.server.proxy_controller.refresh_provider()
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "not_found", "message": "接口不存在。"}})
        except ValidationError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"code": error.code, "message": error.message}})
        except ProxyError as error:
            self._send_json(error.status, {"error": {"code": error.code, "message": "代理控制器请求失败。"}})
        except PermissionError as error:
            code = str(error) or "forbidden"
            status = HTTPStatus.UNAUTHORIZED if code == "unauthorized" else HTTPStatus.FORBIDDEN
            self._send_json(status, {"error": {"code": code, "message": "没有执行此操作的权限。"}})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"code": "invalid_json", "message": "请求体不是有效 JSON。"}})
        except (TypeError, ValueError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"code": "invalid_value", "message": "请求字段值无效。"}})
        except Exception as error:
            self.log_error("unhandled request error (%s)", type(error).__name__)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": {"code": "internal_error", "message": "服务器处理请求时发生内部错误。"}},
            )

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc == self.headers.get("Host", "")

    def _session_credentials(self) -> tuple[str | None, bool]:
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            return authorization[7:].strip(), False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return None, True
        morsel = cookie.get(SESSION_COOKIE)
        return (morsel.value if morsel else None), True

    def _require_user(self, *, mutation: bool = False) -> tuple[dict[str, Any], str]:
        if mutation and not self._origin_allowed():
            raise PermissionError("origin_not_allowed")
        token, cookie_auth = self._session_credentials()
        csrf = self.headers.get("X-CSRF-Token") if mutation and cookie_auth else None
        if not token or (mutation and cookie_auth and not csrf):
            raise PermissionError("unauthorized")
        user = self.server.accounts.verify_session(token, csrf=csrf)
        if not user:
            raise PermissionError("unauthorized")
        return user, token

    def _require_admin(self, *, mutation: bool = False) -> tuple[dict[str, Any], str]:
        user, token = self._require_user(mutation=mutation)
        if user["role"] != "admin":
            raise PermissionError("admin_required")
        return user, token

    def _require_device(self, scope: str) -> dict[str, str]:
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Device "):
            raise PermissionError("device_token_required")
        device = self.server.accounts.verify_device(authorization[7:].strip(), scope)
        if not device:
            raise PermissionError("unauthorized")
        return device

    def _require_worker(self) -> dict[str, str]:
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Worker "):
            raise PermissionError("worker_token_required")
        worker = self.server.shared.verify_worker(authorization[7:].strip())
        if not worker:
            raise PermissionError("unauthorized")
        return worker

    def _login(self) -> None:
        if not self._origin_allowed():
            raise PermissionError("origin_not_allowed")
        payload = self._read_json()
        username = str(payload.get("username") or "").strip()
        key = f"{self.client_address[0]}:{username.casefold()}"
        now = time.monotonic()
        with self.server.login_lock:
            failures = [item for item in self.server.login_failures.get(key, []) if now - item < LOGIN_WINDOW_SECONDS]
            if len(failures) >= LOGIN_MAX_FAILURES:
                self._send_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"error": {"code": "login_rate_limited", "message": "登录失败次数过多，请稍后再试。"}},
                )
                return
        user = self.server.accounts.authenticate_password(username, payload.get("password"))
        if not user:
            with self.server.login_lock:
                self.server.login_failures[key] = failures + [now]
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"error": {"code": "invalid_credentials", "message": "账号或密码不正确。"}},
            )
            return
        with self.server.login_lock:
            self.server.login_failures.pop(key, None)
        session = self.server.accounts.create_session(user["id"])
        self._send_json(
            HTTPStatus.OK,
            {"account": user, "session": session},
            session_cookie=session["token"],
            csrf_cookie=session["csrf_token"],
        )

    def _list_users(self, viewer: dict[str, Any]) -> None:
        remarks = self.server.accounts.remarks(viewer["id"])
        connections = {item["account_id"]: item for item in self.server.shared.list_connections(viewer["id"])}
        users = []
        for account in self.server.accounts.list_accounts():
            if account["id"] == viewer["id"] or (account["disabled"] and viewer["role"] != "admin"):
                continue
            item = dict(account)
            item["remark"] = remarks.get(account["id"], "")
            item["connection"] = connections.get(account["id"])
            users.append(item)
        self._send_json(HTTPStatus.OK, {"users": users})

    def _create_inference_task(self, owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        instruction = str(payload.get("instruction") or "").strip()
        parameters = payload.get("parameters", {})
        priority = int(payload.get("priority", 5))
        if not instruction or len(instruction) > 50_000:
            raise ValidationError("invalid_instruction", "推理指令须为 1–50000 个字符。")
        if not isinstance(parameters, dict) or set(parameters) - INFERENCE_PARAMETER_KEYS:
            raise ValidationError("invalid_parameters", "推理参数包含不支持的字段。")
        validate_json_shape(parameters)
        self._reject_sensitive_parameter_keys(parameters)
        if compact_json_size(parameters) > 32 * 1024 or not 0 <= priority <= 9:
            raise ValidationError("invalid_parameters", "推理参数或优先级超过限制。")
        return self.server.shared.create_task(owner_id, instruction, parameters, priority)

    @staticmethod
    def _reject_sensitive_parameter_keys(value: Any) -> None:
        blocked = {"path", "file", "url", "command", "shell", "token", "secret", "password", "credential"}
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = key.casefold()
                if (
                    lowered in blocked
                    or any(lowered.endswith(f"_{part}") for part in blocked)
                    or any(lowered.startswith(f"{part}_") for part in blocked)
                ):
                    raise ValidationError("unsafe_parameter", "推理参数不能下达文件路径、命令、URL 或凭据。")
                ManagementRequestHandler._reject_sensitive_parameter_keys(child)
        elif isinstance(value, list):
            for child in value:
                ManagementRequestHandler._reject_sensitive_parameter_keys(child)

    def _read_json(self) -> dict[str, Any]:
        if self.headers.get_content_type() != "application/json":
            raise ValidationError("json_required", "请求必须使用 application/json。")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValidationError("invalid_content_length", "请求长度无效。") from error
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValidationError("invalid_content_length", "请求体为空或超过限制。")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValidationError("json_object_required", "请求体必须是 JSON 对象。")
        return value

    @staticmethod
    def _query_int(query: dict[str, list[str]], key: str, default: int) -> int:
        try:
            return int(query.get(key, [str(default)])[0])
        except (TypeError, ValueError):
            return default

    def _serve_avatar(self, account_id: str) -> None:
        asset = self.server.accounts.avatar(account_id)
        if not asset:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "avatar_not_found", "message": "头像不存在。"}})
            return
        self._serve_file(asset[0], asset[1], "private, max-age=300")

    def _serve_blog_asset(self, account_id: str, name: str) -> None:
        path = self.server.blogs.asset(account_id, name)
        if not path:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "asset_not_found", "message": "博客资源不存在。"}})
            return
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]
        self._serve_file(path, mime, "private, max-age=300")

    def _serve_custom_blog(self, account_id: str, revision_id: str) -> None:
        path = self.server.blogs.custom_page(account_id, revision_id)
        if not path:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "blog_not_found", "message": "博客页面不存在。"}})
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header(
            "Content-Security-Policy",
            "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(content)

    def _serve_file(self, path: Path, content_type: str, cache_control: str) -> None:
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(content)

    def _serve_ui_file(self, name: str, content_type: str) -> None:
        if name not in {"index.html", "app.css", "app.js"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "not_found", "message": "资源不存在。"}})
            return
        if self.server.ui_root is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "ui_unavailable", "message": "未配置测试界面。"}})
            return
        path = self.server.ui_root / name
        if not path.is_file():
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": {"code": "ui_unavailable", "message": "测试界面尚未安装。"}})
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'none'; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store" if name == "index.html" else "private, max-age=300")
        self.end_headers()
        self.wfile.write(content)

    def _meta_payload(self) -> dict[str, Any]:
        return {
            "service": "authenticated-management-api",
            "api_version": "v1",
            "ui_bundled": self.server.ui_root is not None,
            "documentation": "BACKEND_GUIDE.md",
        }

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        *,
        session_cookie: str | None = None,
        csrf_cookie: str | None = None,
        clear_cookie: bool = False,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if session_cookie is not None:
            secure = "; Secure" if self.server.secure_cookie else ""
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={session_cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_MAX_AGE}{secure}")
            if csrf_cookie is not None:
                self.send_header("Set-Cookie", f"{CSRF_COOKIE}={csrf_cookie}; Path=/; SameSite=Strict; Max-Age={SESSION_MAX_AGE}{secure}")
        elif clear_cookie:
            secure = "; Secure" if self.server.secure_cookie else ""
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}")
            self.send_header("Set-Cookie", f"{CSRF_COOKIE}=; Path=/; SameSite=Strict; Max-Age=0{secure}")
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()


def create_server(
    host: str,
    port: int,
    *,
    data_root: str | Path | None = None,
    accounts: AccountStore | None = None,
    shared: SharedStore | None = None,
    proxy_controller: Any | None = None,
    secure_cookie: bool = False,
    ui_root: str | Path | None = None,
) -> ManagementServer:
    if accounts is None:
        root = Path(data_root or os.environ.get("APP_DATA_DIR", ".runtime/data"))
        accounts = AccountStore(root)
    if shared is None:
        shared = SharedStore(accounts.shared_root / "platform.sqlite3")
    if proxy_controller is None:
        proxy_controller = MihomoClient(os.environ.get("MIHOMO_SOCKET", "/run/mihomo/controller.sock"))
    return ManagementServer((host, port), accounts, shared, proxy_controller, secure_cookie=secure_cookie, ui_root=ui_root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "18761")))
    parser.add_argument("--data-root", default=os.environ.get("APP_DATA_DIR", ".runtime/data"))
    parser.add_argument("--mihomo-socket", default=os.environ.get("MIHOMO_SOCKET", "/run/mihomo/controller.sock"))
    parser.add_argument("--secure-cookie", action="store_true")
    parser.add_argument("--ui-root", default=os.environ.get("CONTROL_PLANE_UI_ROOT"), help="可选界面目录；可使用 control_plane/ui 基础模板，不配置时根路径只返回 API 元数据")
    args = parser.parse_args()
    server = create_server(
        args.host,
        args.port,
        data_root=args.data_root,
        proxy_controller=MihomoClient(args.mihomo_socket),
        secure_cookie=args.secure_cookie,
        ui_root=args.ui_root,
    )
    stopping = threading.Event()

    def request_shutdown(_signum: int, _frame: object) -> None:
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    print(f"Authenticated management API listening on http://{server.server_address[0]}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
