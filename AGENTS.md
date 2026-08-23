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
3. Fetch and rebase `agent-1` on `origin/main` before editing.
4. Keep all ordinary work, temporary files, and upload staging under `agent-1`. Remote uploads go to `agent-1/.cache/uploads`.
5. Push every meaningful iteration to `origin/agent-1`.
6. When a coherent unit is complete, open a pull request from `agent-1` to `main`; verify it, check coordination conflicts, and merge it when safe.
7. Update `STATUS.md` and `TASKS.md`, then refresh the local copies with `./server.ps1 progress`.

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
