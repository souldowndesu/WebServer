#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


SESSION_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
COMPOSE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class WorkspaceRuntimeError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise WorkspaceRuntimeError("lease contains an invalid timestamp") from error
    if parsed.tzinfo is None:
        raise WorkspaceRuntimeError("lease timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


class WorkspaceRuntime:
    def __init__(self, root: Path, config_path: Path | None = None) -> None:
        self.root = root.resolve()
        self.config_path = (config_path or self.root / "config/workspace-runtime.json").resolve()
        self.config = self._load_config()
        self.workspace_id = self.root.name
        try:
            self.workspace = self.config["workspaces"][self.workspace_id]
        except KeyError as error:
            raise WorkspaceRuntimeError(
                "workspace %r is not registered in %s"
                % (self.workspace_id, self.config_path)
            ) from error

        runtime_relative = Path(self.workspace["runtime_dir"])
        self.runtime_dir = (self.root / runtime_relative).resolve()
        try:
            self.runtime_dir.relative_to(self.root)
        except ValueError as error:
            raise WorkspaceRuntimeError("runtime_dir must stay inside the workspace") from error
        self.lease_path = self.runtime_dir / "workspace-lease.json"
        self.lock_path = self.runtime_dir / "workspace-lease.lock"

    def _load_config(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise WorkspaceRuntimeError("runtime config is missing: %s" % self.config_path) from error
        except json.JSONDecodeError as error:
            raise WorkspaceRuntimeError("runtime config is not valid JSON") from error
        if payload.get("schema_version") != 1:
            raise WorkspaceRuntimeError("unsupported runtime config schema")
        shared = payload.get("shared_ports")
        workspaces = payload.get("workspaces")
        if not isinstance(shared, dict) or not isinstance(workspaces, dict):
            raise WorkspaceRuntimeError("runtime config requires shared_ports and workspaces maps")

        used_ports: dict[int, str] = {}
        for name, entry in shared.items():
            self._register_port(used_ports, entry.get("port"), "shared:%s" % name)
        for workspace_id, entry in workspaces.items():
            if not isinstance(entry, dict):
                raise WorkspaceRuntimeError("workspace %s config must be an object" % workspace_id)
            if entry.get("branch") != workspace_id:
                raise WorkspaceRuntimeError(
                    "workspace %s must use its matching branch" % workspace_id
                )
            if entry.get("bind") != "127.0.0.1":
                raise WorkspaceRuntimeError(
                    "development workspace %s must bind to 127.0.0.1" % workspace_id
                )
            compose_project = entry.get("compose_project", "")
            if not COMPOSE_PATTERN.fullmatch(compose_project):
                raise WorkspaceRuntimeError(
                    "workspace %s has an invalid compose_project" % workspace_id
                )
            port_range = entry.get("port_range")
            if (
                not isinstance(port_range, list)
                or len(port_range) != 2
                or not all(isinstance(value, int) for value in port_range)
                or port_range[0] > port_range[1]
            ):
                raise WorkspaceRuntimeError(
                    "workspace %s has an invalid port_range" % workspace_id
                )
            ports = entry.get("ports")
            if not isinstance(ports, dict) or not ports:
                raise WorkspaceRuntimeError("workspace %s needs named ports" % workspace_id)
            for purpose, port in ports.items():
                if not port_range[0] <= port <= port_range[1]:
                    raise WorkspaceRuntimeError(
                        "workspace %s port %s is outside its range"
                        % (workspace_id, purpose)
                    )
                self._register_port(
                    used_ports,
                    port,
                    "workspace:%s:%s" % (workspace_id, purpose),
                )
        return payload

    @staticmethod
    def _register_port(used: dict[int, str], value: Any, owner: str) -> None:
        if not isinstance(value, int) or not 1 <= value <= 65535:
            raise WorkspaceRuntimeError("%s has an invalid TCP port" % owner)
        if value in used:
            raise WorkspaceRuntimeError(
                "TCP port %d is assigned to both %s and %s"
                % (value, used[value], owner)
            )
        used[value] = owner

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise WorkspaceRuntimeError("git command failed: %s" % message)
        return result.stdout.strip()

    def branch(self) -> str:
        return self._git("branch", "--show-current")

    def is_clean(self) -> bool:
        return not self._git("status", "--porcelain=v1", "--untracked-files=all")

    def validate_identity(self) -> None:
        expected = self.workspace["branch"]
        actual = self.branch()
        if actual != expected:
            raise WorkspaceRuntimeError(
                "workspace %s must be on branch %s, not %s"
                % (self.workspace_id, expected, actual or "detached HEAD")
            )

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.runtime_dir, 0o700)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_lease(self) -> dict[str, Any] | None:
        try:
            lease = json.loads(self.lease_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as error:
            raise WorkspaceRuntimeError(
                "workspace lease is corrupt; inspect it without overwriting it"
            ) from error
        required = {"workspace", "branch", "session", "task", "started_at", "expires_at"}
        if not isinstance(lease, dict) or not required.issubset(lease):
            raise WorkspaceRuntimeError("workspace lease is incomplete")
        parse_time(lease["started_at"])
        parse_time(lease["expires_at"])
        return lease

    def _write_lease(self, lease: dict[str, Any]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.runtime_dir,
            prefix="workspace-lease.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(lease, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.lease_path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _expired(lease: dict[str, Any], now: datetime | None = None) -> bool:
        return parse_time(lease["expires_at"]) <= (now or utc_now())

    @staticmethod
    def _validate_session(session: str) -> None:
        if not SESSION_PATTERN.fullmatch(session):
            raise WorkspaceRuntimeError(
                "session must use 1-128 letters, digits, dots, underscores, colons, or hyphens"
            )

    def port_available(self, purpose: str) -> bool:
        try:
            port = self.workspace["ports"][purpose]
        except KeyError as error:
            raise WorkspaceRuntimeError("unknown port purpose: %s" % purpose) from error
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((self.workspace["bind"], port))
        except OSError:
            return False
        finally:
            probe.close()
        return True

    def claim(
        self,
        *,
        session: str,
        task: str,
        ttl_hours: float = 8,
    ) -> dict[str, Any]:
        self._validate_session(session)
        task = task.strip()
        if not task or len(task) > 240:
            raise WorkspaceRuntimeError("task must contain 1-240 characters")
        if not 0 < ttl_hours <= 24:
            raise WorkspaceRuntimeError("ttl-hours must be greater than 0 and at most 24")
        self.validate_identity()
        now = utc_now()
        with self._locked():
            existing = self._read_lease()
            if existing and not self._expired(existing, now):
                if existing["session"] != session:
                    raise WorkspaceRuntimeError(
                        "workspace is leased by session %s for %s until %s"
                        % (existing["session"], existing["task"], existing["expires_at"])
                    )
                existing["expires_at"] = format_time(now + timedelta(hours=ttl_hours))
                self._write_lease(existing)
                return existing
            if existing:
                raise WorkspaceRuntimeError(
                    "an expired lease remains; inspect the worktree, then run clear-expired"
                )
            if not self.is_clean():
                raise WorkspaceRuntimeError(
                    "worktree is not clean and has no lease; inspect existing work before claiming"
                )
            occupied = [
                purpose
                for purpose in self.workspace["ports"]
                if not self.port_available(purpose)
            ]
            if occupied:
                raise WorkspaceRuntimeError(
                    "assigned development ports are already in use: %s"
                    % ", ".join(sorted(occupied))
                )
            lease = {
                "branch": self.workspace["branch"],
                "expires_at": format_time(now + timedelta(hours=ttl_hours)),
                "host": socket.gethostname(),
                "session": session,
                "started_at": format_time(now),
                "task": task,
                "workspace": self.workspace_id,
            }
            self._write_lease(lease)
            return lease

    def renew(self, *, session: str, ttl_hours: float = 8) -> dict[str, Any]:
        self._validate_session(session)
        if not 0 < ttl_hours <= 24:
            raise WorkspaceRuntimeError("ttl-hours must be greater than 0 and at most 24")
        self.validate_identity()
        with self._locked():
            lease = self._read_lease()
            if not lease or self._expired(lease):
                raise WorkspaceRuntimeError("workspace does not have an active lease")
            if lease["session"] != session:
                raise WorkspaceRuntimeError("workspace lease belongs to another session")
            lease["expires_at"] = format_time(utc_now() + timedelta(hours=ttl_hours))
            self._write_lease(lease)
            return lease

    def release(self, *, session: str) -> None:
        self._validate_session(session)
        self.validate_identity()
        with self._locked():
            lease = self._read_lease()
            if not lease:
                raise WorkspaceRuntimeError("workspace does not have a lease")
            if lease["session"] != session:
                raise WorkspaceRuntimeError("workspace lease belongs to another session")
            if not self.is_clean():
                raise WorkspaceRuntimeError(
                    "worktree is dirty; commit or hand off the changes before releasing the lease"
                )
            self.lease_path.unlink()

    def clear_expired(self) -> None:
        self.validate_identity()
        with self._locked():
            lease = self._read_lease()
            if not lease:
                return
            if not self._expired(lease):
                raise WorkspaceRuntimeError("active leases cannot be cleared")
            if not self.is_clean():
                raise WorkspaceRuntimeError(
                    "expired lease has a dirty worktree; inspect and hand off before clearing"
                )
            self.lease_path.unlink()

    def require_lease(self, session: str) -> dict[str, Any]:
        self._validate_session(session)
        with self._locked():
            lease = self._read_lease()
            if not lease or self._expired(lease):
                raise WorkspaceRuntimeError("an active workspace lease is required")
            if lease["session"] != session:
                raise WorkspaceRuntimeError("workspace lease belongs to another session")
            return lease

    def environment(self, *, session: str, purpose: str) -> dict[str, str]:
        self.require_lease(session)
        try:
            port = self.workspace["ports"][purpose]
        except KeyError as error:
            raise WorkspaceRuntimeError("unknown port purpose: %s" % purpose) from error
        runtime = self.runtime_dir
        return {
            "APP_CACHE_DIR": str(runtime / "cache"),
            "APP_DATA_DIR": str(runtime / "data"),
            "APP_HOST": self.workspace["bind"],
            "APP_INSTANCE": self.workspace_id,
            "APP_LOG_DIR": str(runtime / "logs"),
            "APP_PORT": str(port),
            "APP_RUNTIME_DIR": str(runtime),
            "COMPOSE_PROJECT_NAME": self.workspace["compose_project"],
        }

    def status(self) -> dict[str, Any]:
        with self._locked():
            lease = self._read_lease()
        return {
            "branch": self.branch(),
            "clean": self.is_clean(),
            "lease": lease,
            "lease_expired": bool(lease and self._expired(lease)),
            "ports": self.workspace["ports"],
            "runtime_dir": str(self.runtime_dir),
            "workspace": self.workspace_id,
        }

    def doctor(self, session: str | None = None) -> dict[str, Any]:
        self.validate_identity()
        status = self.status()
        lease = status["lease"]
        if status["lease_expired"]:
            raise WorkspaceRuntimeError("workspace lease is expired")
        if not status["clean"] and not lease:
            raise WorkspaceRuntimeError("dirty worktree has no workspace lease")
        if session is not None:
            self.require_lease(session)
        return status


def print_lease(lease: dict[str, Any]) -> None:
    print(
        "workspace {workspace} leased to {session} for {task} until {expires_at}".format(
            **lease
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guard a shared server development workspace")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--config", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)

    claim = commands.add_parser("claim", help="atomically lease a clean workspace")
    claim.add_argument("--session", required=True)
    claim.add_argument("--task", required=True)
    claim.add_argument("--ttl-hours", type=float, default=8)

    renew = commands.add_parser("renew", help="extend the current session lease")
    renew.add_argument("--session", required=True)
    renew.add_argument("--ttl-hours", type=float, default=8)

    release = commands.add_parser("release", help="release a clean workspace")
    release.add_argument("--session", required=True)
    commands.add_parser("clear-expired", help="clear an expired lease from a clean workspace")

    status = commands.add_parser("status", help="show lease and runtime allocation")
    status.add_argument("--json", action="store_true")
    doctor = commands.add_parser("doctor", help="validate branch, lease, and runtime config")
    doctor.add_argument("--session")

    environment = commands.add_parser("env", help="print isolated runtime environment")
    environment.add_argument("purpose")
    environment.add_argument("--session", required=True)
    environment.add_argument("--json", action="store_true")

    run = commands.add_parser("run", help="run a foreground command on an assigned port")
    run.add_argument("purpose")
    run.add_argument("--session", required=True)
    run.add_argument("program", nargs=argparse.REMAINDER)
    return parser


def run_foreground(command: Sequence[str], environment: dict[str, str]) -> int:
    parent_pid = os.getppid()
    if parent_pid <= 1:
        raise WorkspaceRuntimeError(
            "run must stay attached to an interactive parent process"
        )
    child = subprocess.Popen(
        command,
        env=environment,
        start_new_session=True,
    )

    def forward(signum: int, _frame: Any) -> None:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    monitor_stop = threading.Event()

    def monitor_parent() -> None:
        while not monitor_stop.wait(0.25):
            if os.getppid() != parent_pid:
                forward(signal.SIGTERM, None)
                return

    forwarded_signals = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    previous_handlers = {
        signum: signal.signal(signum, forward) for signum in forwarded_signals
    }
    monitor = threading.Thread(target=monitor_parent, daemon=True)
    monitor.start()
    try:
        return child.wait()
    finally:
        monitor_stop.set()
        monitor.join(timeout=1)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(arguments)
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    runtime = WorkspaceRuntime(root, args.config)

    if args.command == "claim":
        print_lease(
            runtime.claim(session=args.session, task=args.task, ttl_hours=args.ttl_hours)
        )
    elif args.command == "renew":
        print_lease(runtime.renew(session=args.session, ttl_hours=args.ttl_hours))
    elif args.command == "release":
        runtime.release(session=args.session)
        print("workspace lease released")
    elif args.command == "clear-expired":
        runtime.clear_expired()
        print("expired workspace lease cleared")
    elif args.command in {"status", "doctor"}:
        status = runtime.doctor(getattr(args, "session", None)) if args.command == "doctor" else runtime.status()
        if getattr(args, "json", False):
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            print(
                "workspace={workspace} branch={branch} clean={clean} runtime={runtime_dir}".format(
                    **status
                )
            )
            if status["lease"]:
                print_lease(status["lease"])
            else:
                print("workspace has no lease")
            for purpose, port in sorted(status["ports"].items()):
                print("%s=127.0.0.1:%s" % (purpose, port))
    elif args.command == "env":
        environment = runtime.environment(session=args.session, purpose=args.purpose)
        if args.json:
            print(json.dumps(environment, indent=2, sort_keys=True))
        else:
            for name, value in sorted(environment.items()):
                print("export %s=%s" % (name, shlex.quote(value)))
    elif args.command == "run":
        command = list(args.program)
        if command and command[0] == "--":
            command.pop(0)
        if not command:
            raise WorkspaceRuntimeError("run requires a command after --")
        if not runtime.port_available(args.purpose):
            raise WorkspaceRuntimeError("assigned port is already in use")
        environment = runtime.environment(session=args.session, purpose=args.purpose)
        for directory_name in ("APP_CACHE_DIR", "APP_DATA_DIR", "APP_LOG_DIR"):
            Path(environment[directory_name]).mkdir(parents=True, exist_ok=True)
        replacements = {
            "{host}": environment["APP_HOST"],
            "{instance}": environment["APP_INSTANCE"],
            "{port}": environment["APP_PORT"],
            "{runtime_dir}": environment["APP_RUNTIME_DIR"],
        }
        command = [replacements.get(value, value) for value in command]
        child_environment = os.environ.copy()
        child_environment.update(environment)
        return run_foreground(command, child_environment)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkspaceRuntimeError as error:
        print("workspace-runtime: %s" % error, file=sys.stderr)
        raise SystemExit(2)
