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

### 2026-08-24 — Loopback-only Mihomo proxy control web service

- State: applied
- Owner: Agent 1
- Dedicated PR: #11
- Reason: run the merged proxy control dashboard as a restartable, low-privilege service that the operator can reach through an authenticated SSH tunnel without exposing control access to the public network.
- Scope (exact paths/packages/services/settings): create system user/group proxy-control and add that user to the existing mihomo supplementary group; create /opt/proxy-control containing the merged `proxy_control` package; create /etc/systemd/system/proxy-control.service; enable and start proxy-control.service on 127.0.0.1:8790. No package installation, UFW rule, cloud firewall change, public listener, Mihomo TCP controller, credential, profile, agent-2, or global proxy setting change.
- Source URL/version/SHA-256, if applicable: no external artifact; application source is repository main merge commit a7907104e0990a8b03abd4d0f551ced1d1bd0fc4.
- Planned actions:
  1. Stage the systemd unit only under /root/ai-workspaces/agent-1/.cache/uploads/proxy-control.service and validate it with systemd-analyze verify.
  2. Confirm TCP 8790, the proxy-control account, /opt/proxy-control, and proxy-control.service are absent before creating them.
  3. Create the non-login proxy-control system account/group, add only that account to the existing mihomo group, and verify no other group membership changes.
  4. Install the merged proxy_control package root-owned and read-only under /opt/proxy-control; do not copy repository metadata, tests, private subscription data, or credentials.
  5. Install the validated unit, reload systemd, and enable/start proxy-control.service.
  6. Verify enabled/active state, the exact 127.0.0.1:8790 listener, successful access to /run/mihomo/controller.sock through the supplementary group, allowlisted status output, same-origin mutation protection, absence of a public/UFW change, and a real browser session through an SSH local port forward.
- Planned service: runs `/usr/bin/python3 -m proxy_control.server --host 127.0.0.1 --port 8790 --socket /run/mihomo/controller.sock` as the non-login proxy-control user with the existing mihomo group supplementary access; reads only /opt/proxy-control and the Mihomo Unix socket; writes nowhere; uses NoNewPrivileges, private devices/tmp, strict filesystem/home/kernel protection, loopback-only IP allow rules, restricted AF_INET/AF_UNIX families, a 96 MiB memory ceiling, and a 64-task ceiling.
- Actual actions: confirmed the proxy-control account/group, /opt/proxy-control, unit file, and listener were absent after stopping the exact temporary browser-QA process. Staged proxy-control.service with SHA-256 a8b8c3e3689fac6e571c3a2f3022b7f7d719dd701380feb38c89bca066049861; systemd-analyze accepted it with exit 0 and only unrelated pre-existing unit warnings. Created uid/gid 997 proxy-control as a non-login system account with only group 998 mihomo as supplementary access. Created /opt/proxy-control and installed exactly five root:root mode-0644 product files from main merge commit a790710; all five deployed/source SHA-256 values matched. Installed the hash-matched unit at /etc/systemd/system/proxy-control.service, reloaded systemd, and enabled/started proxy-control.service. Used a temporary SSH local port forward for final browser QA, then closed the test tunnel.
- Verification and result: systemd reports proxy-control.service enabled, active/running, ExecMainStatus 0, MainPID 63033, MemoryMax 96 MiB, and TasksMax 64; the process runs as proxy-control and listens only on 127.0.0.1:8790. The deployed status API returned HTTP 200, online, rule mode, AUTO selection, and 40 nodes; recursively checked response keys exclude server, port, password, secret, subscriptionInfo, and URL fields. A non-loopback Host received HTTP 400, a cross-origin mode POST received HTTP 403, and a same-origin rule POST received HTTP 200. Through an SSH tunnel, desktop 1440×900, tablet 820×900, and mobile 390×844 browser runs each loaded all 40 nodes, had no horizontal overflow, console error, or failed request; real direct/rule and manual/AUTO interactions restored `rule + AUTO`. A request to the public server address on TCP 8790 failed, and UFW still lists only 22/tcp and 8765/tcp rules. mihomo.service, connectivity-chat.service, and proxy-control.service all remained active; chat health returned ok and proxied GitHub HTTPS returned HTTP 200.
- Rollback: disable and stop only proxy-control.service; remove only /etc/systemd/system/proxy-control.service; daemon-reload; confirm /opt/proxy-control resolves to that exact path before removing it; remove only the proxy-control system account/group and its mihomo supplementary membership; verify no 8790 listener remains. No Mihomo configuration, subscription, Git proxy, UFW, chat service, or agent-2 rollback is required.
- Coordination impact: the service reads a deployed copy of the main-merged product and does not read either Git workspace at runtime. Agent-2 and public network behavior remain unchanged. Operators access the page with `ssh -N -L 8790:127.0.0.1:8790 aliyun-server` and browse to `http://127.0.0.1:8790`.

