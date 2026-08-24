# Environment Change Ledger

This ledger documents changes to server state outside the assigned Git workspace. Every planned environment or unavoidable outside-workspace change requires its own documentation-only PR.

Never record secrets or secret values.

## Baseline observed on 2026-08-24

This is an observation, not a change made by the current initialization:

- Server: Ubuntu Linux, SSH alias `aliyun-server`.
- Editable workspace: `/root/ai-workspaces/agent-1` on branch `agent-1`.
- Git remote: `https://github.com/souldowndesu/agent.git`.
- Restricted Git credential helper is configured for this repository.
- GitHub CLI access is provided by `/root/.local/bin/agent-gh`.
- Local-first uploads stage at `/root/ai-workspaces/agent-1/.cache/uploads`.

## Change records

No server environment changes were made during the workflow-document initialization.

### 2026-08-24 — Public connectivity chat on TCP 8765

- State: applied
- Owner: Agent 1
- Dedicated PR: #6 (plan) and #7 (applied verification)
- Reason: run the merged clock page, browser chat, and HTTP API as a restartable server service and expose TCP 8765 for local-to-server connectivity tests.
- Scope (exact paths/packages/services/settings): create /etc/systemd/system/connectivity-chat.service; enable and start connectivity-chat.service; add one UFW allow rule for 8765/tcp (IPv4 and IPv6). No packages, credentials, profiles, or sibling workspaces change.
- Source URL/version/SHA-256, if applicable: no external artifact; application source is repository main merge commit 8653e1c8d06c785c462fb2813919617d464afcbb.
- Planned actions:
  1. Stage the unit only under /root/ai-workspaces/agent-1/.cache/uploads/connectivity-chat.service.
  2. Validate the staged unit with systemd-analyze verify.
  3. Install it at mode 0644 to /etc/systemd/system/connectivity-chat.service and run systemctl daemon-reload.
  4. Add UFW rule allow 8765/tcp with comment connectivity-chat.
  5. Enable and start connectivity-chat.service.
- Planned unit: runs /usr/bin/python3 -m chat_app.server --host 0.0.0.0 --port 8765 from /root/ai-workspaces/agent-1; restarts on failure; disables bytecode writes; applies NoNewPrivileges, private temporary storage, kernel/control-group protections, restricted address families, a 128 MB memory ceiling, and a 64-task ceiling.
- Actual actions: staged the unit under agent-1/.cache/uploads with SHA-256 d026c684c09dbf7da19855cc0028d71111cd71f1d01df47c5040bcee47f1dffc; systemd-analyze accepted it with only unrelated pre-existing warnings; installed /etc/systemd/system/connectivity-chat.service at mode 0644; ran daemon-reload; after explicit user approval added the UFW 8765/tcp connectivity-chat rule for IPv4/IPv6; enabled and started connectivity-chat.service.
- Verification and result: systemd reports enabled, active, and running with ExecMainStatus 0; python listens on 0.0.0.0:8765; UFW lists allow rules for 8765/tcp on IPv4 and IPv6; server-local health returned status ok; a direct public request from the operator machine returned status ok; the hash-matched local CLI sent message #1 through the public port and retrieved the same message from server history.
- Rollback: systemctl disable --now connectivity-chat.service; remove only /etc/systemd/system/connectivity-chat.service; systemctl daemon-reload; delete only the UFW 8765/tcp connectivity-chat rule; verify the unit, listener, and firewall rule are absent.
- Coordination impact: the service reads only the agent-1 checkout and does not touch agent-2. TCP 8765 becomes publicly reachable if the cloud security group also permits it. The test app is unauthenticated, unencrypted HTTP with in-memory messages only; do not send sensitive content.

## Entry template

### YYYY-MM-DD — short title

- State: planned | applied | rolled back
- Owner:
- Dedicated PR:
- Reason:
- Scope (exact paths/packages/services/settings):
- Source URL/version/SHA-256, if applicable:
- Planned actions:
- Actual actions:
- Verification and result:
- Rollback:
- Coordination impact:
