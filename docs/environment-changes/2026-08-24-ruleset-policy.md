# GitHub Main Ruleset Replacement

- State: planned — API creation blocked by token permission
- Date: 2026-08-24
- Owner: Agent 1
- Dedicated branch: `agent-1-ruleset-policy`
- Dedicated PR: pending
- Repository: `souldowndesu/agent`
- Previous ruleset: `21239285` (`Protect main - two AI review`), disabled by the repository owner and scheduled for deletion
- Replacement ruleset: `Protect main - PR coordination` (ID pending creation)

## Reason

The repository has one authenticated GitHub account for both server workspaces. The previous ruleset required one approval from someone other than the last pusher and had no bypass actor. GitHub therefore rejected both self-approval and administrator merge, making every PR impossible to merge even after the repository owner authorized and verified it.

The operational policy requires versioned PR coordination, but explicitly permits the repository owner/agent to verify and merge completed work. The enforcement settings must match that available identity model.

The repository owner chose to delete the incompatible ruleset and asked Agent 1 to create a replacement.

## Exact replacement

Create one active branch ruleset targeting only the default branch with no bypass actors.

Required protections:

- PR-only integration with `required_approving_review_count: 0` and `require_last_push_approval: false`;
- deletion protection;
- non-fast-forward protection;
- required review-thread resolution;
- merge, squash, and rebase merge methods remain available.

No server package, service, credential, or file outside the Git workspaces is changed.

## Planned actions

1. Publish this dedicated record as its own PR.
2. Preserve the previous ruleset configuration locally for rollback.
3. Confirm ruleset `21239285` has been deleted by the repository owner.
4. Create the replacement through the GitHub rulesets API.
5. Confirm the replacement is active and all intended protections are present.
6. Merge the verified operations PR and this policy-record PR.
7. Record the new ruleset ID, final API state, and merge results in the PR conversation.

## Verification

- The ruleset API must show exactly one active default-branch protection ruleset.
- It must report `required_approving_review_count: 0` and `require_last_push_approval: false`.
- PR #2 must become mergeable without a second account.
- The ruleset must still report active enforcement, deletion protection, non-fast-forward protection, a pull-request rule, and required review-thread resolution.

## Attempt on 2026-08-24

- The previous ruleset was confirmed deleted; the repository ruleset list was empty.
- Agent 1 attempted to create the approved replacement through the repository rulesets API.
- GitHub returned HTTP 403: `Resource not accessible by personal access token`.
- The installed repository token can push code and manage pull requests but cannot create rulesets because it lacks repository Administration write permission.
- No replacement ruleset was created and no fallback protection was changed.
- Do not merge into or push directly to `main` until the replacement exists.
- Next action: the repository owner creates the documented ruleset in GitHub settings, or replaces the protected server token with one that has repository Administration read/write permission, then Agent 1 retries and verifies.

## Rollback

Delete the replacement ruleset and recreate the previous ruleset from the locally preserved `state/ruleset-21239285-before.json` configuration. Rollback restores the previous enforcement behavior, which will again require a distinct second GitHub account for every merge.

## Coordination impact

GitHub will no longer enforce an independent account approval. Agents must still inspect the diff, verification, open PRs, and conflicts before merge, and must record that review in the PR body or conversation. Every coherent change continues to require a PR into `main`.