### 2026-08-24 — Restricted Git credential path migration to WebServer

- State: applied
- Owner: Agent 1
- Dedicated PR: #15 (plan); #16 (applied verification)
- Reason: the repository was renamed to `souldowndesu/WebServer`; the existing least-privilege credential helper still authorizes only the old redirected `souldowndesu/agent` path, causing direct pushes to the canonical URL to fail. The operator explicitly authorized the new Git path to simplify pushes.
- Scope (exact paths/packages/services/settings): replace only the repository path allowlist in `/root/.local/bin/agent-git-credential` from `souldowndesu/agent` and `souldowndesu/agent.git` to `souldowndesu/WebServer` and `souldowndesu/WebServer.git`; preserve root:root mode 0755, HTTPS-only protocol, github.com-only host, get-only operation, token-file location/content/permissions, output format, and all other logic. Change only agent-1's repository-local `origin` URL to `https://github.com/souldowndesu/WebServer.git`. No token rotation/readout, global Git config, package, service, firewall, profile, proxy, GitHub permission, agent-2 checkout, or product-file change.
- Source URL/version/SHA-256, if applicable: no external artifact. Existing `/root/.local/bin/agent-git-credential` SHA-256 is `b125f86291815aba32c4559eac77132c3ea03352598ce8bd91167df6fd70b1b0`, size 586 bytes, root:root mode 0755. The planned replacement is derived from that exact file with only the two repository path strings changed.
- Planned actions:
  1. Reconfirm the helper hash/mode/owner, agent-1 origin, clean leased worktree, and that the helper path allowlist still contains only the old repository path.
  2. Copy the exact current helper into ignored agent-1 staging for rollback, record its SHA-256, and create a replacement in ignored staging by changing only the two path allowlist strings; never copy, print, modify, or hash-report the token value.
  3. Verify a diff between staged old/new helpers contains only the path replacement; run `bash -n`; verify the replacement contains github.com plus only the new WebServer path and retains mode 0755 when installed.
  4. Install the staged replacement atomically at `/root/.local/bin/agent-git-credential` as root:root mode 0755, then set only agent-1's `origin` to `https://github.com/souldowndesu/WebServer.git`.
  5. With terminal prompting disabled, verify canonical `git fetch`, `git ls-remote`, and a no-change/dry-run push succeed; perform a normal agent-1 push if required to verify the actual path.
  6. Use a redacted probe that reports only `username=<present>` and `password=<present>` field names to verify the new WebServer path receives credentials, while the old agent path and an unrelated repository path receive no credential fields. Never print credential values.
