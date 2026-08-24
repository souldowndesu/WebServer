# Coordination Guide

All work is integrated through GitHub. Each operator edits only its assigned checkout and branch.

## Workspace ownership

- Agent 1: `/root/ai-workspaces/agent-1`, branch `agent-1`.
- Agent 2: `/root/ai-workspaces/agent-2`, branch `agent-2`.
- Shared integration branch: `main`.
- This operator may edit only `agent-1`. Do not manually change `agent-2`; publish shared rules through a PR to `main` and let each workspace update itself.
- Canonical remote: `https://github.com/souldowndesu/WebServer.git`. Each workspace owner verifies and updates only its own `origin`; this operator must not change agent-2's Git configuration.

## Two-layer ownership

Git ownership and runtime ownership are separate:

| Resource | Agent 1 | Agent 2 | Shared/main owner |
| --- | --- | --- | --- |
| Checkout | `/root/ai-workspaces/agent-1` | `/root/ai-workspaces/agent-2` | None |
| Branch | `agent-1` | `agent-2` | `main` integrates PRs |
| Lease file | `agent-1/.runtime/workspace-lease.json` | `agent-2/.runtime/workspace-lease.json` | None |
| Control-plane preview | `127.0.0.1:18761` | `127.0.0.1:18861` | Not deployed |
| Compose project | `agent1` | `agent2` | Deployment chooses its own name |
| Data/cache/logs | `agent-1/.runtime/*` | `agent-2/.runtime/*` | Deployed service-owned paths |

`config/workspace-runtime.json` is normative. Port ranges are reserved per workspace even when only some named ports are currently assigned. Development ports stay loopback-only and do not receive UFW rules.

## Workspace lease

A local lease prevents two Codex tasks, terminals, or operators from using the same checkout concurrently. It complements, but does not replace, the GitHub-visible task record.

1. The first operation on a clean workspace is `python3 tools/workspace_runtime.py claim --session <stable-session-id> --task "<task>"`.
2. The claim uses a filesystem lock and refuses an active lease, an unowned dirty worktree, the wrong branch, or an occupied assigned port.
3. Record the task in `STATUS.md` and `TASKS.md`, push it, and open a Draft PR so the other workspace can see cross-workspace intent.
4. Renew long tasks before the lease expires. A lease may last at most 24 hours.
5. Release only after the worktree is clean and the handoff is recorded. An expired lease with dirty files is a protected handoff, not permission to clear or overwrite files.

A lease is deliberately stored under ignored `.runtime/`; it coordinates sessions sharing one checkout without creating Git conflicts. GitHub Draft PRs and `TASKS.md` coordinate between the two independent checkouts.

## Runtime rules

- Run development processes in the foreground through `tools/workspace_runtime.py run`, or use the environment printed by its `env` command.
- Never hard-code `container_name`. Compose receives the configured `COMPOSE_PROJECT_NAME`; volumes, networks, databases, Redis keys, queue names, uploads, and logs must also include `APP_INSTANCE` or live under `APP_RUNTIME_DIR`.
- Unit tests use TCP port `0` and temporary directories. Only tests that genuinely require a shared installed service may use deployment ports, and those tests run serially.
- TCP 7890 is a shared client-facing proxy endpoint. Agents may consume it but must not start a second Mihomo instance.
- Legacy TCP 8765 and 8790 were retired through environment PRs #22 and #23. They are unassigned and must not be revived without updating the registry and environment ledger.
- A stable systemd service must not read either agent checkout. Deployment changes are serialized through a dedicated environment-change PR and operate only on a reviewed `main` commit.

## Before starting work

1. Read `STATUS.md`, `TASKS.md`, and open PRs.
2. Confirm the current checkout and assigned branch.
3. Run:

```sh
python3 tools/workspace_runtime.py claim --session <stable-session-id> --task "<task>"
git fetch origin
git rebase origin/main
python3 tools/workspace_runtime.py doctor --session <stable-session-id>
```

4. Claim or update the task in `STATUS.md` and `TASKS.md`, push the claim, and create a Draft PR before material edits.

## Iterations and pull requests

1. Keep commits small and describe intent clearly.
2. Push every meaningful iteration only to the assigned workspace branch.
3. Do not force-push shared history and do not commit directly to `main`.
4. When a coherent related unit is complete, open a PR into `main`.
5. Inspect the diff, checks, scope, and coordination conflicts. The repository owner may approve and merge when safe.
6. Record the PR and result in `STATUS.md` and `TASKS.md`.
7. After merge, each workspace fetches and rebases its own branch onto updated `main`.
8. Release the workspace lease only after the branch and worktree are clean.

## Environment or outside-workspace changes

Environment changes include packages, services, global tools, shell profiles, credential wiring, and any file outside the assigned workspace. They require a dedicated documentation-only PR based on `ENVIRONMENT_CHANGES.md`; do not mix that PR with ordinary work.

The record must state:

- reason and owner;
- exact paths, packages, services, or settings affected;
- planned and actual commands/actions;
- verification and observed result;
- rollback procedure;
- coordination impact and PR.

Non-environment edits outside the assigned workspace are prohibited. If one is unavoidable, handle it under the same dedicated record and PR process before making the change.

## Conflict and handoff rules

- If two agents need the same file, agree on ownership first or split the work into separate files.
- Resolve conflicts on the feature/workspace branch, never directly on `main`.
- Never overwrite, reset, delete, or adopt unrecognized changes.
- Before handoff, push the branch and record unfinished work, decisions, risks, verification, and the recommended next action.

## Artifact transfer

External artifacts are downloaded to the local control machine first, hashed, uploaded to `agent-1/.cache/uploads`, and hashed again. Installation that changes the environment follows the dedicated environment-change PR process.
