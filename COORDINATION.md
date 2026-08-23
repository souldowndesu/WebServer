# Coordination Guide

Each AI must work only on its own branch and use pull requests to merge into `main`.

## Before starting work

```sh
git fetch origin
git rebase origin/main
```

## While working

1. Keep commits small and describe the intent clearly.
2. Push only to the workspace's assigned branch.
3. Do not force-push shared history.
4. Record unfinished work and important decisions in the pull request description.

## Handing work to the other AI

1. Push the current branch.
2. Open a pull request into `main`.
3. Let the other AI review or continue from the pull request.
4. After merge, both workspaces fetch and rebase onto the updated `main`.

## Conflict rule

If both AIs need the same file, agree on ownership first or split the change into separate files. Resolve conflicts on the feature branch, never directly on `main`.
