# Shared Task Board

Update this file through pull requests. Each task needs an owner, branch, acceptance criteria, verification, and result.

## Backlog

| Task | Owner | Acceptance criteria |
| --- | --- | --- |

## In progress

| Task | Owner | Branch | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |

## Completed

| Task | Owner | Pull request | Verification | Result |
| --- | --- | --- | --- | --- |
| Interactive account-platform UI and temporary single-area deployment | Agent 1 | #26, #27, #28, #29 | User acceptance; 25 tests; real 9-route/6-capture browser QA; Windows adapter and tester-account sync; exact main/UI/data migration checks; hardened low-privilege systemd state; local/public connectivity and unchanged UFW/Mihomo | Complete — accepted base template runs from main-derived `/opt/account-control` on loopback 8790 with preserved private data in `/var/lib/account-control`; accessible only through SSH tunnel; agent-1 preview stopped and 18761 returned; final visual/interaction polish and public HTTPS remain future work |
| Authenticated multi-user management platform | Agent 1 | #21, #22, #23, #24 | 24 tests; workspace doctor; real HTTP health/root smoke; 6 local-only responsive captures without overflow/browser errors; public/local legacy-port closure; unchanged Mihomo health | Complete — account-isolated backend and handoff contract merged; old source, in-memory chat data, services, users, paths, firewall rule, and runtime registrations retired; formal UI and HTTPS deployment remain gated |
| Initialize shared two-agent repository | Shared | #1 | Branches and coordination files present | Complete |
| Establish server operations and governance | Agent 1 | #2 | SSH/status/Git/PR helpers; PowerShell parse; hash-matched upload; root rules and skill reviewed | Complete |
| Replace incompatible main ruleset | Agent 1 + repository owner | #3 | Ruleset `21255128` API verified: active, PR-only, deletion/force-push protected, discussions resolved, zero approvals, no bypass | Complete |
| Clock page, browser chat, and local input connectivity test | Agent 1 | #5, #6, #7 | Five automated tests; desktop/tablet/mobile visual checks; public health ok; Python CLI and local PowerShell tool public round trips succeeded | Historical — retired by #21–#24 |
| Local-only Mihomo proxy for agent-1 GitHub traffic | Agent 1 | #8 | Official binary/config validation; enabled active service; loopback-only listener; 40 usable nodes with AUTO/manual switching; mode switching restored to rule; proxied HTTP, ls-remote, and persisted fetch passed | Complete |
| Loopback-only Mihomo proxy control page | Agent 1 | #10, #11 | 13 tests; low-privilege enabled service; loopback-only 8790; allowlisted/same-origin API; 40 live nodes; mode and node switching restored; desktop/tablet/mobile SSH-tunnel QA; public port unreachable | Historical — standalone page retired by #21–#24; allowlist moved into control plane |
| Isolate two-agent development and deployment runtime | Agent 1 | #13, #14, #15, #16, #17, #18, #19 | 25 tests; atomic lease and duplicate rejection; deterministic loopback ports; SSH-disconnect process cleanup; canonical direct/local-relay Git pushes; main-derived low-privilege services; internal/public health and unchanged UFW | Complete — each agent has an isolated development namespace and stable services read neither checkout |
