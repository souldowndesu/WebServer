---
name: server-workspace-ops
description: Operate the user's aliyun-server through the local SSH control folder, including status checks, progress mirroring, local-first downloads/uploads, agent-1 GitHub workflow, and documented environment changes. Use for this server only; do not use it for unrelated SSH hosts or sibling workspaces.
---

# Server Workspace Operations

Use the established paths and wrappers; do not rediscover credentials or create a second workspace.

## Load context

Before acting, read the nearest `AGENTS.md`, then read `STATUS.md`, `TASKS.md`, `COORDINATION.md`, and `ENVIRONMENT_CHANGES.md`. Read `OPERATIONS.md` when the task involves connection, transfer, GitHub, troubleshooting, or environment state.

## Route by execution context

- From the local control folder, prefer `./server.ps1 <action>`.
- On the server, work only in `/root/ai-workspaces/agent-1` on branch `agent-1`.
- Never manually edit `/root/ai-workspaces/agent-2`. Cross-workspace synchronization happens through PRs into `main`.

## Short actions

- Connect: `./server.ps1 connect`
- Observe and save snapshot: `./server.ps1 status`
- Refresh and show canonical progress: `./server.ps1 progress`
- Inspect Git: `./server.ps1 git`
- Push through the local network: `./server.ps1 push`
- List open PRs: `./server.ps1 prs`
- Download locally: `./server.ps1 download <https-url> [name]`
- Upload staged artifact: `./server.ps1 upload <downloads-file> [remote-relative-path]`

Treat `STATUS.md` and `TASKS.md` on the server as canonical; local copies are mirrors.

## Invariants

- Keep ordinary source, task files, temporary data, and uploaded artifacts inside `agent-1`; use `.cache/uploads` for remote staging.
- Download external artifacts to local `downloads/` first, record their source/version, verify SHA-256, upload, and verify SHA-256 again.
- Do not reveal or copy SSH keys or GitHub tokens. Use `/root/.local/bin/agent-gh` for GitHub CLI operations.
- When server-to-GitHub push is unreliable, use local `./server.ps1 push`; its restricted SSH credential relay must not be replaced with a token file or printed credential command.
- Fetch and rebase on `origin/main` before work. Push each meaningful iteration to `origin/agent-1`. Open a PR for each coherent completed unit and merge only after diff, validation, and coordination checks.
- Before changing packages, services, global tools, profiles, credential wiring, or anything outside `agent-1`, add a complete entry to `ENVIRONMENT_CHANGES.md` and use a dedicated documentation-only PR. Do not mix that PR with ordinary work.
- If the worktree contains unrecognized changes, stop and inspect. Never overwrite, reset, or delete them.

## Completion

Update `STATUS.md` and `TASKS.md`, push the assigned branch, create or update the relevant PR, and run local `./server.ps1 progress` so the local process record exactly matches the server.
