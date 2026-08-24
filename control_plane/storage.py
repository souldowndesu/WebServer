"""Filesystem-backed account isolation and owned data storage."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .security import (
    DUMMY_PASSWORD_HASH,
    ValidationError,
    canonical_username,
    decode_image_data_url,
    hash_password,
    new_token,
    token_digest,
    utc_now,
    validate_password,
    verify_password,
)


ACCOUNT_ID_LENGTH = 32
SESSION_TTL_HOURS = 12
DEVICE_TOKEN_LIMIT = 20
AVATAR_MAX_BYTES = 2 * 1024 * 1024
PLANNER_MAX_BYTES = 12 * 1024 * 1024


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _default_planner() -> dict[str, Any]:
    return {
        "version": 5,
        "revision": 0,
        "source_updated_at": None,
        "received_at": None,
        "goals": [],
        "actions": [],
        "routineCategories": [],
        "routines": [],
        "plans": [],
        "completionRecords": [],
        "settings": {},
    }


class AccountStore:
    """Owns the sibling account directories and never stores plaintext passwords."""

    def __init__(self, data_root: str | Path) -> None:
        self.root = Path(data_root).resolve()
        self.accounts_root = self.root / "accounts"
        self.shared_root = self.root / "shared"
        self.index_path = self.accounts_root / "index.json"
        self._lock = threading.RLock()
        self.accounts_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.shared_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.index_path.exists():
            _atomic_write_json(self.index_path, {"version": 1, "accounts": {}})

    def _index(self) -> dict[str, Any]:
        value = _read_json(self.index_path, {"version": 1, "accounts": {}})
        if not isinstance(value, dict) or not isinstance(value.get("accounts"), dict):
            raise RuntimeError("account_index_invalid")
        return value

    def _account_dir(self, account_id: str) -> Path:
        if len(account_id) != ACCOUNT_ID_LENGTH or any(char not in "0123456789abcdef" for char in account_id):
            raise ValidationError("invalid_account_id", "账号标识无效。")
        return self.accounts_root / account_id

    def account_exists(self, account_id: str) -> bool:
        try:
            path = self._account_dir(account_id)
        except ValidationError:
            return False
        return (path / "identity.json").is_file()

    def account_dir(self, account_id: str) -> Path:
        path = self._account_dir(account_id)
        if not (path / "identity.json").is_file():
            raise ValidationError("account_not_found", "账号不存在。")
        return path

    def bootstrap_admin(self, username: Any, password: Any) -> dict[str, Any]:
        with self._lock:
            if self._index()["accounts"]:
                raise ValidationError("already_initialized", "账号池已初始化。")
            return self.create_account(username, password, role="admin")

    def create_account(self, username: Any, password: Any, *, role: str = "user") -> dict[str, Any]:
        username = canonical_username(username)
        password = validate_password(password)
        if role not in {"admin", "user"}:
            raise ValidationError("invalid_role", "账号角色无效。")
        with self._lock:
            index = self._index()
            key = username.casefold()
            if key in index["accounts"]:
                raise ValidationError("username_exists", "账号名已存在。")
            account_id = uuid.uuid4().hex
            directory = self._account_dir(account_id)
            directory.mkdir(mode=0o700)
            for relative in ("avatars", "blog/assets", "blog/drafts", "blog/published"):
                (directory / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
            now = utc_now()
            identity = {
                "version": 1,
                "id": account_id,
                "username": username,
                "role": role,
                "disabled": False,
                "password": hash_password(password),
                "created_at": now,
                "updated_at": now,
            }
            _atomic_write_json(directory / "identity.json", identity)
            _atomic_write_json(
                directory / "profile.json",
                {"nickname": username, "avatar": None, "updated_at": now},
            )
            _atomic_write_json(
                directory / "settings.json",
                {
                    "theme": "system",
                    "locale": "zh-CN",
                    "proxy": {"preferred_mode": "rule", "preferred_selection": "AUTO"},
                    "updated_at": now,
                },
            )
            _atomic_write_json(directory / "social.json", {"remarks": {}, "updated_at": now})
            _atomic_write_json(directory / "sessions.json", {"sessions": []})
            _atomic_write_json(directory / "devices.json", {"devices": []})
            _atomic_write_json(directory / "planner.json", _default_planner())
            _atomic_write_json(
                directory / "blog" / "manifest.json",
                {"mode": "structured", "published": False, "title": "", "summary": "", "blocks": [], "updated_at": now},
            )
            index["accounts"][key] = {"id": account_id, "username": username}
            _atomic_write_json(self.index_path, index)
            return self.public_account(account_id)

    def identity(self, account_id: str) -> dict[str, Any]:
        value = _read_json(self.account_dir(account_id) / "identity.json", None)
        if not isinstance(value, dict):
            raise RuntimeError("identity_invalid")
        return value

    def account_id_for_username(self, username: Any) -> str | None:
        candidate = str(username or "").strip().casefold()
        if not candidate:
            return None
        record = self._index()["accounts"].get(candidate)
        return str(record["id"]) if isinstance(record, dict) and record.get("id") else None

    def authenticate_password(self, username: Any, password: Any) -> dict[str, Any] | None:
        account_id = self.account_id_for_username(username)
        if not account_id:
            verify_password(password, DUMMY_PASSWORD_HASH)
            return None
        identity = self.identity(account_id)
        if identity.get("disabled") or not verify_password(password, identity.get("password")):
            return None
        return self.public_account(account_id)

    def list_accounts(self) -> list[dict[str, Any]]:
        records = []
        for item in self._index()["accounts"].values():
            if isinstance(item, dict) and self.account_exists(str(item.get("id", ""))):
                records.append(self.public_account(str(item["id"])))
        return sorted(records, key=lambda item: item["username"].casefold())

    def public_account(self, account_id: str) -> dict[str, Any]:
        identity = self.identity(account_id)
        profile = self.profile(account_id)
        return {
            "id": identity["id"],
            "username": identity["username"],
            "nickname": profile["nickname"],
            "avatar_url": profile.get("avatar_url"),
            "role": identity["role"],
            "disabled": bool(identity.get("disabled")),
            "created_at": identity["created_at"],
        }

    def update_account(
        self,
        account_id: str,
        *,
        disabled: bool | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            identity = self.identity(account_id)
            if role is not None:
                if role not in {"admin", "user"}:
                    raise ValidationError("invalid_role", "账号角色无效。")
                if identity["role"] == "admin" and role != "admin" and self.enabled_admin_count() <= 1:
                    raise ValidationError("last_admin", "不能移除最后一个可用管理员。")
                identity["role"] = role
            if disabled is not None:
                if identity["role"] == "admin" and disabled and self.enabled_admin_count() <= 1:
                    raise ValidationError("last_admin", "不能停用最后一个可用管理员。")
                identity["disabled"] = bool(disabled)
                if disabled:
                    _atomic_write_json(self.account_dir(account_id) / "sessions.json", {"sessions": []})
            identity["updated_at"] = utc_now()
            _atomic_write_json(self.account_dir(account_id) / "identity.json", identity)
            return self.public_account(account_id)

    def enabled_admin_count(self) -> int:
        return sum(
            1
            for account in self.list_accounts()
            if account["role"] == "admin" and not account["disabled"]
        )

    def reset_password(self, account_id: str, password: Any) -> None:
        password = validate_password(password)
        with self._lock:
            identity = self.identity(account_id)
            identity["password"] = hash_password(password)
            identity["updated_at"] = utc_now()
            _atomic_write_json(self.account_dir(account_id) / "identity.json", identity)
            _atomic_write_json(self.account_dir(account_id) / "sessions.json", {"sessions": []})

    def profile(self, account_id: str) -> dict[str, Any]:
        value = _read_json(self.account_dir(account_id) / "profile.json", {})
        if not isinstance(value, dict):
            raise RuntimeError("profile_invalid")
        result = dict(value)
        avatar = result.get("avatar")
        result["avatar_url"] = f"/api/v1/users/{account_id}/avatar" if avatar else None
        result.pop("avatar", None)
        return result

    def update_profile(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            directory = self.account_dir(account_id)
            stored = _read_json(directory / "profile.json", {})
            if "nickname" in payload:
                nickname = str(payload.get("nickname") or "").strip()
                if not nickname or len(nickname) > 60:
                    raise ValidationError("invalid_nickname", "昵称须为 1–60 个字符。")
                stored["nickname"] = nickname
            if "avatar_data_url" in payload:
                value = payload.get("avatar_data_url")
                if value is None or value == "":
                    old = stored.pop("avatar", None)
                    if old:
                        try:
                            (directory / str(old)).unlink()
                        except FileNotFoundError:
                            pass
                else:
                    _mime, extension, content = decode_image_data_url(value, max_bytes=AVATAR_MAX_BYTES)
                    relative = f"avatars/current.{extension}"
                    target = directory / relative
                    target.write_bytes(content)
                    os.chmod(target, 0o600)
                    old = stored.get("avatar")
                    if old and old != relative:
                        try:
                            (directory / str(old)).unlink()
                        except FileNotFoundError:
                            pass
                    stored["avatar"] = relative
            stored["updated_at"] = utc_now()
            _atomic_write_json(directory / "profile.json", stored)
            return self.profile(account_id)

    def avatar(self, account_id: str) -> tuple[Path, str] | None:
        stored = _read_json(self.account_dir(account_id) / "profile.json", {})
        relative = stored.get("avatar") if isinstance(stored, dict) else None
        if not relative:
            return None
        path = self.account_dir(account_id) / str(relative)
        if not path.is_file():
            return None
        suffix = path.suffix.lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix)
        return (path, mime) if mime else None

    def settings(self, account_id: str) -> dict[str, Any]:
        value = _read_json(self.account_dir(account_id) / "settings.json", {})
        return value if isinstance(value, dict) else {}

    def update_settings(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"theme", "locale", "proxy"}
        if set(payload) - allowed:
            raise ValidationError("unknown_setting", "设置中包含不支持的字段。")
        with self._lock:
            value = self.settings(account_id)
            if "theme" in payload:
                if payload["theme"] not in {"system", "light", "dark"}:
                    raise ValidationError("invalid_theme", "主题设置无效。")
                value["theme"] = payload["theme"]
            if "locale" in payload:
                locale = str(payload["locale"])
                if locale not in {"zh-CN", "en-US"}:
                    raise ValidationError("invalid_locale", "语言设置无效。")
                value["locale"] = locale
            if "proxy" in payload:
                proxy = payload["proxy"]
                if not isinstance(proxy, dict):
                    raise ValidationError("invalid_proxy_settings", "代理偏好必须是对象。")
                preferred_mode = proxy.get("preferred_mode", value.get("proxy", {}).get("preferred_mode", "rule"))
                selection = str(proxy.get("preferred_selection", value.get("proxy", {}).get("preferred_selection", "AUTO")))
                if preferred_mode not in {"rule", "global", "direct"} or not selection or len(selection) > 160:
                    raise ValidationError("invalid_proxy_settings", "代理偏好无效。")
                value["proxy"] = {"preferred_mode": preferred_mode, "preferred_selection": selection}
            value["updated_at"] = utc_now()
            _atomic_write_json(self.account_dir(account_id) / "settings.json", value)
            return value

    def set_remark(self, owner_id: str, target_id: str, remark: Any) -> str:
        if owner_id == target_id or not self.account_exists(target_id):
            raise ValidationError("invalid_remark_target", "备注目标无效。")
        value = str(remark or "").strip()
        if len(value) > 120:
            raise ValidationError("remark_too_long", "备注不得超过 120 个字符。")
        with self._lock:
            path = self.account_dir(owner_id) / "social.json"
            social = _read_json(path, {"remarks": {}})
            remarks = social.setdefault("remarks", {})
            if value:
                remarks[target_id] = value
            else:
                remarks.pop(target_id, None)
            social["updated_at"] = utc_now()
            _atomic_write_json(path, social)
        return value

    def remarks(self, owner_id: str) -> dict[str, str]:
        social = _read_json(self.account_dir(owner_id) / "social.json", {"remarks": {}})
        remarks = social.get("remarks", {}) if isinstance(social, dict) else {}
        return {str(key): str(value) for key, value in remarks.items()} if isinstance(remarks, dict) else {}

    def create_session(self, account_id: str) -> dict[str, str]:
        with self._lock:
            identity = self.identity(account_id)
            if identity.get("disabled"):
                raise ValidationError("account_disabled", "账号已停用。")
            secret = new_token()
            csrf = new_token(24)
            expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
            path = self.account_dir(account_id) / "sessions.json"
            value = _read_json(path, {"sessions": []})
            now = datetime.now(timezone.utc)
            sessions = [
                item
                for item in value.get("sessions", [])
                if isinstance(item, dict) and _parse_time(str(item.get("expires_at", "1970-01-01T00:00:00Z"))) > now
            ]
            sessions.append(
                {
                    "digest": token_digest(secret),
                    "csrf_digest": token_digest(csrf),
                    "created_at": utc_now(),
                    "expires_at": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
                }
            )
            _atomic_write_json(path, {"sessions": sessions[-20:]})
            return {"token": f"{account_id}.{secret}", "csrf_token": csrf, "expires_at": sessions[-1]["expires_at"]}

    def verify_session(self, token: Any, csrf: Any = None) -> dict[str, Any] | None:
        if not isinstance(token, str) or "." not in token:
            return None
        account_id, secret = token.split(".", 1)
        if not self.account_exists(account_id):
            return None
        identity = self.identity(account_id)
        if identity.get("disabled"):
            return None
        digest = token_digest(secret)
        csrf_digest = token_digest(str(csrf)) if csrf is not None else None
        now = datetime.now(timezone.utc)
        sessions = _read_json(self.account_dir(account_id) / "sessions.json", {"sessions": []}).get("sessions", [])
        for item in sessions:
            try:
                if _parse_time(str(item["expires_at"])) <= now:
                    continue
                if secrets.compare_digest(str(item["digest"]), digest):
                    if csrf_digest is not None and not secrets.compare_digest(str(item["csrf_digest"]), csrf_digest):
                        return None
                    return self.public_account(account_id)
            except (KeyError, TypeError, ValueError):
                continue
        return None

    def revoke_session(self, token: Any) -> None:
        if not isinstance(token, str) or "." not in token:
            return
        account_id, secret = token.split(".", 1)
        if not self.account_exists(account_id):
            return
        digest = token_digest(secret)
        with self._lock:
            path = self.account_dir(account_id) / "sessions.json"
            value = _read_json(path, {"sessions": []})
            value["sessions"] = [item for item in value.get("sessions", []) if item.get("digest") != digest]
            _atomic_write_json(path, value)

    def create_device(self, account_id: str, name: Any, scope: str) -> dict[str, str]:
        label = str(name or "").strip()
        if not label or len(label) > 80 or scope not in {"planner_sync"}:
            raise ValidationError("invalid_device", "设备名称或权限范围无效。")
        with self._lock:
            path = self.account_dir(account_id) / "devices.json"
            value = _read_json(path, {"devices": []})
            enabled = [item for item in value.get("devices", []) if isinstance(item, dict) and not item.get("revoked_at")]
            if len(enabled) >= DEVICE_TOKEN_LIMIT:
                raise ValidationError("device_limit", "设备令牌数量已达上限。")
            device_id = uuid.uuid4().hex
            secret = new_token()
            record = {
                "id": device_id,
                "name": label,
                "scope": scope,
                "digest": token_digest(secret),
                "created_at": utc_now(),
                "last_used_at": None,
                "revoked_at": None,
            }
            value["devices"] = value.get("devices", []) + [record]
            _atomic_write_json(path, value)
            return {"id": device_id, "name": label, "scope": scope, "token": f"{account_id}.{device_id}.{secret}"}

    def list_devices(self, account_id: str) -> list[dict[str, Any]]:
        value = _read_json(self.account_dir(account_id) / "devices.json", {"devices": []})
        result = []
        for item in value.get("devices", []):
            if not isinstance(item, dict):
                continue
            result.append({key: item.get(key) for key in ("id", "name", "scope", "created_at", "last_used_at", "revoked_at")})
        return result

    def revoke_device(self, account_id: str, device_id: str) -> None:
        with self._lock:
            path = self.account_dir(account_id) / "devices.json"
            value = _read_json(path, {"devices": []})
            for item in value.get("devices", []):
                if isinstance(item, dict) and item.get("id") == device_id and not item.get("revoked_at"):
                    item["revoked_at"] = utc_now()
                    _atomic_write_json(path, value)
                    return
        raise ValidationError("device_not_found", "设备令牌不存在或已撤销。")

    def verify_device(self, token: Any, scope: str) -> dict[str, str] | None:
        if not isinstance(token, str):
            return None
        parts = token.split(".", 2)
        if len(parts) != 3:
            return None
        account_id, device_id, secret = parts
        if not self.account_exists(account_id):
            return None
        digest = token_digest(secret)
        path = self.account_dir(account_id) / "devices.json"
        with self._lock:
            value = _read_json(path, {"devices": []})
            for item in value.get("devices", []):
                if (
                    item.get("id") == device_id
                    and item.get("scope") == scope
                    and not item.get("revoked_at")
                    and secrets.compare_digest(str(item.get("digest", "")), digest)
                ):
                    item["last_used_at"] = utc_now()
                    _atomic_write_json(path, value)
                    return {"account_id": account_id, "device_id": device_id, "scope": scope}
        return None

    def planner(self, account_id: str) -> dict[str, Any]:
        value = _read_json(self.account_dir(account_id) / "planner.json", _default_planner())
        return value if isinstance(value, dict) else _default_planner()

    def write_planner(self, account_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > PLANNER_MAX_BYTES:
            raise ValidationError("planner_too_large", "规划快照超过 12 MiB 限制。")
        with self._lock:
            current = self.planner(account_id)
            incoming_revision = int(snapshot.get("revision", 0))
            if incoming_revision <= int(current.get("revision", 0)):
                raise ValidationError("stale_planner_revision", "规划快照 revision 必须递增。")
            value = dict(snapshot)
            value["received_at"] = utc_now()
            _atomic_write_json(self.account_dir(account_id) / "planner.json", value)
            return value

    def blog_dir(self, account_id: str) -> Path:
        return self.account_dir(account_id) / "blog"

    def blog_manifest(self, account_id: str) -> dict[str, Any]:
        value = _read_json(self.blog_dir(account_id) / "manifest.json", {})
        return value if isinstance(value, dict) else {}

    def write_blog_manifest(self, account_id: str, value: dict[str, Any]) -> None:
        _atomic_write_json(self.blog_dir(account_id) / "manifest.json", value)

    def directory_size(self, path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


__all__ = ["AccountStore", "ValidationError", "_atomic_write_json", "_read_json"]