- Planned service: not applicable; no service is created or restarted.
- Actual actions: generated the replacement and a key-name-only probe on the local control machine, then uploaded them to ignored agent-1 staging with SHA-256 `41bcfbccbe802d8c38ac60e51cddfb59d7b2a61d8ce4632f3fe18fa28f9f6977` and `f24f729ec63a66e44b433b1fb42189f0aa99a489dd7415395bb5db91e69ea085`. Reconfirmed the installed helper's original hash/mode/owner and the active clean workspace lease; `bash -n` accepted both staged scripts. A unified diff showed exactly one change: replacing the old two-path case arm with the new two-path WebServer case arm. Set staged scripts root-only executable for testing; the redacted probe reported username/password fields for the new path and no fields for the old or unrelated path. Copied the exact original helper with preserved metadata to `/root/ai-workspaces/agent-1/.cache/uploads/git-path-migration/agent-git-credential.before`; its SHA-256 matched the installed original. Installed the staged replacement as root:root mode 0755 at `/root/.local/bin/agent-git-credential`, then changed only agent-1 origin to `https://github.com/souldowndesu/WebServer.git`. The token file was not printed, copied, modified, or included in hashes or logs.
- Verification and result: the installed helper is root:root mode 0755, size 594 bytes, passes `bash -n`, and has SHA-256 `41bcfbccbe802d8c38ac60e51cddfb59d7b2a61d8ce4632f3fe18fa28f9f6977`, matching staged replacement. The redacted installed-helper probe returned exactly `username=<present>` and `password=<present>` for `souldowndesu/WebServer.git`, and no credential fields for `souldowndesu/agent.git` or `souldowndesu/unrelated.git`. With `GIT_TERMINAL_PROMPT=0`, canonical origin fetch completed without output/error, `ls-remote --heads` returned agent-1, agent-1-ruleset-policy, agent-2, and main, and both dry-run and normal agent-1 pushes reported everything up-to-date. Agent-1 origin reports exactly `https://github.com/souldowndesu/WebServer.git`.
- Rollback: reinstall the hash-matched original helper from ignored agent-1 staging as root:root mode 0755; restore only agent-1 origin to `https://github.com/souldowndesu/agent.git`; verify old-path fetch/push works and canonical direct access is again refused by the helper. No token, service, package, firewall, product, proxy, UFW, or agent-2 rollback is required.
- Coordination impact: agent-1 now pushes directly through the canonical URL. The checked-in local relay still needs a normal follow-up PR to replace its old compatibility URL; until that merges, prefer direct server pushes. Agent-2 was not edited by this operator; after shared instructions merge, its owner must independently verify a clean checkout and change its own origin. The credential remains restricted to one GitHub host and one repository, only under its new canonical path.

### 2026-08-24 — Main-derived connectivity chat deployment

- State: applied
- Owner: Agent 1
- Dedicated PR: #18 (plan); #19 (applied verification)
- Reason: remove the remaining stable-service dependency on the mutable agent-1 checkout so agent-1 and agent-2 can rebase, edit, and preview independently without changing what connectivity-chat.service will execute on restart.
- Scope (exact paths/packages/services/settings): create a non-login connectivity-chat system user/group; create `/opt/connectivity-chat` containing exactly the reviewed main `chat_app` package; replace `/etc/systemd/system/connectivity-chat.service` so it runs as connectivity-chat from `/opt/connectivity-chat`; reload systemd and restart only connectivity-chat.service. Preserve TCP 8765, its existing UFW rules, public bind, memory/task limits, and all unrelated services. No package, credential, profile, global proxy, agent-2, cloud firewall, database, or Mihomo change.
- Source URL/version/SHA-256, if applicable: no external artifact; planned application source is repository main commit `62aba332b7220fbb38b972ca80cac519dfd708f0`. Baseline source SHA-256 values are `3dbe8613599ff0ae09b3551575270114d62c3bf161cca507553abb469af17430` for `chat_app/__init__.py`, `ab63078bbb6aa82a4675bc18fb72cbbeb71ea1e8f67773a1c1b7fdcb644d1ad0` for `chat_app/server.py`, and `d94b7e12ff7b293680be867ba3dc25de647f591704e9b940b3cc69b523ed878f` for `chat_app/static/index.html`.
- Planned actions:
  1. Capture the exact current unit in ignored agent-1 staging and record its SHA-256 for rollback; confirm it still runs as root from `/root/ai-workspaces/agent-1` before replacement.
  2. Reconfirm the connectivity-chat account/group and `/opt/connectivity-chat` are absent, the agent-1 worktree is clean/leased, and source commit/hashes still match reviewed main.
  3. Stage the replacement unit under `/root/ai-workspaces/agent-1/.cache/uploads`, verify its SHA-256, and validate it with `systemd-analyze verify` before installation.
  4. Create the non-login connectivity-chat system account/group without supplementary groups or a writable home.
  5. Create `/opt/connectivity-chat` and install exactly the three `chat_app` product files from reviewed main as root:root, directories mode 0755 and files mode 0644; do not copy Git metadata, tests, runtime leases, uploads, credentials, or environment files.
  6. Stop only connectivity-chat.service, install the validated unit at mode 0644, run `systemctl daemon-reload`, and start/enable only connectivity-chat.service.
  7. Verify deployed/source hashes, root-owned read-only product files, the exact service account and working directory, enabled/active state, ExecMainStatus 0, 0.0.0.0:8765 listener, local/public health, unchanged UFW rules, and continued health of mihomo.service and proxy-control.service.
