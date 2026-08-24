# Server Operations Runbook

## Known endpoints and paths

| Purpose | Value |
| --- | --- |
| Local SSH alias | `aliyun-server` |
| SSH account | `root` (resolved by local SSH config) |
| Editable server workspace | `/root/ai-workspaces/agent-1` |
| Assigned branch | `agent-1` |
| Integration branch | `main` |
| GitHub repository | `souldowndesu/WebServer` |
| Agent 1 development ports | `127.0.0.1:18761-18799` |
| Agent 2 development ports | `127.0.0.1:18861-18899` |
| Safe remote upload staging | `/root/ai-workspaces/agent-1/.cache/uploads` |
| Server GitHub CLI wrapper | `/root/.local/bin/agent-gh` |

Do not copy the private key or GitHub token into this directory, the repository, logs, PRs, or chat output.

## Routine operations

Prefer the local wrapper:

```powershell
.\server.ps1 status
.\server.ps1 progress
.\server.ps1 git
.\server.ps1 push
.\server.ps1 prs
.\server.ps1 workspace
```

Use `connect` only when an interactive shell is needed:

```powershell
.\server.ps1 connect
```

The equivalent direct connection is `ssh aliyun-server`.

## Local-first download and upload

The server's external network is not trusted for reliable downloads. Use this sequence:

1. Download to local `downloads/`.
2. Record the source URL, version, and local SHA-256.
3. Upload into `agent-1/.cache/uploads/`.
4. Verify SHA-256 again on the server.
5. If installation changes the environment, stop and follow the dedicated environment-change PR process before installing.

```powershell
.\server.ps1 download <https-url> [local-name]
.\server.ps1 upload <local-file-or-name> [remote-relative-path]
```

Do not upload directly into `/usr`, `/opt`, `/root/.local`, another workspace, or the repository source tree. Stage first, verify, then perform an explicitly authorized and documented installation.

## Workspace lease and development runtime

Every editing session claims its own checkout before changing files. Choose a stable, non-secret session identifier and reuse it for renew/release commands:

```sh
cd /root/ai-workspaces/agent-1
python3 tools/workspace_runtime.py claim \
  --session codex-example-task \
  --task "short task description"
python3 tools/workspace_runtime.py doctor --session codex-example-task
```

If claim reports another lease or an unowned dirty tree, stop and inspect. Do not clear, stash, reset, or overwrite it. For a long task:

```sh
python3 tools/workspace_runtime.py renew --session codex-example-task
```

Run a preview with the assigned loopback address and strict named port:

```sh
python3 tools/workspace_runtime.py run \
  --session codex-example-task chat -- \
  python3 -m chat_app.server --host {host} --port {port}
```

The wrapper exports `APP_INSTANCE`, `APP_HOST`, `APP_PORT`, `APP_RUNTIME_DIR`, `APP_DATA_DIR`, `APP_CACHE_DIR`, `APP_LOG_DIR`, and `COMPOSE_PROJECT_NAME`. It refuses an occupied port. Keep the command in the foreground so its lifecycle stays visible.

When the handoff is recorded and the worktree is clean:

```sh
python3 tools/workspace_runtime.py release --session codex-example-task
```

Assigned runtime resources:

| Purpose | Agent 1 | Agent 2 | Shared/deployed |
| --- | --- | --- | --- |
| Chat preview | `127.0.0.1:18761` | `127.0.0.1:18861` | `0.0.0.0:8765` |
| Proxy-control preview | `127.0.0.1:18762` | `127.0.0.1:18862` | `127.0.0.1:8790` |
| Mihomo client proxy | Do not start | Do not start | `127.0.0.1:7890` |

Tests use ephemeral port `0`. Workspace state belongs under ignored `.runtime/`. For Docker Compose, consume `COMPOSE_PROJECT_NAME` and never set a fixed `container_name`.

## Git and GitHub

Run Git inside `/root/ai-workspaces/agent-1`. The repository already has a restricted credential helper. GitHub CLI operations must use `/root/.local/bin/agent-gh`; plain `gh` does not inherit the protected repository token.

The least-privilege credential helper was migrated through environment PRs #15 and #16 and now authorizes only `https://github.com/souldowndesu/WebServer.git`. Agent-1 `origin` and the local relay push remote must use that exact canonical URL. Agent-2's owner updates its own `origin` after receiving the merged shared instructions.

Start an iteration:

```sh
git -C /root/ai-workspaces/agent-1 fetch origin
git -C /root/ai-workspaces/agent-1 rebase origin/main
```

Checkpoint an iteration:

```sh
git -C /root/ai-workspaces/agent-1 add -- <explicit-paths>
git -C /root/ai-workspaces/agent-1 commit -m "Describe the coherent change"
git -C /root/ai-workspaces/agent-1 push origin agent-1
```

If the server-to-GitHub connection times out or terminates TLS, use the local relay instead of repeatedly retrying or copying credentials:

```powershell
.\server.ps1 push
```

The relay keeps a temporary nested checkout in local `state/git-relay`, fetches the committed `agent-1` state over SSH, and pushes through the local network. Its Git credential helper calls the server's repository-restricted helper over SSH; the token is not stored locally or printed. The action refuses a dirty relay, an unexpected branch/remote, or a non-fast-forward update.

Open and merge a completed unit:

```sh
cd /root/ai-workspaces/agent-1
/root/.local/bin/agent-gh pr create --repo souldowndesu/WebServer --base main --head agent-1 --fill
/root/.local/bin/agent-gh pr checks <number>
/root/.local/bin/agent-gh pr merge <number> --merge
```

Before merging, inspect the diff, validate the result, and check for conflicting work. Never force-push shared history or commit directly to `main`.

## Progress records

`STATUS.md` and `TASKS.md` in the server repository are canonical. `./server.ps1 progress` copies them and the operating documents to this local directory, then prints the current progress. Local copies are mirrors and must not diverge.

Update both documents before a handoff, PR merge, or end of a work session. Include the current task, owner, branch, state, verification, PR, and next action.

## Environment changes

Packages, services, global tools, profiles, credential wiring, and files outside `agent-1` are environment changes. Before applying one:

1. Add a complete entry to `ENVIRONMENT_CHANGES.md`.
2. Commit and push it on `agent-1` as a dedicated documentation-only change.
3. Open a dedicated PR to `main`; do not mix product changes.
4. Apply the change only after scope and rollback are explicit.
5. Update the same record with actual verification and final state.

An unavoidable non-environment edit outside `agent-1` follows the same process. Ordinary non-environment edits outside `agent-1` are prohibited.

Stable services are installed only from a reviewed `main` commit into service-owned deployment paths such as `/opt/proxy-control`. A systemd unit must never point at `/root/ai-workspaces/agent-1` or `/root/ai-workspaces/agent-2`. Deployment changes are serialized; record the exact source commit and deployed/source hashes.

## Failure boundaries

- If SSH fails, run `ssh -v aliyun-server` only for diagnosis and redact sensitive paths or values from shared output.
- If GitHub access fails, verify `/root/.local/bin/agent-gh auth status`; do not print or read the token file.
- If a download is incomplete or its hash differs, discard the staged copy and retry from the local machine.
- If the server worktree is dirty with unrecognized changes, stop and inspect; do not reset, overwrite, or delete them.
- If a lease is expired but the worktree is dirty, treat it as an unfinished handoff. Do not run `clear-expired` until ownership and preservation are resolved.
