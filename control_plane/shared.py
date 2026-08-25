"""Atomic shared state for relationships, bounded conversations, reviews, and jobs."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .security import ValidationError, new_token, token_digest, utc_now


def _pair(first: str, second: str) -> tuple[str, str, str]:
    low, high = sorted((first, second))
    return f"{low}:{high}", low, high


def _future(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")


class SharedStore:
    def __init__(
        self,
        path: str | Path,
        *,
        conversation_max_messages: int = 10_000,
        conversation_max_bytes: int = 16 * 1024 * 1024,
        account_message_max_bytes: int = 64 * 1024 * 1024,
        global_message_max_bytes: int = 512 * 1024 * 1024,
        message_retention_days: int = 365,
        worker_lease_seconds: int = 300,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.conversation_max_messages = conversation_max_messages
        self.conversation_max_bytes = conversation_max_bytes
        self.account_message_max_bytes = account_message_max_bytes
        self.global_message_max_bytes = global_message_max_bytes
        self.message_retention_days = message_retention_days
        self.worker_lease_seconds = worker_lease_seconds
        self._lock = threading.RLock()
        self._initialize()
        self.prune_all_messages()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA auto_vacuum = INCREMENTAL")
        connection.execute("PRAGMA journal_size_limit = 16777216")
        connection.execute("PRAGMA wal_autocheckpoint = 1000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS connections (
                    pair_key TEXT PRIMARY KEY,
                    low_id TEXT NOT NULL,
                    high_id TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','connected','rejected')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS connections_low ON connections(low_id, status);
                CREATE INDEX IF NOT EXISTS connections_high ON connections(high_id, status);

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair_key TEXT NOT NULL REFERENCES connections(pair_key) ON DELETE CASCADE,
                    sender_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_pair_id ON messages(pair_key, id);
                CREATE INDEX IF NOT EXISTS messages_created ON messages(created_at);

                CREATE TABLE IF NOT EXISTS worker_tokens (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT
                );

                CREATE TABLE IF NOT EXISTS inference_tasks (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
                    progress REAL NOT NULL DEFAULT 0,
                    phase_label TEXT NOT NULL,
                    worker_id TEXT,
                    lease_digest TEXT,
                    lease_expires_at TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS tasks_owner_created ON inference_tasks(owner_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS tasks_queue ON inference_tasks(status, priority DESC, created_at);

                CREATE TABLE IF NOT EXISTS blog_reviews (
                    account_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
                    reviewer_id TEXT,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    PRIMARY KEY(account_id, revision_id)
                );
                CREATE INDEX IF NOT EXISTS blog_reviews_status ON blog_reviews(status, created_at);
                """
            )

    def request_connection(self, requester_id: str, target_id: str) -> dict[str, Any]:
        if requester_id == target_id:
            raise ValidationError("invalid_connection", "不能向自己发送连接申请。")
        pair_key, low, high = _pair(requester_id, target_id)
        now = utc_now()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM connections WHERE pair_key = ?", (pair_key,)).fetchone()
            if row and row["status"] == "connected":
                raise ValidationError("already_connected", "双方已经建立连接。")
            if row and row["status"] == "pending":
                if row["requester_id"] == requester_id:
                    return self._connection_dict(row, requester_id)
                raise ValidationError("request_crossed", "对方已向你发送申请，请直接处理。")
            db.execute(
                """INSERT INTO connections(pair_key, low_id, high_id, requester_id, status, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(pair_key) DO UPDATE SET requester_id=excluded.requester_id, status='pending', updated_at=excluded.updated_at""",
                (pair_key, low, high, requester_id, "pending", now, now),
            )
            row = db.execute("SELECT * FROM connections WHERE pair_key = ?", (pair_key,)).fetchone()
            return self._connection_dict(row, requester_id)

    @staticmethod
    def _connection_dict(row: sqlite3.Row, viewer_id: str) -> dict[str, Any]:
        other_id = row["high_id"] if row["low_id"] == viewer_id else row["low_id"]
        return {
            "account_id": other_id,
            "status": row["status"],
            "direction": "outgoing" if row["requester_id"] == viewer_id else "incoming",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_connections(self, account_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM connections WHERE low_id = ? OR high_id = ? ORDER BY updated_at DESC",
                (account_id, account_id),
            ).fetchall()
        return [self._connection_dict(row, account_id) for row in rows]

    def act_on_connection(self, actor_id: str, target_id: str, action: str) -> dict[str, Any]:
        if action not in {"accept", "reject", "cancel"}:
            raise ValidationError("invalid_connection_action", "连接操作无效。")
        pair_key, _low, _high = _pair(actor_id, target_id)
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM connections WHERE pair_key = ?", (pair_key,)).fetchone()
            if not row or row["status"] != "pending":
                raise ValidationError("request_not_found", "待处理申请不存在。")
            if action in {"accept", "reject"} and row["requester_id"] == actor_id:
                raise ValidationError("not_request_recipient", "只有接收方可以接受或拒绝申请。")
            if action == "cancel" and row["requester_id"] != actor_id:
                raise ValidationError("not_request_sender", "只有发送方可以撤回申请。")
            status = "connected" if action == "accept" else "rejected"
            db.execute(
                "UPDATE connections SET status = ?, updated_at = ? WHERE pair_key = ?",
                (status, utc_now(), pair_key),
            )
            updated = db.execute("SELECT * FROM connections WHERE pair_key = ?", (pair_key,)).fetchone()
            return self._connection_dict(updated, actor_id)

    def connected(self, first: str, second: str) -> bool:
        pair_key, _low, _high = _pair(first, second)
        with self._connect() as db:
            row = db.execute("SELECT status FROM connections WHERE pair_key = ?", (pair_key,)).fetchone()
        return bool(row and row["status"] == "connected")

    def send_message(self, sender_id: str, target_id: str, text: Any) -> dict[str, Any]:
        message = str(text or "").strip()
        if not message:
            raise ValidationError("message_required", "消息不能为空。")
        if len(message) > 4_000:
            raise ValidationError("message_too_long", "消息不得超过 4000 个字符。")
        pair_key, _low, _high = _pair(sender_id, target_id)
        if not self.connected(sender_id, target_id):
            raise ValidationError("not_connected", "建立连接后才能发送消息。")
        encoded_size = len(message.encode("utf-8"))
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "INSERT INTO messages(pair_key, sender_id, text, byte_size, created_at) VALUES(?,?,?,?,?)",
                (pair_key, sender_id, message, encoded_size, utc_now()),
            )
            message_id = int(cursor.lastrowid)
            self._prune_messages(db, pair_key, sender_id, target_id)
            row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise ValidationError("message_quota_exhausted", "消息配额已满且新消息无法保留。")
        return self._message_dict(row)

    @staticmethod
    def _message_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "sender_id": row["sender_id"], "text": row["text"], "created_at": row["created_at"]}

    def messages(self, viewer_id: str, target_id: str, *, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        if not self.connected(viewer_id, target_id):
            raise ValidationError("not_connected", "双方尚未建立连接。")
        pair_key, _low, _high = _pair(viewer_id, target_id)
        limit = max(1, min(200, int(limit)))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM messages WHERE pair_key = ? AND id > ? ORDER BY id LIMIT ?",
                (pair_key, max(0, int(after)), limit),
            ).fetchall()
        return [self._message_dict(row) for row in rows]

    def _delete_oldest_until(self, db: sqlite3.Connection, query: str, parameters: tuple[Any, ...], max_bytes: int, max_count: int | None = None) -> None:
        rows = db.execute(query, parameters).fetchall()
        total = sum(int(row["byte_size"]) for row in rows)
        count = len(rows)
        delete_ids: list[int] = []
        for row in rows:
            if total <= max_bytes and (max_count is None or count <= max_count):
                break
            delete_ids.append(int(row["id"]))
            total -= int(row["byte_size"])
            count -= 1
        if delete_ids:
            db.executemany("DELETE FROM messages WHERE id = ?", [(item,) for item in delete_ids])

    def _prune_messages(self, db: sqlite3.Connection, pair_key: str, first_id: str, second_id: str) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.message_retention_days)).isoformat(timespec="seconds").replace("+00:00", "Z")
        db.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
        self._delete_oldest_until(
            db,
            "SELECT id, byte_size FROM messages WHERE pair_key = ? ORDER BY id",
            (pair_key,),
            self.conversation_max_bytes,
            self.conversation_max_messages,
        )
        for account_id in {first_id, second_id}:
            self._delete_oldest_until(
                db,
                """SELECT m.id, m.byte_size FROM messages m JOIN connections c ON c.pair_key=m.pair_key
                   WHERE c.low_id=? OR c.high_id=? ORDER BY m.id""",
                (account_id, account_id),
                self.account_message_max_bytes,
            )
        self._delete_oldest_until(
            db,
            "SELECT id, byte_size FROM messages ORDER BY id",
            (),
            self.global_message_max_bytes,
        )
        db.execute("PRAGMA incremental_vacuum(64)")

    def message_usage(self) -> dict[str, int]:
        with self._connect() as db:
            row = db.execute("SELECT COUNT(*) AS count, COALESCE(SUM(byte_size),0) AS bytes FROM messages").fetchone()
        return {"messages": int(row["count"]), "bytes": int(row["bytes"]), "global_limit_bytes": self.global_message_max_bytes}

    def prune_all_messages(self) -> None:
        with self._lock, self._connect() as db:
            pairs = db.execute("SELECT pair_key, low_id, high_id FROM connections").fetchall()
            for row in pairs:
                self._prune_messages(db, row["pair_key"], row["low_id"], row["high_id"])

    def create_worker(self, name: Any) -> dict[str, str]:
        label = str(name or "").strip()
        if not label or len(label) > 80:
            raise ValidationError("invalid_worker_name", "监控端名称须为 1–80 个字符。")
        worker_id = uuid.uuid4().hex
        secret = new_token()
        with self._connect() as db:
            db.execute(
                "INSERT INTO worker_tokens(id,name,digest,created_at) VALUES(?,?,?,?)",
                (worker_id, label, token_digest(secret), utc_now()),
            )
        return {"id": worker_id, "name": label, "token": f"{worker_id}.{secret}"}

    def verify_worker(self, token: Any) -> dict[str, str] | None:
        if not isinstance(token, str) or "." not in token:
            return None
        worker_id, secret = token.split(".", 1)
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM worker_tokens WHERE id = ? AND enabled = 1", (worker_id,)).fetchone()
            if not row or not secrets.compare_digest(row["digest"], token_digest(secret)):
                return None
            db.execute("UPDATE worker_tokens SET last_seen_at = ? WHERE id = ?", (utc_now(), worker_id))
            return {"id": worker_id, "name": row["name"]}

    def create_task(self, owner_id: str, instruction: str, parameters: dict[str, Any], priority: int) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        now = utc_now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO inference_tasks(id,owner_id,instruction,parameters_json,priority,status,phase_label,created_at,updated_at)
                   VALUES(?,?,?,?,?,'queued','等待监控端领取',?,?)""",
                (task_id, owner_id, instruction, json.dumps(parameters, ensure_ascii=False, separators=(",", ":")), priority, now, now),
            )
            row = db.execute("SELECT * FROM inference_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task_dict(row)

    @staticmethod
    def _task_dict(row: sqlite3.Row, *, lease_token: str | None = None) -> dict[str, Any]:
        result = {
            "id": row["id"],
            "owner_id": row["owner_id"],
            "instruction": row["instruction"],
            "parameters": json.loads(row["parameters_json"]),
            "priority": row["priority"],
            "status": row["status"],
            "progress": row["progress"],
            "phase_label": row["phase_label"],
            "worker_id": row["worker_id"],
            "lease_expires_at": row["lease_expires_at"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }
        if lease_token:
            result["lease_token"] = lease_token
        return result

    def tasks_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM inference_tasks WHERE owner_id = ? ORDER BY created_at DESC LIMIT 200",
                (owner_id,),
            ).fetchall()
        return [self._task_dict(row) for row in rows]

    def task_for_owner(self, owner_id: str, task_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM inference_tasks WHERE id = ? AND owner_id = ?", (task_id, owner_id)).fetchone()
        return self._task_dict(row) if row else None

    def cancel_task(self, owner_id: str, task_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM inference_tasks WHERE id=? AND owner_id=?", (task_id, owner_id)).fetchone()
            if not row:
                raise ValidationError("task_not_found", "推理任务不存在。")
            if row["status"] not in {"queued", "running"}:
                raise ValidationError("task_not_cancellable", "当前任务状态不能取消。")
            now = utc_now()
            db.execute(
                "UPDATE inference_tasks SET status='cancelled', phase_label='已取消', updated_at=?, finished_at=?, lease_digest=NULL WHERE id=?",
                (now, now, task_id),
            )
            updated = db.execute("SELECT * FROM inference_tasks WHERE id=?", (task_id,)).fetchone()
            return self._task_dict(updated)

    def claim_task(self, worker_id: str) -> dict[str, Any] | None:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE inference_tasks SET status='queued', worker_id=NULL, lease_digest=NULL, lease_expires_at=NULL,
                   phase_label='租约过期，等待重新领取', updated_at=?
                   WHERE status='running' AND lease_expires_at < ?""",
                (now, now),
            )
            row = db.execute(
                "SELECT * FROM inference_tasks WHERE status='queued' ORDER BY priority DESC, created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            secret = new_token()
            lease_token = f"{row['id']}.{secret}"
            expires = _future(self.worker_lease_seconds)
            db.execute(
                """UPDATE inference_tasks SET status='running', worker_id=?, lease_digest=?, lease_expires_at=?,
                   phase_label='监控端已领取', progress=0, started_at=COALESCE(started_at,?), updated_at=? WHERE id=?""",
                (worker_id, token_digest(secret), expires, now, now, row["id"]),
            )
            updated = db.execute("SELECT * FROM inference_tasks WHERE id=?", (row["id"],)).fetchone()
            return self._task_dict(updated, lease_token=lease_token)

    def _leased_task(self, db: sqlite3.Connection, worker_id: str, task_id: str, lease_token: str) -> sqlite3.Row:
        if "." not in lease_token:
            raise ValidationError("invalid_lease", "任务租约无效。")
        token_task, secret = lease_token.split(".", 1)
        row = db.execute("SELECT * FROM inference_tasks WHERE id=?", (task_id,)).fetchone()
        if (
            not row
            or token_task != task_id
            or row["status"] != "running"
            or row["worker_id"] != worker_id
            or not row["lease_digest"]
            or not secrets.compare_digest(row["lease_digest"], token_digest(secret))
            or row["lease_expires_at"] < utc_now()
        ):
            raise ValidationError("invalid_lease", "任务租约无效或已过期。")
        return row

    def update_task_progress(self, worker_id: str, task_id: str, lease_token: str, progress: float, label: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            self._leased_task(db, worker_id, task_id, lease_token)
            expires = _future(self.worker_lease_seconds)
            db.execute(
                "UPDATE inference_tasks SET progress=?, phase_label=?, lease_expires_at=?, updated_at=? WHERE id=?",
                (progress, label, expires, utc_now(), task_id),
            )
            row = db.execute("SELECT * FROM inference_tasks WHERE id=?", (task_id,)).fetchone()
            return self._task_dict(row, lease_token=lease_token)

    def complete_task(
        self,
        worker_id: str,
        task_id: str,
        lease_token: str,
        *,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            self._leased_task(db, worker_id, task_id, lease_token)
            status = "failed" if error else "succeeded"
            now = utc_now()
            db.execute(
                """UPDATE inference_tasks SET status=?, progress=?, phase_label=?, result_json=?, error=?,
                   lease_digest=NULL, lease_expires_at=NULL, updated_at=?, finished_at=? WHERE id=?""",
                (
                    status,
                    1.0 if status == "succeeded" else 0.0,
                    "任务完成" if status == "succeeded" else "任务失败",
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")) if result is not None else None,
                    error,
                    now,
                    now,
                    task_id,
                ),
            )
            row = db.execute("SELECT * FROM inference_tasks WHERE id=?", (task_id,)).fetchone()
            return self._task_dict(row)

    def submit_blog_review(self, account_id: str, revision_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO blog_reviews(account_id,revision_id,status,created_at) VALUES(?,?,'pending',?)
                   ON CONFLICT(account_id,revision_id) DO UPDATE SET status='pending',reviewer_id=NULL,note='',reviewed_at=NULL""",
                (account_id, revision_id, now),
            )
            row = db.execute("SELECT * FROM blog_reviews WHERE account_id=? AND revision_id=?", (account_id, revision_id)).fetchone()
        return dict(row)

    def pending_blog_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM blog_reviews WHERE status='pending' ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def blog_reviews_for_account(self, account_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(100, int(limit)))
        with self._connect() as db:
            rows = db.execute(
                """SELECT account_id,revision_id,status,note,created_at,reviewed_at
                   FROM blog_reviews WHERE account_id=? ORDER BY created_at DESC LIMIT ?""",
                (account_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def review_blog(self, reviewer_id: str, account_id: str, revision_id: str, decision: str, note: str) -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ValidationError("invalid_review_decision", "审核结果无效。")
        with self._connect() as db:
            row = db.execute("SELECT * FROM blog_reviews WHERE account_id=? AND revision_id=?", (account_id, revision_id)).fetchone()
            if not row or row["status"] != "pending":
                raise ValidationError("review_not_found", "待审核博客版本不存在。")
            db.execute(
                "UPDATE blog_reviews SET status=?,reviewer_id=?,note=?,reviewed_at=? WHERE account_id=? AND revision_id=?",
                (decision, reviewer_id, note, utc_now(), account_id, revision_id),
            )
            updated = db.execute("SELECT * FROM blog_reviews WHERE account_id=? AND revision_id=?", (account_id, revision_id)).fetchone()
        return dict(updated)


__all__ = ["SharedStore"]
