# Server Workspace Rules

These instructions apply to every agent operating from this local control folder.

## Fixed scope

- Connect through the local SSH alias `aliyun-server`; never copy or expose private keys or tokens.
- The only server checkout this operator may edit is `/root/ai-workspaces/agent-1`, on branch `agent-1`.
- Do not manually edit sibling workspaces such as `agent-2`. Share rules and work through pull requests into `main`; each workspace updates itself from `main`.
- Do not edit non-environment files outside `agent-1`. If an exception is genuinely required, treat it as an environment change and follow the dedicated environment-change PR process.

## Required workflow

1. Read `STATUS.md`, `TASKS.md`, `COORDINATION.md`, and `ENVIRONMENT_CHANGES.md` before starting.
2. Run `./server.ps1 progress` to refresh the local copies from the server.
3. Confirm the worktree is clean, then atomically claim it before editing: `python3 tools/workspace_runtime.py claim --session <stable-session-id> --task "<task>"`.
4. If the claim fails, stop. Never stash, reset, delete, or adopt the other session's work. Inspect the reported lease and worktree instead.
5. Fetch and rebase `agent-1` on `origin/main`, then run `python3 tools/workspace_runtime.py doctor --session <stable-session-id>`.
6. Keep all ordinary work, temporary files, and upload staging under `agent-1`. Runtime data goes under `.runtime`; remote uploads go to `.cache/uploads`.
7. Push every meaningful iteration to `origin/agent-1` and keep a draft or open PR visible while work is active.
8. When a coherent unit is complete, verify it, check coordination conflicts, and merge the pull request into `main` when safe.
9. Update `STATUS.md` and `TASKS.md`, rebase the clean branch on merged `main`, then release the lease with `python3 tools/workspace_runtime.py release --session <stable-session-id>`.
10. Run `./server.ps1 progress` so the local mirror matches the server.

## Runtime isolation

- `config/workspace-runtime.json` is the canonical port and namespace registry. Do not invent ports in task-specific instructions.
- Development listeners bind only to the configured `127.0.0.1` ports. Do not use `8765`, `8790`, or another shared/deployment port for workspace development.
- Start foreground development commands through `tools/workspace_runtime.py run`; it requires the matching active lease and injects workspace-specific data, cache, log, and Compose namespaces.
- Tests must request ephemeral ports (`0`) whenever the application supports it. Shared integration tests that cannot isolate their resources must run serially.
- Stable services belong to `main`-derived deployment artifacts, never a mutable agent checkout. Package, service, firewall, deployment-directory, or shared-database changes use the environment-change workflow.

## Environment and outside-workspace changes

- Before changing packages, services, shell profiles, global tools, credentials wiring, or files outside `agent-1`, add a record to `ENVIRONMENT_CHANGES.md`.
- Put the normative record in a dedicated PR that is not mixed with product or task changes.
- Record reason, exact scope, commands/actions, verification, rollback, and affected operators.
- Never include secrets in Git, logs, local mirrors, PRs, or chat output.

## Network transfer

- Download external artifacts to this machine first with `./server.ps1 download <https-url> [name]`.
- Upload only from local `downloads/` with `./server.ps1 upload <file> [remote-relative-path]`.
- Verify SHA-256 locally and on the server before installation or execution.

For operational details, read `OPERATIONS.md`. For reusable agent behavior, load `skills/server-workspace-ops/SKILL.md`.
