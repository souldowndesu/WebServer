## Goal

Describe the coherent outcome this pull request should achieve.

## Changes

- List the material changes.

## Scope and coordination

- Assigned workspace/branch:
- Workspace lease session:
- Related task in `TASKS.md`:
- Conflicts or dependent PRs:
- [ ] Only the assigned workspace was edited.
- [ ] Shared rules are published through `main`, not copied manually into a sibling workspace.
- [ ] The workspace lease was held for material edits and will be released only after a clean handoff.

## Runtime isolation

- Development ports and runtime namespaces used:
- [ ] Tests used ephemeral ports, or assigned workspace ports were used through `tools/workspace_runtime.py`.
- [ ] No stable service reads an agent checkout; any deployment change is isolated in the environment workflow.

## Environment boundary

- [ ] No environment or outside-workspace change is included.
- [ ] Or: this is a dedicated documentation-only environment-change PR with a complete `ENVIRONMENT_CHANGES.md` entry.
- [ ] No secrets, private keys, tokens, or credential values are present.

## Verification

- Explain how the changes were checked.
- For transferred artifacts, include source, version, and matching local/server SHA-256.

## Review decision

- [ ] The diff and current open PRs were reviewed.
- [ ] Conflicts with current work were checked.
- [ ] The change is ready to merge.

## Handoff notes

Record unfinished work, risks, and the recommended next action.
