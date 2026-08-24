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

- State: applied
- Owner: Agent 1
- Dedicated PR: #8
- Reason: use the operator-provided private subscription to improve unreliable server-to-GitHub HTTPS traffic while keeping proxy access local to the server.
- Scope (exact paths/packages/services/settings): create system user/group mihomo; install /usr/local/bin/mihomo; create /etc/mihomo/config.yaml, /var/lib/mihomo, /run/mihomo/controller.sock, and /etc/systemd/system/mihomo.service; enable mihomo.service; set only the agent-1 repository-local Git key http.https://github.com.proxy to http://127.0.0.1:7890. No UFW rule, TCP control port, global shell proxy, global Git proxy, credential helper, agent-2, or public proxy listener changes.
- Source URL/version/SHA-256, if applicable: official MetaCubeX/mihomo v1.19.30 compatible amd64 asset from https://github.com/MetaCubeX/mihomo/releases/download/v1.19.30/mihomo-linux-amd64-compatible-v1.19.30.gz; SHA-256 db214c7a2517e63c150d123178d16d102e03a241ccdae4e5e07ffbe9cf56c6f9 matched locally and at /root/ai-workspaces/agent-1/.cache/uploads/mihomo-linux-amd64-compatible-v1.19.30.gz.
- Planned actions:
  1. Accept the subscription through a no-echo interactive helper into a mode-0600 ignored staging configuration; never print, commit, or place the private URL in a command argument.
  2. Decompress and validate the staged official binary, then install it root-owned at mode 0755 to /usr/local/bin/mihomo.
  3. Generate a fixed rule-mode configuration that references the subscription only as a proxy provider, so subscription-provided top-level listeners, controllers, TUN, DNS, and routing settings are never imported.
  4. Force mixed-port 7890, allow-lan false, bind-address 127.0.0.1, no TCP controller, and a GitHub automatic latency-test group with a direct fallback for all non-GitHub traffic.
  5. Validate the generated configuration with Mihomo before installing it root:mihomo at mode 0640; delete the private staging configuration and validation artifacts after service verification.
  6. Create the unprivileged mihomo account, data directory, hardened systemd unit, and enable/start the service with an ephemeral Unix control socket at /run/mihomo/controller.sock for local mode and node management.
  7. Verify local-only listeners, Unix-socket control, provider/node discovery, automatic node selection, and proxy egress; then test GitHub access through a one-command temporary Git proxy setting before persisting the repository-local GitHub-only proxy key.
- Planned service: runs as the non-login mihomo user without TUN capabilities; writes only to /var/lib/mihomo and its systemd-created /run/mihomo runtime directory; listens only on 127.0.0.1:7890; exposes control only through /run/mihomo/controller.sock and no TCP control port; uses NoNewPrivileges, private devices/tmp, strict filesystem protection, restricted address families, a 256 MB memory ceiling, and a 128-task ceiling.
- Actual actions: downloaded the official v1.19.30 compatible amd64 asset locally, matched its compressed SHA-256 locally and in ignored server staging, decompressed it there, confirmed the expected version/architecture, and installed the root-owned binary at /usr/local/bin/mihomo. Created the non-login mihomo system account, /etc/mihomo and /var/lib/mihomo with restricted ownership/modes, and a hardened systemd unit. The operator entered the subscription through the no-echo helper; the helper generated a fixed rule configuration that uses the private URL only as a provider and never imports subscription top-level settings. Validated the configuration without printing it and installed it at /etc/mihomo/config.yaml as root:mihomo mode 0640. Enabled and started mihomo.service; added a systemd-created /run/mihomo runtime directory and Unix control socket; added a GITHUB selector whose default AUTO child performs latency testing while retaining manual node selection. Set only agent-1's repository-local http.https://github.com.proxy key. Safely overwrote and removed the two private staging configurations and validation artifacts after verification; retained only the no-secret helper for future protected subscription replacement.
- Verification and result: /usr/local/bin/mihomo reports Meta v1.19.30 linux amd64; its SHA-256 8ad44e28fe72be4640254b96741b677f4074991b99186cc4486a1c28ded02b1a matched the decompressed staged binary. Configuration validation exited 0. systemd reports enabled, active/running, ExecMainStatus 0, MemoryMax 256 MiB, and TasksMax 128. The only proxy TCP listener is 127.0.0.1:7890; control is available only through /run/mihomo/controller.sock inside a mode-0750 runtime directory; no TCP control port or new UFW rule exists. The provider loaded approximately 43 entries, exposed 40 usable node options, and the GITHUB selector exposed AUTO plus all 40 nodes. Direct mode and manual node selection were each applied successfully and then restored to rule mode and AUTO. Proxied GitHub HTTPS returned HTTP 200 in 0.577 seconds. A temporary-proxy git ls-remote returned four heads in 0.928 seconds, and a normal git fetch using the persisted repository-local key completed in 0.961 seconds with no stderr. All identified private staging copies and validation artifacts were confirmed within agent-1/.cache/uploads and then removed.
- Rollback: unset only the agent-1 http.https://github.com.proxy key; disable and stop mihomo.service; remove only /etc/systemd/system/mihomo.service and /usr/local/bin/mihomo; daemon-reload; confirm /etc/mihomo, /var/lib/mihomo, and /run/mihomo resolve to those exact paths before removing their contents/directories; remove the mihomo system account/group; verify no 7890 listener, control socket, or secret staging files remain.
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
