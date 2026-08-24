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

### 2026-08-24 — Local-only Mihomo proxy for GitHub traffic

- State: planned
- Owner: Agent 1
- Dedicated PR: #8
- Reason: use the operator-provided private subscription to improve unreliable server-to-GitHub HTTPS traffic while keeping proxy access local to the server.
- Scope (exact paths/packages/services/settings): create system user/group mihomo; install /usr/local/bin/mihomo; create /etc/mihomo/config.yaml, /var/lib/mihomo, and /etc/systemd/system/mihomo.service; enable mihomo.service; set only the agent-1 repository-local Git key http.https://github.com.proxy to http://127.0.0.1:7890. No UFW rule, global shell proxy, global Git proxy, credential helper, agent-2, or public proxy listener changes.
- Source URL/version/SHA-256, if applicable: official MetaCubeX/mihomo v1.19.30 compatible amd64 asset from https://github.com/MetaCubeX/mihomo/releases/download/v1.19.30/mihomo-linux-amd64-compatible-v1.19.30.gz; SHA-256 db214c7a2517e63c150d123178d16d102e03a241ccdae4e5e07ffbe9cf56c6f9 matched locally and at /root/ai-workspaces/agent-1/.cache/uploads/mihomo-linux-amd64-compatible-v1.19.30.gz.
- Planned actions:
  1. Accept the subscription through a no-echo interactive helper into a mode-0600 ignored staging file; never print, commit, or place the private URL in a command argument.
  2. Decompress and validate the staged official binary, then install it root-owned at mode 0755 to /usr/local/bin/mihomo.
  3. Fetch the subscription through a curl config file so the URL is absent from process arguments; store raw data only in ignored staging.
  4. Remove any subscription-provided public listeners, controller, authentication, TUN, and DNS listener settings; force mixed-port 7890, allow-lan false, bind-address 127.0.0.1, no external controller, TUN disabled, and DNS listener disabled.
  5. Validate the sanitized configuration with Mihomo before installing it at mode 0600; delete the private URL intake and raw subscription staging files.
  6. Create the unprivileged mihomo account, data directory, hardened systemd unit, and enable/start the service.
  7. Verify local-only listeners and proxy egress, then test GitHub access through a one-command temporary Git proxy setting before persisting the repository-local GitHub-only proxy key.
- Planned service: runs as the non-login mihomo user without TUN capabilities; writes only to /var/lib/mihomo; listens only on 127.0.0.1:7890; uses NoNewPrivileges, private devices/tmp, strict filesystem protection, restricted address families, a 256 MB memory ceiling, and a 128-task ceiling.
- Actual actions: pending.
- Verification and result: pending. Planned checks are binary version/hash, configuration validation without printing secrets, systemd enabled/active state, exact 127.0.0.1:7890 listener, absence of public proxy/firewall changes, proxied HTTPS egress, GitHub ls-remote through the proxy, and a normal Git fetch using the persisted repository-local key.
- Rollback: unset only the agent-1 http.https://github.com.proxy key; disable and stop mihomo.service; remove only /etc/systemd/system/mihomo.service and /usr/local/bin/mihomo; daemon-reload; remove /etc/mihomo and /var/lib/mihomo after confirming their resolved exact paths; remove the mihomo system account/group; verify no 7890 listener and no secret staging files remain.
- Coordination impact: agent-2 and global network behavior remain unchanged. The subscription and generated proxy credentials are confidential, root/mihomo readable only, and excluded from Git, PRs, logs, status mirrors, and chat output.

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
