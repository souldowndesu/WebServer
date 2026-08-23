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