- Planned service: runs `/usr/bin/python3 -m chat_app.server --host 0.0.0.0 --port 8765` as the non-login connectivity-chat user/group from `/opt/connectivity-chat`; disables bytecode writes; retains restart-on-failure, NoNewPrivileges, private devices/tmp, strict filesystem/home/kernel/control-group protection, restricted address families, the 128 MiB memory ceiling, and the 64-task ceiling. The service has no writable application directory.
- Actual actions: reconfirmed a clean leased agent-1 worktree, matching reviewed source hashes, the original root/agent-1 unit state, and absent target account/group/path. Copied the exact original unit with preserved metadata to ignored rollback staging as root:root mode 0644; its SHA-256 `d026c684c09dbf7da19855cc0028d71111cd71f1d01df47c5040bcee47f1dffc` matched the installed original. Uploaded the replacement unit with matching local/server SHA-256 `e9fc36465d517a80792cdbd49f6c40ad753b947e67708669acee0f6ea2176f43`; `systemd-analyze verify` exited 0 with only unrelated pre-existing snapd/cloudmonitor warnings. Created uid 996/gid 999 connectivity-chat as a non-login system account with no supplementary groups or writable home. Created `/opt/connectivity-chat` and installed exactly the three planned application files root:root with directories mode 0755 and files mode 0644. Stopped only connectivity-chat.service, installed the validated unit, reloaded systemd, and enabled/started that service. No UFW, package, credential, profile, proxy, Mihomo, proxy-control, agent-2, or cloud firewall setting changed. The authorized test/in-memory messages were discarded by the restart.
- Verification and result: all three deployed/source SHA-256 pairs match the planned values and `/opt/connectivity-chat` contains exactly the three planned root-owned read-only files. The installed/staged unit hashes match. systemd reports connectivity-chat.service enabled and active/running with ExecMainStatus 0, User/Group connectivity-chat, WorkingDirectory `/opt/connectivity-chat`, MemoryMax 128 MiB, and TasksMax 64; Python listens exactly on 0.0.0.0:8765. Local and operator-machine public health both returned status ok with zero in-memory messages, and the message list was empty. UFW remained active with exactly its existing 22/tcp and connectivity-chat 8765/tcp IPv4/IPv6 rules. mihomo.service and proxy-control.service remained active; proxy-control returned HTTP 200 and GitHub through Mihomo returned HTTP 200.
- Rollback: stop only connectivity-chat.service; reinstall the hash-recorded original unit from ignored agent-1 staging; run daemon-reload and restart/enable connectivity-chat.service; verify root plus WorkingDirectory `/root/ai-workspaces/agent-1`, port 8765, and health are restored. Confirm `/opt/connectivity-chat` resolves to that exact path before removing it, then remove only the connectivity-chat system account/group. No UFW, Mihomo, proxy-control, agent-2, package, or credential rollback is required.
- Coordination impact: the service restart causes brief TCP 8765 downtime and clears its in-memory test messages. After migration, neither agent checkout is read at runtime; both agents may rebase/edit independently, while future stable deployment updates remain serialized environment changes sourced from reviewed main commits.

### 2026-08-24 — Retire legacy connectivity chat and standalone proxy-control services

