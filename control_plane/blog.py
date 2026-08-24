"""Structured blogs and reviewed, script-free custom pages."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .security import ValidationError, decode_image_data_url, utc_now
from .shared import SharedStore
from .storage import AccountStore, _atomic_write_json


BLOG_QUOTA_BYTES = 32 * 1024 * 1024
CUSTOM_HTML_MAX_BYTES = 256 * 1024
BLOG_IMAGE_MAX_BYTES = 4 * 1024 * 1024
SAFE_TAGS = {
    "html", "head", "title", "style", "body", "main", "header", "footer", "nav", "section", "article",
    "aside", "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "dl", "dt",
    "dd", "blockquote", "pre", "code", "strong", "em", "small", "figure", "figcaption", "img", "a", "hr", "br",
    "table", "thead", "tbody", "tr", "th", "td", "colgroup", "col",
}
SAFE_ATTRS = {"class", "id", "title", "lang", "dir", "role", "alt", "width", "height", "colspan", "rowspan"}
UNSAFE_CSS_RE = re.compile(r"(?:url\s*\(|@import|expression\s*\(|javascript\s*:|behavior\s*:)", re.I)


class SafePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in SAFE_TAGS:
            raise ValidationError("unsafe_blog_html", f"自定义博客不允许使用 <{tag}> 标签。")
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = str(raw_value or "")
            if name.startswith("on"):
                raise ValidationError("unsafe_blog_html", "自定义博客不允许事件处理属性。")
            if name == "style":
                if UNSAFE_CSS_RE.search(value):
                    raise ValidationError("unsafe_blog_css", "自定义样式包含外部资源或可执行表达式。")
                continue
            if name.startswith("aria-") or name.startswith("data-") or name in SAFE_ATTRS:
                continue
            if tag == "a" and name == "href" and (value.startswith("#") or value == ""):
                continue
            if tag == "img" and name == "src" and value.startswith("data:image/"):
                decode_image_data_url(value, max_bytes=BLOG_IMAGE_MAX_BYTES)
                continue
            raise ValidationError("unsafe_blog_html", f"自定义博客属性 {name} 不在允许列表中。")
        if tag not in {"img", "hr", "br", "col"}:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in {"img", "hr", "br", "col"}:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1] == "style" and UNSAFE_CSS_RE.search(data):
            raise ValidationError("unsafe_blog_css", "自定义样式包含外部资源或可执行表达式。")

    def handle_entityref(self, name: str) -> None:
        return

    def handle_charref(self, name: str) -> None:
        return


def validate_custom_html(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("invalid_blog_html", "自定义博客页面必须是 HTML 字符串。")
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > CUSTOM_HTML_MAX_BYTES:
        raise ValidationError("blog_html_too_large", "自定义博客页面不得超过 256 KiB。")
    if "<!doctype html" not in value[:200].lower():
        raise ValidationError("invalid_blog_html", "自定义博客页面必须包含 HTML doctype。")
    parser = SafePageParser()
    try:
        parser.feed(value)
        parser.close()
    except ValidationError:
        raise
    except Exception as error:
        raise ValidationError("invalid_blog_html", "自定义博客 HTML 无法解析。") from error
    return value


class BlogManager:
    def __init__(self, accounts: AccountStore, shared: SharedStore) -> None:
        self.accounts = accounts
        self.shared = shared

    def publish_structured(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        blocks = payload.get("blocks")
        if not title or len(title) > 120 or len(summary) > 500 or not isinstance(blocks, list) or len(blocks) > 100:
            raise ValidationError("invalid_blog", "博客标题、摘要或内容块无效。")
        prepared: list[dict[str, Any]] = []
        pending_assets: list[tuple[Path, bytes]] = []
        blog_dir = self.accounts.blog_dir(account_id)
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") not in {"text", "image"}:
                raise ValidationError("invalid_blog_block", "博客内容块类型无效。")
            if block["type"] == "text":
                text = str(block.get("text") or "")
                if not text or len(text) > 10_000:
                    raise ValidationError("invalid_blog_block", "文本块须为 1–10000 个字符。")
                prepared.append({"type": "text", "text": text})
            else:
                alt = str(block.get("alt") or "").strip()[:200]
                _mime, extension, content = decode_image_data_url(block.get("data_url"), max_bytes=BLOG_IMAGE_MAX_BYTES)
                name = f"{uuid.uuid4().hex}.{extension}"
                pending_assets.append((blog_dir / "assets" / name, content))
                prepared.append({"type": "image", "alt": alt, "src": f"/api/v1/blogs/{account_id}/assets/{name}"})
        projected = self.accounts.directory_size(blog_dir) + sum(len(content) for _path, content in pending_assets)
        if projected > BLOG_QUOTA_BYTES:
            raise ValidationError("blog_quota_exceeded", "博客资源超过 32 MiB 配额。")
        for path, content in pending_assets:
            path.write_bytes(content)
            os.chmod(path, 0o600)
        manifest = {
            "mode": "structured",
            "published": True,
            "title": title,
            "summary": summary,
            "blocks": prepared,
            "custom_revision": None,
            "updated_at": utc_now(),
        }
        self.accounts.write_blog_manifest(account_id, manifest)
        return manifest

    def submit_custom(self, account_id: str, html: Any) -> dict[str, Any]:
        content = validate_custom_html(html)
        blog_dir = self.accounts.blog_dir(account_id)
        if self.accounts.directory_size(blog_dir) + len(content.encode("utf-8")) > BLOG_QUOTA_BYTES:
            raise ValidationError("blog_quota_exceeded", "博客资源超过 32 MiB 配额。")
        revision_id = uuid.uuid4().hex
        path = blog_dir / "drafts" / f"{revision_id}.html"
        path.write_text(content, encoding="utf-8")
        os.chmod(path, 0o600)
        return self.shared.submit_blog_review(account_id, revision_id)

    def review(self, reviewer_id: str, account_id: str, revision_id: str, decision: str, note: str) -> dict[str, Any]:
        if len(note) > 500:
            raise ValidationError("review_note_too_long", "审核备注不得超过 500 个字符。")
        draft = self.accounts.blog_dir(account_id) / "drafts" / f"{revision_id}.html"
        if not draft.is_file():
            raise ValidationError("review_not_found", "待审核博客文件不存在。")
        record = self.shared.review_blog(reviewer_id, account_id, revision_id, decision, note)
        if decision == "approved":
            published = self.accounts.blog_dir(account_id) / "published" / f"{revision_id}.html"
            shutil.copyfile(draft, published)
            os.chmod(published, 0o600)
            manifest = self.accounts.blog_manifest(account_id)
            manifest.update({"mode": "custom", "published": True, "custom_revision": revision_id, "updated_at": utc_now()})
            self.accounts.write_blog_manifest(account_id, manifest)
        return record

    def public_blog(self, account_id: str) -> dict[str, Any]:
        manifest = self.accounts.blog_manifest(account_id)
        if not manifest.get("published"):
            raise ValidationError("blog_not_found", "该账号尚未发布博客。")
        return manifest

    def asset(self, account_id: str, name: str) -> Path | None:
        if not re.fullmatch(r"[0-9a-f]{32}\.(?:png|jpg|webp)", name):
            return None
        path = self.accounts.blog_dir(account_id) / "assets" / name
        return path if path.is_file() else None

    def custom_page(self, account_id: str, revision_id: str) -> Path | None:
        manifest = self.accounts.blog_manifest(account_id)
        if manifest.get("mode") != "custom" or manifest.get("custom_revision") != revision_id:
            return None
        path = self.accounts.blog_dir(account_id) / "published" / f"{revision_id}.html"
        return path if path.is_file() else None


__all__ = ["BlogManager", "validate_custom_html"]
