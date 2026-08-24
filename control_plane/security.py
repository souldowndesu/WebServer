"""Password, token, upload, and request validation helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any


USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
MAX_JSON_DEPTH = 8
MAX_JSON_ITEMS = 2_000
IMAGE_TYPES = {
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/webp": ("webp", b"RIFF"),
}


class ValidationError(ValueError):
    """A public, non-secret validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_username(value: Any) -> str:
    username = str(value or "").strip()
    if not USERNAME_RE.fullmatch(username):
        raise ValidationError(
            "invalid_username",
            "账号名须为 3–32 位 ASCII 字母、数字、点、下划线或连字符。",
        )
    return username


def validate_password(password: Any) -> str:
    if not isinstance(password, str):
        raise ValidationError("invalid_password", "密码必须是字符串。")
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise ValidationError(
            "invalid_password",
            f"密码长度须为 {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} 个字符。",
        )
    if password.isspace():
        raise ValidationError("invalid_password", "密码不能只包含空白字符。")
    return password


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> dict[str, Any]:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
    )
    return {
        "algorithm": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": _b64(salt),
        "digest": _b64(digest),
    }


def verify_password(password: Any, encoded: Any) -> bool:
    if not isinstance(password, str) or not isinstance(encoded, dict):
        return False
    try:
        if encoded.get("algorithm") != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(str(encoded["salt"])),
            n=int(encoded["n"]),
            r=int(encoded["r"]),
            p=int(encoded["p"]),
            maxmem=SCRYPT_MAXMEM,
        )
        return hmac.compare_digest(digest, _unb64(str(encoded["digest"])))
    except (KeyError, TypeError, ValueError, OSError):
        return False


# Equalize the expensive verification path for unknown usernames without using
# a real account's password material.
DUMMY_PASSWORD_HASH = hash_password("unreachable dummy password 9d2f6bce")


def new_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_json_shape(value: Any, *, max_depth: int = MAX_JSON_DEPTH) -> None:
    items = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal items
        if depth > max_depth:
            raise ValidationError("json_too_deep", "JSON 嵌套层级过深。")
        if isinstance(node, dict):
            items += len(node)
            for key, child in node.items():
                if not isinstance(key, str) or len(key) > 80:
                    raise ValidationError("invalid_json_key", "JSON 键无效或过长。")
                walk(child, depth + 1)
        elif isinstance(node, list):
            items += len(node)
            for child in node:
                walk(child, depth + 1)
        elif node is not None and not isinstance(node, (str, int, float, bool)):
            raise ValidationError("invalid_json_value", "JSON 包含不支持的值。")
        if items > MAX_JSON_ITEMS:
            raise ValidationError("json_too_large", "JSON 项目数量超过限制。")

    walk(value, 0)


def compact_json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def decode_image_data_url(value: Any, *, max_bytes: int) -> tuple[str, str, bytes]:
    if not isinstance(value, str) or not value.startswith("data:image/") or ";base64," not in value:
        raise ValidationError("invalid_image", "图像必须是受支持的 base64 data URL。")
    header, encoded = value.split(",", 1)
    mime = header[5:].split(";", 1)[0].lower()
    image_type = IMAGE_TYPES.get(mime)
    if image_type is None:
        raise ValidationError("invalid_image_type", "仅支持 PNG、JPEG 或 WebP 图像。")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise ValidationError("invalid_image", "图像 base64 数据无效。") from error
    if not content or len(content) > max_bytes:
        raise ValidationError("image_too_large", f"图像不得超过 {max_bytes // (1024 * 1024)} MiB。")
    extension, signature = image_type
    if not content.startswith(signature):
        raise ValidationError("invalid_image", "图像内容与声明类型不一致。")
    if mime == "image/webp" and (len(content) < 12 or content[8:12] != b"WEBP"):
        raise ValidationError("invalid_image", "WebP 文件头无效。")
    return mime, extension, content
