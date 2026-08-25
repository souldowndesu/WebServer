# Workspace Status

Update this file before handoff, pull-request merge, or the end of a work session.

## Agent 1

- State: ready
- Current task: none
- Branch: `agent-1`
- Last verification: user testing accepted the current interface as a temporary base template despite known polish defects; 25 automated tests, the earlier real 9-route/6-capture browser QA, Windows PowerShell 5.1 adapter QA, and live tester-account IrohaWalendar flow pass. The main-derived account-control.service is enabled/active with ExecMainStatus 0, initialized health and login page HTTP 200, admin proxy unauthenticated HTTP 401, exact UI hashes, private migrated data, only `127.0.0.1:8790` listening, no 18761 listener, unchanged SSH-only UFW, active Mihomo, and failed public 8790 connectivity
- Pull requests: product #26, deployment-port registry #27, environment plan #28, and applied verification #29 are merged
- Last handoff: the accepted base template runs from root-owned `/opt/account-control`; the preserved two-account data runs from private `/var/lib/account-control`; operators access it only through `ssh -N -L 8790:127.0.0.1:8790 aliyun-server`. The workspace preview is stopped and its lease/18761 port is returned in the final release step
- Next action: future work may refine or replace `control_plane/ui` using `docs/frontend-handoff.md`; public multi-user access remains gated on a separate HTTPS reverse-proxy deployment with Secure Cookie

## Agent 2

- State: ready (last observed)
- Current task: none recorded
- Last handoff: repository initialized

## Decisions pending

- None.
