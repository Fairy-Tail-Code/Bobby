# Auth File And Login

Use this reference when the user provides a login or account file for browser testing.

## Preferred Auth File Shape

Prefer JSON. Example:

```json
{
  "login_url": null,
  "login_type": "email_otp",
  "email": "tester@example.com",
  "password": null,
  "username": null,
  "state_file": "/tmp/example-auth-state.json",
  "session_name": null,
  "otp_mode": "human"
}
```

Password example:

```json
{
  "login_url": null,
  "login_type": "password",
  "username": "tester",
  "password": "secret",
  "state_file": "/tmp/example-auth-state.json",
  "session_name": null
}
```

`session_name` is optional. When it is omitted, the skill should generate a fresh session name in the format `abtp-<repo名>-<yyyyMMdd-HHmmss>` and pass it explicitly to `agent-browser --session`.

## Supported Login Types

Recommended values:
1. `password`
2. `email_otp`
3. `sms_otp`
4. `password_plus_otp`

## Execution Order

1. Read auth file.
2. Derive a fresh default session name in the format `abtp-<repo名>-<yyyyMMdd-HHmmss>`.
3. Launch `agent-browser` with the explicit `--session` value from step 2 unless the user explicitly asked for reuse.
4. If the user explicitly asked for reuse, then try `state_file`, `session_name`, or `profile` reuse first.
5. If reuse fails:
   - open `login_url` if it is present
   - otherwise open the target site URL and detect the login entry from the current page
6. Use the login type to decide the flow:
   - `password`: fill credentials and submit
   - `email_otp` or `sms_otp`: fill email or phone, trigger code delivery, wait for Human-In-The-Loop input
   - `password_plus_otp`: fill credentials first, then continue with OTP
7. After success, save state and verify it can be reused.

## Human-In-The-Loop OTP

When OTP is required:
1. trigger the code delivery first
2. verify the page is now in the code-entry state
3. only then ask the user for the code
4. resume the same browser session with the provided code

## Optional login_url

`login_url` is optional.

When it is omitted:
1. open the target site URL first
2. inspect the page for login affordances such as:
   - `Sign in`
   - `Log in`
   - `登录`
   - account or avatar buttons that open an auth menu
3. click the most explicit login entry
4. once the login form is visible, continue with the declared login type

Good pause message:

```text
已触发发送验证码，页面已进入验证码输入态。请把验证码发给我，我收到后会继续填入并提交。
```

## Blocked vs Failed

Blocked:
1. the user has not yet provided the missing OTP
2. the auth file is missing required fields
3. the site presents an unexpected anti-bot challenge

Failed:
1. a provided password or OTP is accepted by the page but login still does not complete
2. a saved state is written but cannot be reused immediately afterward

## Session Isolation

Default behavior:
1. create a fresh session for every run
2. use the format `abtp-<repo名>-<yyyyMMdd-HHmmss>`
3. pass the session explicitly with `--session`

Only reuse `session_name`, `state_file`, or `profile` when the user explicitly asks for reuse.
