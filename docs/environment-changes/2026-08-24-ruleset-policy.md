# GitHub Main Ruleset Policy Change

- State: planned
- Date: 2026-08-24
- Owner: Agent 1
- Dedicated branch: `agent-1-ruleset-policy`
- Dedicated PR: pending
- Repository: `souldowndesu/agent`
- Ruleset: `21239285` (`Protect main - two AI review`)

## Reason

The repository has one authenticated GitHub account for both server workspaces. The active ruleset requires one approval from someone other than the last pusher and has no bypass actor. GitHub therefore rejects both self-approval and administrator merge, making every PR impossible to merge even after the repository owner authorizes and verifies it.

The operational policy requires versioned PR coordination, but explicitly permits the repository owner/agent to verify and merge completed work. The enforcement settings must match that available identity model.

## Exact scope

Change only the `pull_request` rule parameters in repository ruleset `21239285`:

- `required_approving_review_count`: `1` to `0`.
- `require_last_push_approval`: `true` to `false`.

Preserve:

- active enforcement on the default branch;
- PR-only integration;
- deletion protection;
- non-fast-forward protection;
- stale-review dismissal setting;
- required review-thread resolution;
- allowed merge methods;
- all other rule parameters.

No server package, service, credential, or file outside the Git workspaces is changed.

## Planned actions

1. Publish this dedicated record as its own PR.
2. Save and inspect the current ruleset response.
3. Update the two incompatible approval parameters through the GitHub rulesets API.
4. Confirm the ruleset remains active and all preserved protections remain present.
5. Merge the verified operations PR and this policy-record PR.
6. Record final API state and merge results in the PR conversation.

## Verification

- The ruleset API must report `required_approving_review_count: 0` and `require_last_push_approval: false`.
- PR #2 must become mergeable without a second account.
- The ruleset must still report active enforcement, deletion protection, non-fast-forward protection, a pull-request rule, and required review-thread resolution.

## Rollback

Update ruleset `21239285` with the preserved configuration and restore:

- `required_approving_review_count: 1`;
- `require_last_push_approval: true`.

Rollback restores the previous enforcement behavior, which will again require a distinct second GitHub account for every merge.

## Coordination impact

GitHub will no longer enforce an independent account approval. Agents must still inspect the diff, verification, open PRs, and conflicts before merge, and must record that review in the PR body or conversation. Every coherent change continues to require a PR into `main`.
