# agent-browser-test-from-prd

## 依赖：

npm install -g agent-browser

## 使用案例

用 $agent-browser-test-from-prd 读取代码仓库 /mnt/work/project/your-app 的 `testcase/` 目录，
优先使用 `testcase/browser-regression-cases.md` 和 `testcase/browser-regression-guide.md`，
对 https://agui-demo.8btc-ops.com 执行测试，
账号文件是 ./example/auth.json

## 这个 skill 做什么

这个 skill 用于把“已有 testcase -> 浏览器自动化测试”串起来。

默认流程：

1. 读取指定代码 repo 路径下固定的 `testcase/` 目录
2. 优先读取 `testcase/browser-regression-cases.md` 和 `testcase/browser-regression-guide.md`
3. 如果规范文件缺失，再回退读取 `testcase/` 目录中的其他已有 case
4. 读取指定的 `auth.json`
5. 为本次运行自动生成新的 session 名，格式为 `abtp-<repo名>-<yyyyMMdd-HHmmss>`
6. 启动 `agent-browser` 时显式传入 `--session`
7. 用 `agent-browser` 对已有 testcase 执行测试
8. 如果是验证码登录，进入 Human-In-The-Loop，等待用户输入验证码
9. 输出测试结果，并尽量复用保存的登录态
10. 测试完成后关闭 `agent-browser` 会话，避免遗留浏览器进程
11. 输出测试覆盖率、通过率和不通过用例；不通过用例需要明确打回开发

这两个文件的作用：

1. `testcase/browser-regression-cases.md`
   负责定义“测什么”，也就是验收用例、主路径、边界场景、阻断项和验收标准。
2. `testcase/browser-regression-guide.md`
   负责定义“怎么跑这些浏览器用例”，也就是 agent-browser 的执行提示、顺序和注意事项。
3. 账号文件
   负责定义“怎么登录”和“是否复用状态”。

---

## 什么时候用

适合这些场景：

1. 你的 repo 里已经有 `testcase/`，希望 AI 直接执行这些用例
2. 你希望 `agent-browser` 自动登录并执行主路径和边界场景
3. 你希望测试结果输出成可复查的执行报告

---

## 输入约定

使用这个 skill 时，建议明确提供 3 个输入：

1. 代码 repo 路径
2. 目标 URL
3. 账号文件路径

典型输入：

```text
用 $agent-browser-test-from-prd 读取代码仓库 /mnt/work/project/your-app，
对 https://agui-demo.8btc-ops.com/agents 执行测试，
账号文件是 auth.example.json
```

其中代码 repo 的 testcase 目录写死为：

```text
<repo>/testcase/
```

这个 skill 只读取该目录已有 case，不负责生成、对比、去重或合并 testcase。
默认优先读取：

```text
<repo>/testcase/browser-regression-cases.md
<repo>/testcase/browser-regression-guide.md
```

如果规范文件缺失，再回退读取同目录下其他已有 testcase 文件。

---

## auth.json 格式

推荐 JSON 格式：

```json
{
  "login_url": null,
  "login_type": "email_otp",
  "email": "tester@example.com",
  "username": null,
  "password": null,
  "phone": null,
  "state_file": "/tmp/your-site-auth-state.json",
  "session_name": null,
  "profile": null,
  "otp_mode": "human",
  "notes": "login_url is optional. If null, agent opens the target site and auto-detects the login entry. session_name is optional because the skill will generate one by default."
}
```

用户名密码登录示例：

```json
{
  "login_url": null,
  "login_type": "password",
  "email": null,
  "username": "tester",
  "password": "your-password",
  "phone": null,
  "state_file": "/tmp/your-site-auth-state.json",
  "session_name": null,
  "profile": null,
  "otp_mode": null,
  "notes": "For password login, agent opens the target site or login_url, fills username and password, then submits. session_name is optional because the skill will generate one by default."
}
```

参数填写说明：

1. `login_url`
   可选。
   如果已知固定登录页，建议直接填。
   如果填 `null`，AI 会先打开目标站点，再自动探测登录入口。
