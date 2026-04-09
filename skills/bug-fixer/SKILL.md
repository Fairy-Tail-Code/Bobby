---
name: bug-fixer
description: Diagnose failing tests or runtime errors, apply focused fixes, and add regression coverage when needed.
---

# Bug Fixer

Diagnose and fix concrete test failures, runtime errors, and regressions in the current repository.

Execution rules:
- Start from the observed failure, not from speculative refactors.
- Reproduce the failure with the narrowest useful command first.
- Inspect logs, stack traces, diffs, and nearby code before editing.
- Prefer the smallest coherent fix that resolves the root cause and preserves existing patterns.
- Add or update tests when the failure indicates missing regression coverage.
- Use docs lookup only when the failure depends on framework or library behavior that is not obvious from the repository.

Before finishing:
- state the root cause you found
- state the exact fix you applied
- list the verification commands you ran
- call out any residual risk or follow-up work if the environment blocked full validation
