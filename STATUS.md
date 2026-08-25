# Workspace Status

Update this file before handoff, pull-request merge, or the end of a work session.

## Agent 1

- State: active
- Current task: public HTTPS access for the accepted account-platform template
- Branch: `agent-1`
- Last verification: user testing accepted the current interface as a temporary base template despite known polish defects; 25 automated tests, the earlier real 9-route/6-capture browser QA, Windows PowerShell 5.1 adapter QA, and live tester-account IrohaWalendar flow pass. The main-derived account-control.service is enabled/active with ExecMainStatus 0, initialized health and login page HTTP 200, admin proxy unauthenticated HTTP 401, exact UI hashes, private migrated data, only `127.0.0.1:8790` listening, no 18761 listener, unchanged SSH-only UFW, active Mihomo, and failed public 8790 connectivity
- Pull requests: product #26, deployment-port registry #27, environment plan #28, and applied verification #29 are merged
- Last handoff: the operator clarified that the accepted base template must be reachable from the public Internet, not only through SSH. The server has no domain, certificate, or existing 80/443 reverse proxy, so the chosen temporary test path is a random HTTPS Cloudflare Quick Tunnel while the origin remains loopback-only
- Next action: add Secure Cookie, HSTS and loopback-trusted Cloudflare client-address handling with regression tests; then separately plan/install the tunnel environment and verify public same-origin interactions without opening an inbound firewall port

## Agent 2

- State: ready (last observed)
- Current task: none recorded
- Last handoff: repository initialized

## Decisions pending

- None.