2. `login_type`
   推荐支持：
   - `password`
   - `email_otp`
   - `sms_otp`
   - `password_plus_otp`
     填 `password` 表示账号密码登录。
3. `username`
   填站点登录时实际使用的用户名。
   如果站点是“邮箱 + 密码”登录，也可以把邮箱填在 `username`，同时把 `email` 留空。
4. `password`
   填真实密码。
5. `email`
   只有站点明确区分“邮箱字段”和“用户名字段”时才使用。
   如果你已经把邮箱写到 `username`，这里就填 `null`。
6. `state_file`
   填登录成功后保存浏览器状态的位置，后续测试可直接复用。
7. `session_name`
   可选。
   如果不填，skill 默认会自动生成一个新的 session 名，格式固定为 `abtp-<repo名>-<yyyyMMdd-HHmmss>`。
   如果你明确想复用某个已有会话，才手工填写。
8. `profile`
   一般可留空，只有你明确要复用某个浏览器 profile 时再填。
9. `otp_mode`
   密码登录时填 `null`。

示例模板文件：

1. `/mnt/work/python/harness/auth.example.json`

---

## 输出内容

这个 skill 默认会产出：

1. 测试执行结果摘要
2. 测试覆盖率
3. 测试通过率，计算方式为 `通过 / (通过 + 不通过)`
4. 不通过用例列表，以及需要打回开发的说明
5. 登录态文件或 `session_name` 复用信息
6. 失败时的最小必要证据，例如：
   - `snapshot`
   - `errors`
   - `network requests`
   - 截图（如需要）
7. 执行完成后关闭 `agent-browser` 的说明

---

---

## 登录策略

默认登录顺序：

1. 默认先为当前运行生成一个新的 `session_name`
2. 生成规则固定为 `abtp-<repo名>-<yyyyMMdd-HHmmss>`
3. 启动 `agent-browser` 时必须显式传 `--session`
4. 只有用户明确要求复用时，才优先使用 `state_file` / `session_name` / `profile`
5. 若复用失败，再走新登录
6. 如果是密码登录，直接填表提交
7. 如果是验证码登录，先触发发码，再等待用户输入验证码

例如 repo 目录名是 `demo-app`，则自动生成的 session 可能是：

```text
abtp-demo-app-20260415-153045
```

验证码场景下，用户只需要参与这一步：

1. 在 AI 提示“已进入验证码输入态”后，把验证码发给 AI

---

## 推荐用法

### 执行 repo 中已有 testcase

```text
用 $agent-browser-test-from-prd 读取代码仓库 /mnt/work/project/your-app，
对 https://agui-demo.8btc-ops.com/agents 执行测试，
账号文件是 /mnt/work/python/harness/auth.example.json
```

### 只检查 testcase 和登录配置，不执行测试

```text
用 $agent-browser-test-from-prd 读取代码仓库 /mnt/work/project/your-app，
检查 testcase 和 auth 配置，先不要执行浏览器测试
```

---

## 注意事项

1. 这个 skill 默认关注功能行为，不默认验证性能指标。
2. 如果产品环境不方便稳定复现异常场景，AI 可能会把部分边界用例标记为 `blocked`。
3. 如果页面存在强验证码、人机挑战、复杂 SSO，可能需要显式提供 `login_url` 或改成可视模式辅助。
4. 除非用户明确要求保留现场，测试完成后应关闭 `agent-browser` 会话。
5. 这个 skill 默认每次生成新的 `session_name`，避免本机并发运行时串会话。
6. 如果用户没有明确要求复用，就不应直接复用 auth 文件里的 `session_name`。
7. 这个 skill 不负责从 PRD 生成 testcase，也不负责对 testcase 做去重、合并和回写。
8. 默认报告应包含：
   - 覆盖率 = 已执行用例 / 计划用例总数
   - 通过率 = 通过 / (通过 + 不通过)
   - 不通过用例逐条列出，并明确这些用例需要打回给开发处理
