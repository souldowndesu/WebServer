# Shared Task Board

Update this file through pull requests. Each task needs an owner, branch, acceptance criteria, verification, and result.

## Backlog

| Task | Owner | Acceptance criteria |
| --- | --- | --- |

## In progress

| Task | Owner | Branch | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |
| Isolate two-agent development and deployment runtime | Agent 1 | `agent-1` | Atomic workspace lease; deterministic loopback preview ports; per-workspace runtime namespaces; updated AGENTS/skill/runbooks; tests; PR integration; main service no longer reads a development checkout | Implementing Git-level controls first |

## Completed

| Task | Owner | Pull request | Verification | Result |
| --- | --- | --- | --- | --- |
| Initialize shared two-agent repository | Shared | #1 | Branches and coordination files present | Complete |
| Establish server operations and governance | Agent 1 | #2 | SSH/status/Git/PR helpers; PowerShell parse; hash-matched upload; root rules and skill reviewed | Complete |
| Replace incompatible main ruleset | Agent 1 + repository owner | #3 | Ruleset `21255128` API verified: active, PR-only, deletion/force-push protected, discussions resolved, zero approvals, no bypass | Complete |
| Clock page, browser chat, and local input connectivity test | Agent 1 | #5, #6, #7 | Five automated tests; desktop/tablet/mobile visual checks; public health ok; Python CLI and local PowerShell tool public round trips succeeded | Complete |
| Local-only Mihomo proxy for agent-1 GitHub traffic | Agent 1 | #8 | Official binary/config validation; enabled active service; loopback-only listener; 40 usable nodes with AUTO/manual switching; mode switching restored to rule; proxied HTTP, ls-remote, and persisted fetch passed | Complete |
| Loopback-only Mihomo proxy control page | Agent 1 | #10, #11 | 13 tests; low-privilege enabled service; loopback-only 8790; allowlisted/same-origin API; 40 live nodes; mode and node switching restored; desktop/tablet/mobile SSH-tunnel QA; public port unreachable | Complete |
