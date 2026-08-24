from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from tools.workspace_runtime import (
    WorkspaceRuntime,
    WorkspaceRuntimeError,
    format_time,
    utc_now,
)


class WorkspaceRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "agent-1"
        self.root.mkdir()
        self.port = self.free_port()
        self.config_path = self.root / "config/workspace-runtime.json"
        self.config_path.parent.mkdir()
        self.write_config()
        (self.root / ".gitignore").write_text(".runtime/\n", encoding="utf-8")
        subprocess.run(
            ["git", "init", "-b", "agent-1", str(self.root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Runtime Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "runtime@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "add", ".gitignore", "config/workspace-runtime.json"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", "test baseline"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.runtime = WorkspaceRuntime(self.root, self.config_path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def free_port() -> int:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        return port

    def write_config(self, *, duplicate: bool = False) -> None:
        second_port = self.port if duplicate else self.free_port()
        config = {
            "schema_version": 1,
            "shared_ports": {
                "shared": {
                    "bind": "127.0.0.1",
                    "owner": "main-deployment",
                    "port": second_port,
                }
            },
            "workspaces": {
                "agent-1": {
                    "bind": "127.0.0.1",
                    "branch": "agent-1",
                    "compose_project": "agent1",
                    "port_range": [self.port, self.port],
                    "ports": {"app": self.port},
                    "runtime_dir": ".runtime",
                },
                "agent-2": {
                    "bind": "127.0.0.1",
                    "branch": "agent-2",
                    "compose_project": "agent2",
                    "port_range": [second_port + 1, second_port + 1],
                    "ports": {"app": second_port + 1},
                    "runtime_dir": ".runtime",
                },
            },
        }
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def claim(self, session: str = "session-one") -> dict:
        return self.runtime.claim(session=session, task="runtime isolation tests")

    def test_claim_is_atomic_and_blocks_another_session(self) -> None:
        lease = self.claim()
        self.assertEqual(lease["workspace"], "agent-1")
        self.assertEqual(lease["session"], "session-one")
        with self.assertRaisesRegex(WorkspaceRuntimeError, "leased by session"):
            self.claim("session-two")

    def test_same_session_claim_is_idempotent(self) -> None:
        first = self.claim()
        second = self.claim()
        self.assertEqual(first["started_at"], second["started_at"])
        self.assertGreaterEqual(second["expires_at"], first["expires_at"])

    def test_claim_rejects_dirty_unleased_worktree(self) -> None:
        (self.root / "unowned.txt").write_text("unowned", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceRuntimeError, "not clean"):
            self.claim()

    def test_release_requires_matching_session_and_clean_tree(self) -> None:
        self.claim()
        with self.assertRaisesRegex(WorkspaceRuntimeError, "another session"):
            self.runtime.release(session="session-two")
        (self.root / "work.txt").write_text("in progress", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceRuntimeError, "dirty"):
            self.runtime.release(session="session-one")
        (self.root / "work.txt").unlink()
        self.runtime.release(session="session-one")
        self.assertIsNone(self.runtime.status()["lease"])

    def test_expired_lease_requires_clean_inspection(self) -> None:
        self.claim()
        lease = json.loads(self.runtime.lease_path.read_text(encoding="utf-8"))
        lease["expires_at"] = format_time(utc_now() - timedelta(minutes=1))
        self.runtime.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        (self.root / "unfinished.txt").write_text("unfinished", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceRuntimeError, "dirty worktree"):
            self.runtime.clear_expired()
        (self.root / "unfinished.txt").unlink()
        self.runtime.clear_expired()
        self.assertIsNone(self.runtime.status()["lease"])

    def test_assigned_port_must_be_free_when_claiming(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", self.port))
        listener.listen()
        try:
            with self.assertRaisesRegex(WorkspaceRuntimeError, "already in use"):
                self.claim()
        finally:
            listener.close()

    def test_environment_is_namespaced_to_workspace(self) -> None:
        self.claim()
        environment = self.runtime.environment(session="session-one", purpose="app")
        self.assertEqual(environment["APP_INSTANCE"], "agent-1")
        self.assertEqual(environment["APP_HOST"], "127.0.0.1")
        self.assertEqual(environment["APP_PORT"], str(self.port))
        self.assertEqual(environment["COMPOSE_PROJECT_NAME"], "agent1")
        self.assertTrue(environment["APP_DATA_DIR"].startswith(str(self.root)))

    def test_duplicate_port_assignments_are_rejected(self) -> None:
        self.write_config(duplicate=True)
        with self.assertRaisesRegex(WorkspaceRuntimeError, "assigned to both"):
            WorkspaceRuntime(self.root, self.config_path)

    def test_wrong_branch_is_rejected(self) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), "switch", "-c", "wrong-branch"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with self.assertRaisesRegex(WorkspaceRuntimeError, "must be on branch"):
            self.runtime.claim(session="session-one", task="wrong branch")


if __name__ == "__main__":
    unittest.main()
