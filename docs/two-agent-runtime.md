# Two-agent Git and runtime isolation

Two agents may edit and test concurrently because source ownership, runtime ownership, and deployment ownership are independent.

```text
agent-1 checkout -> agent-1 branch --\
                                      +-> PR -> main -> deployed artifact -> stable service
agent-2 checkout -> agent-2 branch --/

agent-1 preview -> 127.0.0.1:18761-18799 -> agent-1/.runtime
agent-2 preview -> 127.0.0.1:18861-18899 -> agent-2/.runtime
```

## Ownership model

### Git workspace

Each agent edits only its matching checkout and branch. It pushes meaningful iterations to that branch and integrates only through a PR into `main`. After one PR merges, the other agent rebases on the new `main` before its own merge.

### Local workspace lease

A lease prevents two tasks from entering the same checkout. `tools/workspace_runtime.py` uses `flock` plus an atomically replaced JSON lease under ignored `.runtime/`.

A lease contains only workspace, branch, host, session identifier, task, and timestamps. It contains no keys, tokens, subscription data, or credentials.

The safety decisions are intentional:

- A clean, correctly branched workspace with free assigned ports can be claimed.
- A second session cannot claim an active lease.
- A dirty workspace without a lease is protected as unowned work.
- An expired lease with dirty files is protected as an unfinished handoff.
- Release requires both the matching session and a clean worktree.

The local lease is not visible across separate checkouts, so each task also pushes its `STATUS.md`/`TASKS.md` claim and opens a Draft PR. That is the cross-workspace coordination signal.

## Port and process ownership

The canonical registry is `config/workspace-runtime.json`.

| Scope | Bind/range | Rule |
| --- | --- | --- |
| Agent 1 development | `127.0.0.1:18761-18799` | Only while agent-1 lease is active |
| Agent 2 development | `127.0.0.1:18861-18899` | Only while agent-2 lease is active |
| Mihomo proxy | `127.0.0.1:7890` | Shared client endpoint; neither agent starts it |
| Connectivity chat | `0.0.0.0:8765` | Stable main deployment only |
| Proxy control | `127.0.0.1:8790` | Stable main deployment only |

Development listeners remain loopback-only and are reached through SSH tunnels when browser access is required. No UFW or cloud firewall rule is added for a preview.

Applications should run in the foreground through:

```sh
python3 tools/workspace_runtime.py run \
  --session <session-id> <purpose> -- <command using {host} and {port}>
```

The wrapper verifies the active lease and free assigned port, creates workspace-local cache/data/log directories, and injects:

- `APP_INSTANCE`
- `APP_HOST`
- `APP_PORT`
- `APP_RUNTIME_DIR`
- `APP_DATA_DIR`
- `APP_CACHE_DIR`
- `APP_LOG_DIR`
- `COMPOSE_PROJECT_NAME`

## Stateful dependencies

Every mutable development resource must include the workspace identity:

| Resource | Isolation rule |
| --- | --- |
| SQLite/files/uploads | Store below `APP_DATA_DIR` |
| Cache/log/PID/socket | Store below the corresponding `.runtime` directory |
| PostgreSQL/MySQL | Separate database such as `app_agent1` and `app_agent2` |
| Redis | Separate database plus `APP_INSTANCE` key prefix |
| Queues/topics | Prefix names with `APP_INSTANCE` |
| Docker Compose | Use injected `COMPOSE_PROJECT_NAME`; omit `container_name` |
| Volumes/networks | Let Compose namespace them or include `APP_INSTANCE` |

If a dependency cannot be namespaced safely, it is a shared integration resource and access to it must be serialized.

## Tests

Unit and application tests bind TCP port `0`, letting the kernel allocate an ephemeral port. Test data uses temporary directories. This keeps normal PR verification parallel-safe.

An end-to-end test that depends on an installed service, database migration, or other shared state runs serially after ordinary isolated tests. It must restore the observed state before releasing the integration lock.

## Stable deployment

A stable service is built or copied from an identified, reviewed `main` commit into a service-owned path such as `/opt/proxy-control`. The deployed files are root-owned/read-only where practical, and deployed/source SHA-256 values are checked.

Systemd units never set `WorkingDirectory` or `PYTHONPATH` to `agent-1` or `agent-2`. Therefore rebases, uncommitted development, and branch changes cannot alter the next service restart.

Creating or updating the deployment path, systemd unit, packages, firewall, credentials wiring, or shared data is an environment change. It uses a dedicated documentation-only PR with exact scope, verification, rollback, and coordination impact before application.

## Lifecycle

1. Read progress, task board, open PRs, and environment ledger.
2. Confirm the assigned worktree is clean and claim it atomically.
3. Fetch and rebase on `origin/main`; run the runtime doctor.
4. Push the task record and open a Draft PR.
5. Edit only the assigned checkout. Use named preview ports and `.runtime` state.
6. Run isolated tests, inspect the diff, and push meaningful iterations.
7. Rebase on current `main`, verify again, and merge the PR when safe.
8. Record the handoff, leave the branch/worktree clean, and release the lease.
9. Each other workspace independently fetches/rebases to receive the merged rules.
