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
| Public HTTPS access for accepted account-platform template | Agent 1 | #31, #32, #33, #34, #35 | 26 tests; signed/pinned artifacts; staging and production IP issuance; Certbot dry-run + deploy hook; public TLS 1.2/1.3, redirect, headers, origin/Host, health/auth and port isolation; exact service/config/data checks | Complete — trusted `https://39.105.132.249/` fronts loopback 8790 through Nginx; automatic short-lived renewal is active; Secure cookies/HSTS and real-client throttling are enabled; UFW adds only 80/443; both accounts and all data are preserved |
| Interactive account-platform UI and loopback deployment | Agent 1 | #26, #27, #28, #29 | User acceptance; 25 tests; 9-route/6-capture browser QA; Windows adapter and tester-account sync; exact main/UI/data migration checks; hardened service and local/public isolation | Complete — accepted base template deployed from reviewed main under `/opt/account-control`, with private data in `/var/lib/account-control` and origin on loopback 8790 |
| Authenticated multi-user management platform | Agent 1 | #21, #22, #23, #24 | 24 tests; account/data isolation; admin account pool and proxy; planner sync; connections/messages; quotas; reviewed blogs; inference queue; legacy service/data retirement | Complete — old clock, anonymous chat and standalone proxy page retired; authenticated account-isolated backend and handoff contract merged |
| Isolate two-agent development and deployment runtime | Agent 1 | #13–#19 | 25 tests; atomic leases; deterministic loopback ports; disconnect cleanup; restricted Git credentials; main-derived low-privilege services | Complete — workspaces have isolated namespaces and stable services read neither mutable checkout |
| Loopback-only Mihomo proxy control page | Agent 1 | #10, #11 | 13 tests; low-privilege loopback service; allowlisted/same-origin API; live node switching; responsive SSH-tunnel QA | Historical — standalone page retired by #21–#24; its allowlist moved into the account control plane |
| Local-only Mihomo proxy for GitHub traffic | Agent 1 | #8 | Official artifact/config validation; enabled active service; loopback-only listener; AUTO/manual switching; proxied GitHub HTTP and Git operations | Complete |
| Clock page, browser chat, and local input connectivity test | Agent 1 | #5, #6, #7 | Five tests; responsive visual checks; public health and message round trips | Historical — retired by the authenticated platform |
| Establish server operations and governance | Agent 1 | #2 | SSH/status/Git/PR helpers; local-first hash transfer; workspace rules and environment ledger | Complete |
| Initialize shared two-agent repository | Shared | #1 | Branches and coordination files present | Complete |
