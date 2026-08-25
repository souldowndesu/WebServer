# Workspace Status

Update this file before handoff, pull-request merge, or the end of a work session.

## Agent 1

- State: ready
- Current task: none
- Branch: `agent-1`
- Last verification: 26 automated tests pass. Public `https://39.105.132.249/` presents a trusted Let’s Encrypt IP certificate and passes TLS 1.2/1.3, HTTP redirect, UI/health, HSTS/CSP/nosniff, same-/cross-origin, foreign-Host rejection and public-8790 isolation checks. Simulated renewal plus deploy hook succeeds; Nginx, account-control, Mihomo and the renewal timer are enabled/active; UFW is SSH+80+443; the origin remains `127.0.0.1:8790`; both account directories and the exact 267845-byte private data tree are unchanged.
- Pull requests: platform #21–#24, accepted UI #26, deployment registry #27, loopback deployment #28/#29, HTTPS hardening #31, environment plan #32, dependency amendment #33, and ACME correction #34 are merged; applied verification PR pending.
- Last handoff: the accepted base template is publicly reachable at `https://39.105.132.249/` with fixed-IP HTTPS and automatic short-lived certificate renewal. Credentialed browser testing is intentionally manual so the tester password never appears in commands or logs.
- Next action: operator tests normal login and interactions through the public URL; future work may refine the known UI/interaction defects without changing this deployment boundary.

## Agent 2

- State: ready (last observed)
- Current task: none recorded
- Last handoff: repository initialized

## Decisions pending

- None.
