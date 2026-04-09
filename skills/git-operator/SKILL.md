---
name: git-operator
description: Inspect local git state, review diffs, stage paths, and create local commits.
---

# Git Operator

Use local git operations to inspect changes and prepare a repository-local delivery state.

Execution rules:
- Prefer read-only git inspection tools first: status, diff, branch, log, and commit inspection.
- Treat `dev` as the default working branch for OpenHarness delivery flows.
- Use Gitee repository lookup or creation tools before cloning when the remote repository may not exist yet.
- Stage only the paths relevant to the current task.
- Create commits only after verification is complete and the staged diff matches the intended change set.
- Do not rewrite history.
- Push only when the workflow or task explicitly requires publishing the final delivery result, and prefer `origin/dev`.

Return:
- the git state you inspected
- the exact paths you staged
- the commit you created, if any
- any unresolved risks in the worktree
