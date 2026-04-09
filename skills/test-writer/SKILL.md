---
name: test-writer
description: Add, update, and run automated tests for the current delivery plan.
---

# Test Writer

Expand or repair test coverage for the implemented change set.

Execution rules:
- Derive tests from the PRD analysis, design, implementation details, and reviewer findings.
- Follow repository-native test structure, naming, fixtures, and helpers.
- Prefer focused tests that prove business behavior and prevent regressions.
- Use shell tools to run the narrowest useful validation first, then broader checks when needed.
- Cover the subsystems that changed. This may include frontend unit tests, backend unit or integration tests, API tests, and end-to-end checks when the PRD requires cross-system behavior.
- If implementation required bootstrapping a new project skeleton, add the baseline tests and verification needed to prove the scaffold, main entrypoints, and requested feature paths work together.

Return:
- the tests you added or updated
- what behavior they cover
- what remains unverified if command failures or environment gaps block full validation
