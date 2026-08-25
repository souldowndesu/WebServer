# Workspace Status

Update this file before handoff, pull-request merge, or the end of a work session.

## Agent 1

- State: active
- Current task: promote the accepted account-platform template into the main-derived single deployment area
- Branch: `agent-1`
- Last verification: user testing accepted the current interface as a temporary base template despite known polish defects; 25 automated tests pass after promotion, the three versioned UI assets are byte-identical to the browser-tested runtime assets, and the earlier 9-route/6-capture browser QA, Windows PowerShell 5.1 adapter QA, and live tester-account IrohaWalendar flow remain valid; legacy services remain inactive and only the registered `127.0.0.1:18761` workspace preview listens
- Pull requests: #21–#24 are merged; product PR #26 contains the backend, tests, sync adapter, handoff documentation, and the accepted deployable base UI template
- Last handoff: the operator accepted the current implementation for temporary deployment; the UI baseline is now reviewable under `control_plane/ui`, while final interaction and visual refinement remain explicitly deferred
- Next action: merge product PR #26, use a dedicated environment-change PR to install a main-derived loopback service in the single deployment area, verify it through an SSH tunnel, then stop the workspace preview and release its lease/registered port

## Agent 2

- State: ready (last observed)
- Current task: none recorded
- Last handoff: repository initialized

## Decisions pending

- None.