- State: planned
- Owner: Agent 1
- Dedicated PR: pending
- Reason: product PR #21 replaced the public clock/anonymous chat surface with an authenticated account control-plane backend and moved the Mihomo allowlist adapter into that backend. The two old deployed web services must stop serving obsolete unauthenticated or standalone interfaces, and the chat listener's in-memory test data must be discarded.
- Scope (exact paths/packages/services/settings): disable and stop only `connectivity-chat.service` and `proxy-control.service`; remove only `/etc/systemd/system/connectivity-chat.service`, `/etc/systemd/system/proxy-control.service`, `/opt/connectivity-chat`, and `/opt/proxy-control`; remove only the `connectivity-chat` and `proxy-control` system users/groups; remove only the UFW `8765/tcp` rule and its IPv6 companion carrying the `connectivity-chat` comment. Preserve `mihomo.service`, `/usr/local/bin/mihomo`, `/etc/mihomo`, `/var/lib/mihomo`, `/run/mihomo`, the `mihomo` account/group, loopback TCP 7890, SSH/UFW 22, Git settings, packages, credentials, agent-2, and all other services.
- Source URL/version/SHA-256, if applicable: no external artifact. Replacement source is reviewed main merge commit `b6ac805cd76c94ff8a4177e8ee05f2a646be7309` from PR #21. Current unit SHA-256 values are `e9fc36465d517a80792cdbd49f6c40ad753b947e67708669acee0f6ea2176f43` for connectivity-chat and `a8b8c3e3689fac6e571c3a2f3022b7f7d719dd701380feb38c89bca066049861` for proxy-control; deployed application hashes remain those recorded by their original change entries.
- Planned actions:
  1. Reconfirm both exact units, listeners, UFW rules, service accounts, deployment-directory realpaths, hashes, active workspace lease, and clean agent-1 worktree. Refuse the change if any target resolves outside the exact paths above.
  2. Copy the two units and two deployment directories with preserved metadata into ignored `/root/ai-workspaces/agent-1/.cache/uploads/legacy-service-retirement/`, then verify the recorded hashes so rollback does not depend on source removed from current main.
  3. Run `systemctl disable --now connectivity-chat.service proxy-control.service`; verify TCP 8765 and 8790 have no listeners before removing files.
  4. Run `ufw --force delete allow 8765/tcp`; verify both the IPv4 and IPv6 `connectivity-chat` rules are absent while SSH 22 rules remain.
  5. After exact `readlink -f`/`realpath` checks, remove only the two unit files and exact `/opt/connectivity-chat` and `/opt/proxy-control` trees; run `systemctl daemon-reload` and `systemctl reset-failed` for only the retired units.
  6. Remove only the `connectivity-chat` and `proxy-control` system users, their same-named primary groups, and the proxy-control supplementary membership from `mihomo`; do not alter the Mihomo account/group itself.
  7. Verify both units are not found/disabled, both ports refuse connections locally and externally as applicable, UFW contains only the preserved rules, legacy paths/accounts are absent, `mihomo.service` stays healthy on loopback 7890, GitHub proxy egress still works, and no agent workspace or product data changed.
- Actual actions: not yet applied.
- Verification and result: pending. Baseline immediately before the plan showed both units enabled/active, Python listening on `0.0.0.0:8765` and `127.0.0.1:8790`, UFW rules for connectivity-chat on IPv4/IPv6, exact non-login service accounts, 44 KiB under `/opt/connectivity-chat`, 72 KiB under `/opt/proxy-control`, and no persistent `/var/lib` data for either service. Chat history is process memory only, so stopping the service is the related-data cleanup.
- Rollback: recreate the two non-login system users/groups (including only proxy-control membership in `mihomo`), restore the hash-matched deployment trees and units from ignored rollback staging with their original ownership/modes, run daemon-reload, re-add `ufw allow 8765/tcp comment 'connectivity-chat'`, enable/start both services, and verify their original binds and health. Do not roll back or replace Mihomo configuration, credentials, packages, Git settings, agent workspaces, or the merged product source.
- Coordination impact: TCP 8765 becomes intentionally unreachable and existing anonymous in-memory messages are irrecoverably cleared. The SSH-tunneled standalone proxy page on 8790 also disappears; Mihomo itself and GitHub proxy traffic continue. The new authenticated backend remains development-only until a separate HTTPS deployment and no-echo initial-admin bootstrap are explicitly authorized and recorded.

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
