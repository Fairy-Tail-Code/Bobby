---
name: agent-browser-test-from-prd
description: Execute repository-local browser testcases with agent-browser against a target URL. Use when Codex needs to read a specified code repo path, prefer the canonical testcase files `testcase/browser-regression-cases.md` and `testcase/browser-regression-guide.md`, fall back to scanning the repo's fixed `testcase/` directory when needed, load a specified account or auth file, auto-generate an isolated agent-browser session name in the format `abtp-<repo名>-<yyyyMMdd-HHmmss>`, log into the target site in headless mode, wait for Human-In-The-Loop OTP input when verification-code login is used, reuse saved browser state only when the user explicitly asks for reuse, and run the existing regression suite with evidence.
---

# Agent Browser Test From Repo Testcase

## Overview

Use this skill when the task is to execute an already prepared browser testcase suite from the repository. The default workflow is:
1. read the specified code repo path and scan the fixed `testcase/` directory under that repo
2. prefer the canonical testcase files `testcase/browser-regression-cases.md` and `testcase/browser-regression-guide.md`
3. read the target URL and auth file
4. execute the existing browser suite with `agent-browser`
5. save evidence and report pass, fail, or blocked

Prefer repository-local testcase files over ad hoc prompts so future agents can reuse the same artifacts.

## Workflow

1. Read the specified code repo and inspect the fixed `testcase/` directory.
   The user must provide the target code repo path. Treat `<repo>/testcase/` as the canonical existing-case directory. If it does not exist, report that the testcase directory is missing instead of inventing new testcase files.
2. Read the testcase suite before execution.
   Treat the existing testcase files under `<repo>/testcase/` as the execution source of truth. Prefer the canonical files `testcase/browser-regression-cases.md` and `testcase/browser-regression-guide.md`. If one or both canonical files are missing, fall back to scanning the remaining testcase files under `<repo>/testcase/`. Do not generate new cases from a PRD, do not compare new and old cases, and do not merge or rewrite testcase content as part of this skill.
3. Read the auth file before touching the login page.
   The auth file is the login source of truth. Use it to determine login type, optional login URL, username or email, password if any, preferred saved-state path, and whether OTP is expected.
4. Generate an isolated browser session name before launching `agent-browser`.
   By default, create a fresh session name for every run in the format `abtp-<repo名>-<yyyyMMdd-HHmmss>`. Derive `<repo名>` from the repo directory name after safe normalization. Pass that value explicitly to `agent-browser --session <generated_name>`. Do not rely on an implicit tool default session name.
5. Reuse saved browser state only when the user explicitly asks for reuse.
   If the user does not ask for reuse, prefer a fresh session even when the auth file contains `session_name`, `state_file`, or `profile`. If the user explicitly asks for reuse, then try the declared `session_name`, `profile`, or `state_file` first.
6. Use headless login by default.
   Drive the login page with `agent-browser`. If `login_url` is present, open it directly. If `login_url` is absent, open the target site first and detect the login entry from the page. If the login type is password-based, fill credentials from the auth file. If the login type requires a one-time code, trigger delivery and then pause for Human-In-The-Loop input.
7. Pause narrowly for OTP.
   Ask the user only for the missing code after the page has definitely reached the verification-code state. Resume the same browser session after the user replies.
8. Execute the existing regression suite against the target URL.
   Run the testcase suite already present under `<repo>/testcase/`. Prefer browser-observable assertions such as DOM presence, DOM removal, request count, and page errors.
9. Preserve useful artifacts.
   Save browser state after successful login when useful. Report the actual session name used for this run. On failure, keep the smallest useful evidence: screenshot, snapshot, page errors, and request summaries.
10. Close `agent-browser` after execution.
   After the report and any state save are complete, close the `agent-browser` session so the run does not leave an idle browser daemon or page open.
11. Report coverage and outcome quality explicitly.
   At the end of the run, report test coverage, pass rate, and the failed cases. Treat failed cases as items that should be sent back to development for fixing.

## Primary Use Cases

- Run an existing browser testcase suite from the repository.
- Keep testcase files in the repo so later agents can rerun the suite.
- Log into a deployed site using a repository-provided auth file.
- Support both password login and OTP login with Human-In-The-Loop continuation.
- Run the existing regression suite with `agent-browser` and summarize results.

## Operating Rules

- Always require the user-specified code repo path.
- Treat `<repo>/testcase/` as a fixed directory name. Do not guess alternate case directories unless the user explicitly overrides this rule.
- Read existing files under `<repo>/testcase/` before execution.
- Prefer `testcase/browser-regression-cases.md` as the scenario source and `testcase/browser-regression-guide.md` as the execution guide.
- If the canonical files are missing, fall back to the other files already present under `<repo>/testcase/`.
- Do not rely on legacy names such as `02-test.md`, `03-test-agent.md`, or `merged-regression.md` as the primary convention.
- Do not generate testcase files from PRD content in this skill.
- Do not compare, deduplicate, merge, or rewrite testcase files in this skill unless the user explicitly asks for testcase editing as a separate task.
- Unless the user explicitly asks for session reuse, generate a fresh session name for every run in the format `abtp-<repo名>-<yyyyMMdd-HHmmss>`.
- Always pass the actual session to `agent-browser` explicitly with `--session`.
- Treat auth-file `session_name` as an optional reuse override, not the default behavior.
- Read the auth file before guessing selectors, login type, or whether OTP is needed.
- Prefer the auth file's declared login URL when present.
- If `login_url` is absent, detect the login entry from the target site by checking visible text, roles, labels, or known auth affordances such as `Sign in`, `Log in`, `登录`, avatar menus, or account buttons.
- If login-entry detection returns multiple plausible candidates, prefer the most explicit auth entry and stop to confirm only if ambiguity remains high.
- Prefer saved browser state before triggering email or SMS codes.
- For OTP flows, do not ask the user for the code until the page has visibly entered the code-input state.
- Do not require the user to open a visible browser unless the site has a challenge that cannot be completed headlessly.
- When an existing testcase says “old content must disappear,” assert real DOM removal or non-rendering, not just visual hiding.
- If the generated or existing test doc says a scenario depends on mocked data, say that clearly in the report instead of pretending the production environment covered it.
- Report blocked scenarios explicitly when they cannot be run in the current environment.
- After saving the final report and any reusable auth state, close the `agent-browser` session before ending the task unless the user explicitly asks to keep it open.
- End every execution report with:
  - test coverage = executed scenarios / total planned scenarios
  - pass rate = passed / (passed + failed)
  - failed cases = every failed scenario listed individually
- Any failed case must be presented as a development handback item, with enough detail for the developer to reproduce and fix it.

## What To Produce

- A compact execution report.
- Coverage and pass-rate summary.
- A development handback section for failed cases.
- Saved browser state details when login succeeds.
- Failure evidence when any scenario diverges from expectation.

## References

- Read [references/auth-file-and-login.md](references/auth-file-and-login.md) when using an account file, restoring state, handling password login, or pausing for OTP.
- Read [references/execution-and-reporting.md](references/execution-and-reporting.md) when translating the existing testcase docs into `agent-browser` execution steps and final reporting.
