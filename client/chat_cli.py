#!/usr/bin/env python3
"""Send messages from a local terminal to the connectivity test chat."""

from __future__ import annotations

import argparse
import json
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ChatClient:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return self._request_json("/api/health")

    def messages_after(self, after: int) -> list[dict[str, Any]]:
        query = urlencode({"after": after})
        return self._request_json("/api/messages?" + query)["messages"]

    def send(self, author: str, text: str) -> dict[str, Any]:
        return self._request_json(
            "/api/messages",
            method="POST",
            payload={"author": author, "text": text},
        )["message"]

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                detail = json.load(error).get("error", str(error))
            except (json.JSONDecodeError, AttributeError):
                detail = str(error)
            raise RuntimeError("HTTP %d: %s" % (error.code, detail)) from error
        except URLError as error:
            raise RuntimeError("连接失败: %s" % error.reason) from error


def print_message(message: dict[str, Any], print_lock: threading.Lock) -> None:
    with print_lock:
        print(
            "\n[%s] %s: %s"
            % (message["created_at"], message["author"], message["text"]),
            flush=True,
        )


def watch_messages(
    client: ChatClient,
    stop_event: threading.Event,
    print_lock: threading.Lock,
    initial_after: int,
) -> None:
    last_id = initial_after
    while not stop_event.wait(1):
        try:
            for message in client.messages_after(last_id):
                last_id = max(last_id, message["id"])
                print_message(message, print_lock)
        except RuntimeError as error:
            with print_lock:
                print("\n[连接提示] %s" % error, flush=True)
            stop_event.wait(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        required=True,
        help="Server base URL, for example http://203.0.113.10:8765",
    )
    parser.add_argument("--name", default="本地工具", help="Chat display name")
    parser.add_argument("--message", help="Send one message and exit")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout")
    args = parser.parse_args()
    client = ChatClient(args.url, timeout=args.timeout)

    try:
        health = client.health()
    except RuntimeError as error:
        parser.error(str(error))
    print(
        "已连接 %s（服务器时间 %s）"
        % (args.url.rstrip("/"), health["server_time"]),
        flush=True,
    )

    if args.message:
        message = client.send(args.name, args.message)
        print("已发送消息 #%d" % message["id"])
        return

    history = client.messages_after(0)
    print_lock = threading.Lock()
    for message in history:
        print_message(message, print_lock)
    last_id = history[-1]["id"] if history else 0

    stop_event = threading.Event()
    watcher = threading.Thread(
        target=watch_messages,
        args=(client, stop_event, print_lock, last_id),
        daemon=True,
    )
    watcher.start()

    print("输入消息并回车；输入 /quit 退出。")
    try:
        while True:
            text = input("> ").strip()
            if text == "/quit":
                break
            if not text:
                continue
            try:
                client.send(args.name, text)
            except RuntimeError as error:
                print("[发送失败] %s" % error)
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        stop_event.set()
        watcher.join(timeout=2)


if __name__ == "__main__":
    main()
