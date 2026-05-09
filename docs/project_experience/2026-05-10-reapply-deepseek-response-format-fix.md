# 2026-05-10 重新补回 DeepSeek `response_format` 兼容修复

## 背景

5/9 曾在分支 `fix_deepseek_response_format` 上修过一次 DeepSeek 兼容问题：

- DeepSeek 的 `chat.completions` 不支持 `response_format.type=json_schema`
- beta network 角色 agent 如果直接传 `response_schema=NetworkTurn`
- `autogen.beta` 会自动下发 `response_format=json_schema`
- 最终导致首轮请求直接 `400 Bad Request`

但随后 `main` 上进行了 session/runtime 分层重构。重构过程中：

- `orchestration/network_runtime.py` 里的本地 JSON 兜底仍保留
- 但 `agents/beta_factory.py` 回到了始终 `response_schema=NetworkTurn` 的旧写法

结果就是：

- 主线已经切到新架构
- 但 DeepSeek 修复实际失效
- 重新安装 `.openharness/repo` 依然会拿到会报 400 的代码

## 根因

这不是“安装没更新”，而是“修复在历史上被后续重构覆盖掉了”。

具体现象：

1. `fix_deepseek_response_format` 的提交历史已经进入 `main`
2. 但当前 `main` 中的 `agents/beta_factory.py` 不再包含：
   - `_supports_native_response_schema(...)`
   - `response_schema=NetworkTurn if native_response_schema else None`
3. 因此运行时仍向 DeepSeek 发送不被支持的 `response_format=json_schema`

## 本次修复

把兼容逻辑重新补回当前主线：

### 1. beta factory 恢复后端能力判断

- 新增 `_supports_native_response_schema(...)`
- 通过 `base_url` 识别 DeepSeek 类后端

### 2. 按后端能力分两条路径创建角色 agent

- 支持 schema 的后端：
  - 继续 `response_schema=NetworkTurn`
- 不支持的后端：
  - 不传 `response_schema`
  - 依赖 prompt contract + runtime 本地解析

### 3. 补一条更直接的工厂回归

新增测试覆盖：

- DeepSeek base_url 时，角色 agent 的 `_response_schema` 为 `None`
- OpenAI 兼容后端仍保留 `_response_schema`

## 文件变更

- `agents/beta_factory.py`
- `tests/test_beta_factory.py`
- `docs/requirement/4.9需求迭代.md`
- `docs/project_experience/2026-05-10-reapply-deepseek-response-format-fix.md`
- `AGENTS.md`

## 验证

定向验证包括：

- `tests/test_beta_factory.py`
- `tests/test_network_runtime.py`

重点确认：

- 主线 agent 创建逻辑已重新具备 DeepSeek 兼容能力
- runtime 的本地 JSON 兜底可继续承接无 schema 模式

## 经验

1. “分支已合并”不等于“修复仍然存在于当前文件内容里”。
2. 对兼容性修复，最好补到离问题最近的工厂/适配层测试，否则后续重构很容易把它静默覆盖掉。
3. 安装仓库 `.openharness/repo` 的内容最终取决于远端 `main`，所以这类修复必须重新落回主线，而不是只停留在历史 worktree。
