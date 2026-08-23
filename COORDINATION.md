# Coordination Guide

All work is integrated through GitHub. Each operator edits only its assigned checkout and branch.

## Workspace ownership

- Agent 1: `/root/ai-workspaces/agent-1`, branch `agent-1`.
- Agent 2: `/root/ai-workspaces/agent-2`, branch `agent-2`.
- Shared integration branch: `main`.
- This operator may edit only `agent-1`. Do not manually change `agent-2`; publish shared rules through a PR to `main` and let each workspace update itself.

## Before starting work

1. Read `STATUS.md`, `TASKS.md`, and open PRs.
2. Confirm the current checkout and assigned branch.
3. Run:

```sh
git fetch origin
git rebase origin/main
```

4. Claim or update the task in `STATUS.md` and `TASKS.md` when coordination would benefit from it.

## Iterations and pull requests

1. Keep commits small and describe intent clearly.
2. Push every meaningful iteration only to the assigned workspace branch.
3. Do not force-push shared history and do not commit directly to `main`.
4. When a coherent related unit is complete, open a PR into `main`.
5. Inspect the diff, checks, scope, and coordination conflicts. The repository owner may approve and merge when safe.
6. Record the PR and result in `STATUS.md` and `TASKS.md`.
7. After merge, each workspace fetches and rebases its own branch onto updated `main`.

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
