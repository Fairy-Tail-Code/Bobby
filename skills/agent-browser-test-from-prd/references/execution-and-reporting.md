# Execution And Reporting

Use this reference when running repository-local testcase docs with `agent-browser`.

## Read Order

1. Code repo path provided by the user
2. Canonical testcase files `testcase/browser-regression-cases.md` and `testcase/browser-regression-guide.md`
3. If canonical files are missing, other existing testcase files under `<repo>/testcase/`
4. Auth file

## Execution Order

1. Read the testcase corpus from `<repo>/testcase/`.
2. Prefer `testcase/browser-regression-cases.md` as the scenario source and `testcase/browser-regression-guide.md` as the execution guide.
3. If one or both canonical files are missing, fall back to the other existing testcase files under `<repo>/testcase/`.
4. Generate the session name in the format `abtp-<repo名>-<yyyyMMdd-HHmmss>` unless the user explicitly asked to reuse an existing one.
5. Start `agent-browser` with the explicit `--session`.
6. Prepare auth state.
7. Confirm the site is reachable.
8. Complete or restore login.
9. Run the existing regression set, starting with happy path and then edge cases.
10. Collect evidence for failures or blocked items.
11. Output a compact report.
12. Save auth state if the run produced a reusable logged-in session.
13. Close `agent-browser` after reporting and state save are complete.

## Browser Assertions

Prefer assertions that `agent-browser` can observe directly:
1. current page URL or title
2. input availability and enabled state
3. visible text content
4. element count
5. DOM removal after an action
6. request count when duplicate-submit protection matters
7. `errors` and `console` output when graceful degradation matters

## Recommended Artifacts

On important failures:
1. `snapshot -i`
2. `errors`
3. `network requests`
4. `screenshot <path>` when visual evidence matters

On success:
1. saved state path or session name
2. confirmation that the browser session was closed

Always include the actual session name used for the run.

## Report Format

Use a compact report like this:

```markdown
- Code repo:
- Testcase dir:
- Target URL:
- Auth file:
- Auth result:
- Saved state:
- Coverage:
- Pass rate:
- Passed:
- Failed:
- Blocked:
- Handback to dev:
- Evidence:
```

Each failed or blocked item should include:
1. scenario id or short name
2. first failing step
3. supporting evidence path or summary

## Coverage And Pass-Rate Rules

1. Coverage = executed scenarios / total planned scenarios
2. Count a scenario as executed if it reached a real pass or fail conclusion
3. Blocked and not-covered scenarios stay outside the numerator for coverage
4. Pass rate = passed / (passed + failed)
5. Do not include blocked or not-covered scenarios in the pass-rate denominator

## Failed Case Handback

Every failed case must be written as a development handback item with:

1. scenario id or short name
2. expected result
3. actual result
4. first failing step
5. evidence reference
6. a short statement that the case should be returned to development for fixing

After the report is finished, close the browser session with `agent-browser close` unless the user explicitly asks to keep the session open for inspection.
