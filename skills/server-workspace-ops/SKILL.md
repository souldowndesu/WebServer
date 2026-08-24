---
name: server-workspace-ops
description: Operate the user's aliyun-server through the local SSH control folder, including atomic workspace leases, isolated development ports/runtime state, status mirroring, local-first transfers, agent-1 GitHub collaboration, main-derived deployment boundaries, and documented environment changes. Use for this server only; do not use it for unrelated SSH hosts or manually edit sibling workspaces.
---

# Server Workspace Operations

Use the established paths and wrappers; do not rediscover credentials or create a second workspace.

## Load context

Before acting, read the nearest `AGENTS.md`, then read `STATUS.md`, `TASKS.md`, `COORDINATION.md`, and `ENVIRONMENT_CHANGES.md`. Read `OPERATIONS.md` when the task involves connection, transfer, GitHub, troubleshooting, or environment state.

## Route by execution context

- From the local control folder, prefer `./server.ps1 <action>`.
- On the server, work only in `/root/ai-workspaces/agent-1` on branch `agent-1`.
- Never manually edit `/root/ai-workspaces/agent-2`. Cross-workspace synchronization happens through PRs into `main`.
- Treat Git workspace ownership and runtime ownership as separate controls; both must be valid before starting a process.

## Short actions

- Connect: `./server.ps1 connect`
- Observe and save snapshot: `./server.ps1 status`
- Refresh and show canonical progress: `./server.ps1 progress`
- Inspect Git: `./server.ps1 git`
- Push through the local network: `./server.ps1 push`
- List open PRs: `./server.ps1 prs`
- Show agent-1 lease and development ports: `./server.ps1 workspace`
- Download locally: `./server.ps1 download <https-url> [name]`
- Upload staged artifact: `./server.ps1 upload <downloads-file> [remote-relative-path]`

Treat `STATUS.md` and `TASKS.md` on the server as canonical; local copies are mirrors.

## Claim before work

From a clean agent-1 checkout, create an atomic local lease before any material edit or long-running development process:

```sh
python3 tools/workspace_runtime.py claim \
  --session <stable-non-secret-session-id> \
  --task "<short task description>"
```

If it refuses because of another lease, dirty unowned files, the wrong branch, or occupied assigned ports, stop and inspect. Never use stash/reset/delete as a way to obtain the lease. Push the task claim and open a Draft PR so agent-2 can see the cross-workspace intent.

After fetch/rebase, validate with `python3 tools/workspace_runtime.py doctor --session <session-id>`. Renew long work with the `renew` command. Release only after the branch is rebased, the worktree is clean, and `STATUS.md`/`TASKS.md` contain the handoff.

## Runtime allocation

- The registry is `config/workspace-runtime.json`: agent-1 uses loopback range 18761-18799; agent-2 uses 18861-18899.
- Stable/shared ports 7890, 8765, and 8790 are not development ports. Do not start substitute shared services.
- Run previews through `python3 tools/workspace_runtime.py run --session <session-id> <purpose> -- <command>`. Use `{host}` and `{port}` arguments so the wrapper injects the exact allocation.
- Keep data, cache, logs, PIDs, sockets, uploads, databases, and queue names workspace-scoped. The wrapper provides `APP_INSTANCE`, `.runtime` paths, and `COMPOSE_PROJECT_NAME`.
- Unit tests request port `0`. Serialize only the integration checks that truly need an installed shared service.
- Stable services run from reviewed `main` deployment artifacts, never agent-1 or agent-2. Deployment/systemd/global changes follow the dedicated environment-change workflow.

## Invariants

- Keep ordinary source, task files, temporary data, and uploaded artifacts inside `agent-1`; use `.cache/uploads` for remote staging.
- Download external artifacts to local `downloads/` first, record their source/version, verify SHA-256, upload, and verify SHA-256 again.
- Do not reveal or copy SSH keys or GitHub tokens. Use `/root/.local/bin/agent-gh` for GitHub CLI operations.
- When server-to-GitHub push is unreliable, use local `./server.ps1 push`; its restricted SSH credential relay must not be replaced with a token file or printed credential command.
- Use `https://github.com/souldowndesu/WebServer.git` for agent-1 origin and the local relay. Environment PRs #15 and #16 migrated the least-privilege helper to this canonical path. Agent-2's owner updates only its own origin after receiving shared rules from `main`.
- Fetch and rebase on `origin/main` before work. Push each meaningful iteration to `origin/agent-1`. Open a PR for each coherent completed unit and merge only after diff, validation, and coordination checks.
- Before changing packages, services, global tools, profiles, credential wiring, or anything outside `agent-1`, add a complete entry to `ENVIRONMENT_CHANGES.md` and use a dedicated documentation-only PR. Do not mix that PR with ordinary work.
- If the worktree contains unrecognized changes, stop and inspect. Never overwrite, reset, or delete them.
- If a lease expires while the worktree is dirty, preserve it as an unfinished handoff. `clear-expired` is allowed only after ownership is resolved and the tree is clean.
- Never bind a development service to a deployment port or a non-loopback interface.

## Completion

Update `STATUS.md` and `TASKS.md`, push the assigned branch, create or update the relevant PR, merge when safe, rebase the clean branch on `main`, release the workspace lease, and run local `./server.ps1 progress` so the local process record exactly matches the server.
