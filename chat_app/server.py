#!/usr/bin/env python3
"""Serve a clock page and a small in-memory chat API."""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


APP_DIR = Path(__file__).resolve().parent
INDEX_FILE = APP_DIR / "static" / "index.html"
MAX_BODY_BYTES = 16_384
MAX_AUTHOR_LENGTH = 40
MAX_MESSAGE_LENGTH = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ChatState:
    """Thread-safe bounded in-memory message store."""

    def __init__(self, capacity: int = 200) -> None:
        self._condition = threading.Condition()
        self._messages: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._next_id = 1

    def publish(self, author: str, text: str) -> dict[str, Any]:
        with self._condition:
            message = {
                "id": self._next_id,
                "author": author,
                "text": text,
                "created_at": utc_now(),
            }
            self._next_id += 1
            self._messages.append(message)
            self._condition.notify_all()
            return message

    def messages_after(self, after: int) -> list[dict[str, Any]]:
        with self._condition:
            return [message for message in self._messages if message["id"] > after]

    def wait_for_messages(self, after: int, timeout: float) -> list[dict[str, Any]]:
        with self._condition:
            messages = [message for message in self._messages if message["id"] > after]
            if messages:
                return messages
            self._condition.wait(timeout)
            return [message for message in self._messages if message["id"] > after]

    @property
    def count(self) -> int:
        with self._condition:
            return len(self._messages)


class ChatServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], state: ChatState) -> None:
        super().__init__(server_address, ChatRequestHandler)
        self.chat_state = state


class ChatRequestHandler(BaseHTTPRequestHandler):
    server: ChatServer
    server_version = "ConnectivityChat/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            self._serve_index()
            return
        if parsed.path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "server_time": utc_now(),
                    "messages_in_memory": self.server.chat_state.count,
                },
            )
            return
        if parsed.path == "/api/messages":
            after = self._parse_after(parsed.query)
            self._send_json(
                HTTPStatus.OK,
                {"messages": self.server.chat_state.messages_after(after)},
            )
            return
        if parsed.path == "/api/events":
            self._serve_events(self._parse_after(parsed.query))
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path != "/api/messages":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        payload = self._read_json()
        if payload is None:
            return

        author = payload.get("author", "")
        text = payload.get("text", "")
        if not isinstance(author, str) or not isinstance(text, str):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "author_and_text_must_be_strings"},
            )
            return

        author = author.strip()
        text = text.strip()
        if not author or not text:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "author_and_text_are_required"},
            )
            return
        if len(author) > MAX_AUTHOR_LENGTH or len(text) > MAX_MESSAGE_LENGTH:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "message_too_long",
                    "limits": {
                        "author": MAX_AUTHOR_LENGTH,
                        "text": MAX_MESSAGE_LENGTH,
                    },
                },
            )
            return

        message = self.server.chat_state.publish(author=author, text=text)
        self._send_json(HTTPStatus.CREATED, {"message": message})

    def _serve_index(self) -> None:
        try:
            content = INDEX_FILE.read_bytes()
        except OSError:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "index_unavailable"},
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _serve_events(self, after: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            messages = self.server.chat_state.wait_for_messages(after, timeout=25)
            if not messages:
                self.wfile.write(b": heartbeat\n\n")
            for message in messages:
                payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
                event = "event: message\ndata: " + payload + "\n\n"
                self.wfile.write(event.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _read_json(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_content_length"},
            )
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

    @staticmethod
    def _parse_after(query: str) -> int:
        value = parse_qs(query).get("after", ["0"])[0]
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def create_server(host: str, port: int, state: ChatState | None = None) -> ChatServer:
    return ChatServer((host, port), state or ChatState())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("CHAT_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CHAT_PORT", "8765")),
    )
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    stop_event = threading.Event()

    def request_shutdown(_signum: int, _frame: object) -> None:
        if not stop_event.is_set():
            stop_event.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    host, port = server.server_address[:2]
    print("Connectivity chat listening on http://%s:%s" % (host, port), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
