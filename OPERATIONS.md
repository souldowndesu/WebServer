# Server Operations Runbook

## Known endpoints and paths

| Purpose | Value |
| --- | --- |
| Local SSH alias | `aliyun-server` |
| SSH account | `root` (resolved by local SSH config) |
| Editable server workspace | `/root/ai-workspaces/agent-1` |
| Assigned branch | `agent-1` |
| Integration branch | `main` |
| GitHub repository | `souldowndesu/agent` |
| Safe remote upload staging | `/root/ai-workspaces/agent-1/.cache/uploads` |
| Server GitHub CLI wrapper | `/root/.local/bin/agent-gh` |

Do not copy the private key or GitHub token into this directory, the repository, logs, PRs, or chat output.

## Routine operations

Prefer the local wrapper:

```powershell
.\server.ps1 status
.\server.ps1 progress
.\server.ps1 git
.\server.ps1 prs
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

## Git and GitHub

Run Git inside `/root/ai-workspaces/agent-1`. The repository already has a restricted credential helper. GitHub CLI operations must use `/root/.local/bin/agent-gh`; plain `gh` does not inherit the protected repository token.

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

Open and merge a completed unit:

```sh
cd /root/ai-workspaces/agent-1
/root/.local/bin/agent-gh pr create --base main --head agent-1 --fill
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

## Failure boundaries

- If SSH fails, run `ssh -v aliyun-server` only for diagnosis and redact sensitive paths or values from shared output.
- If GitHub access fails, verify `/root/.local/bin/agent-gh auth status`; do not print or read the token file.
- If a download is incomplete or its hash differs, discard the staged copy and retry from the local machine.
- If the server worktree is dirty with unrecognized changes, stop and inspect; do not reset, overwrite, or delete them.
