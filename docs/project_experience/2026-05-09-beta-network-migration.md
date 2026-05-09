# 2026-05-09 多 Agent 群聊迁移到 AG2 Beta Network

## 背景

当前专家模式虽然已经不再使用最早的 `GroupChatManager`，但底层仍依赖：

- `DefaultPattern`
- `a_run_group_chat_iter`
- `OnCondition / Handoffs`
- `ConversableAgent` 的 handoff tool call 语义

这仍然属于 AG2 的 group chat/pattern 路径。根据官方迁移文档，需要进一步把“群聊式编排”迁到 beta network 风格：agent 负责产出结构化决策，应用自身负责路由、上下文与事件桥接。

## 参考

- 官方迁移文档：`https://docs.ag2.ai/latest/docs/beta/network/migration_from_group_chat/#concept-mapping`
- beta 动机文档：`https://docs.ag2.ai/latest/docs/beta/motivation/`

> 落地时同时核对了本地可安装版本 `ag2==0.11.5`。文档中的部分 beta 概念页比当前 pip 包更前沿，因此本次实现优先使用当前版本中已经稳定可用的 `Agent / MemoryStream / middleware / HITL hook / beta tools`。

## 概念映射

本次迁移按下面的映射实施：

- `Pattern + Group Chat` → 应用层自管的 `NetworkSwarmRuntime`
- `handoff tool + OnCondition` → `NetworkTurn.next_step`
- `群聊共享历史` → “每个角色自己的 `MemoryStream` + 应用层共享 transcript”
- `UserProxyAgent` → `ChannelAdapter.send()/wait_reply()` 驱动的人类接力
- `ConversableAgent Tool` → beta `FunctionTool`
- `Snip/AutoCompact hook` → beta `HistoryLimiter/TokenLimiter`

## 本次实现

### 1. 新增 beta network 角色层

- 新增 `agents/beta_factory.py`
- 使用 `autogen.beta.Agent`
- 使用 `OpenAIConfig` 从现有 `.env`/`LlmConfig` 映射模型配置
- 使用 `NetworkTurn` 作为统一结构化输出 schema

### 2. 新增显式编排 runtime

- 新增 `orchestration/network_runtime.py`
- 以 `pm -> planner -> generator -> evaluator` 为主路径
- agent 不再通过 `transfer_to_*` 工具切换，而是返回 `next_step`
- runtime 负责：
  - 校验当前角色允许的下一步
  - 将消息写入共享 transcript
  - 通过 channel 发送人工问题并等待回复
  - 在角色间构造 handoff message
  - 维护最终 `completed / terminated` 状态

### 3. 多 Agent session 切换到底层新 runtime

- `single` 模式保持现有 legacy group chat 流程
- `swarm` 模式底层改走 beta network runtime
- 保留：
  - session snapshot
  - gateway/CLI 前端消息发送
  - tool call 前端提示
  - session 收尾 memory extract
  - knowledge collect/sync

### 4. MCP / memory / skill 工具 beta 化

- 新增 `infrastructure/mcp/beta_tool_bridge.py`
- 新增 `infrastructure/memory/beta_tool.py`
- 新增 `infrastructure/skills/beta_tool.py`
- 角色级工具名恢复为自然语义：
  - `load_skill`
  - `load_memory`
  - `save_memory`

## 文件变更

- `agents/beta_factory.py`
- `agents/network_models.py`
- `infrastructure/mcp/beta_tool_bridge.py`
- `infrastructure/memory/beta_tool.py`
- `infrastructure/skills/beta_tool.py`
- `orchestration/network_runtime.py`
- `infrastructure/session/swarm_session.py`
- `orchestration/termination.py`
- `tests/test_network_runtime.py`

## 验证

已通过以下定向测试：

- `tests/test_network_runtime.py`
- `tests/test_session_snapshots.py`
- `tests/test_agent_factory.py`
- `tests/test_orchestration.py`

结果：`15 passed`

## 经验

1. 官方 beta network 迁移的关键不是换 import，而是把“谁决定下一步”从框架内建 manager，移回应用层。
2. 在当前 `ag2==0.11.5` 上，最稳妥的落地方式是使用 `Agent + response_schema + MemoryStream + middleware`，而不是等待文档里更前沿的 beta 模块全部进入 pip 版本。
3. 迁移时不要一次性推翻 single 模式。先把多 agent 主链路切到 network runtime，风险会明显更可控。

## 后续清理

完成主链路迁移后，又补做了一轮“旧实现清场”，避免主仓库同时保留两套专家模式：

- 删除 `orchestration/group.py`
- 删除 `agents/user.py`
- `agents/factory.py` 只保留 single 模式需要的 `create_single_agent / setup_single_handoffs / context transform`
- `infrastructure/agent_pool.py` 只保留 single 模式模板池，不再维护 swarm templates
- `infrastructure/session/swarm_session.py` 删除旧的 `_create_swarm_agents()` 分支
- `main.py` 不再直接组装 `create_all_agents + arun_swarm`，改为复用 `SessionManager`
- 四个专家角色 prompt 删除对 `transfer_to_*` / handoff tool 的依赖性描述

这一步的目标不是“再做一次迁移”，而是把迁移后已经没有任何调用方的旧群聊实现彻底移除，避免后续维护时误判当前真实链路。

