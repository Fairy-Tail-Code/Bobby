# 2026-05-18 单 Agent 模式迁移到 AG2 beta

## 背景

- 项目此前同时维护两套执行内核：
  - `single` 模式：`ConversableAgent + DefaultPattern + UserProxyAgent`
  - `swarm` 模式：`autogen.beta.Agent + beta network runtime`
- 这导致工具桥、provider 兼容、上下文裁剪、流式观察等问题需要修两遍。
- 同时，旧的 `snip.py / auto_compact.py` 只挂在 legacy `TransformMessages` 链路上，beta 路径另有一套 `HistoryLimiter / TokenLimiter`，上下文治理也已经分叉。

## 处理

### 1. single runtime 改为 beta

- `orchestration/single_runtime.py` 重写为 beta 版本。
- 单 Agent 不再依赖：
  - `ConversableAgent`
  - `a_run_group_chat_iter`
  - `ChannelUserProxyAgent`
  - handoff / `TRANSFER TO USER`
- 新 runtime 改为与 beta network 类似的显式编排：
  - `SingleTurn.message`
  - `SingleTurn.next_step`
  - `next_step` 仅允许 `ask_user / complete / terminate`

### 2. single agent 创建改为 beta factory

- `agents/beta_factory.py` 新增 `create_single_beta_agent()`
- 复用 beta 的：
  - OpenAI / DeepSeek config 适配
  - MCP beta tools
  - skill beta tools
  - memory beta tools
  - PromptedSchema/native schema 选择逻辑

### 3. beta 上下文裁剪统一为本地 pair-safe middleware

- 新增 `infrastructure/context/beta_limiters.py`
- 不再使用 AG2 beta 内置 `HistoryLimiter / TokenLimiter`
- 改为本地 `PairSafeHistoryLimiter / PairSafeTokenLimiter`
- 裁剪时把：
  - `assistant(tool_calls)`
  - 紧随其后的 `ToolResultsEvent`
  视为同一个不可拆分 segment，避免裁剪后出现孤儿 `tool` 消息

### 4. AgentPool 从 legacy 模板池降级为兼容壳

- 旧 `AgentPool` 原本只服务 single-mode 的 `ConversableAgent` 模板克隆
- 迁移后 runtime 不再使用它创建单 Agent
- 目前保留最小占位壳，仅用于不改动 SessionManager 启动 wiring

## 结果

- `single` 和 `swarm` 现在都走 `autogen.beta.Agent`
- beta tool / stream / prompt schema / frontend 观察链路统一
- legacy `snip.py / auto_compact.py` 与旧 single runtime 仍在仓库中，但已不再处于主执行路径

## 验证

- 新增 beta single runtime 回归测试，覆盖：
  - `ask_user -> complete` 主流程
  - PromptedSchema fenced JSON 兼容
  - 纯文本提问降级为 `ask_user`
- 新增 beta context limiter 回归测试，覆盖 tool-call / tool-result 配对裁剪
