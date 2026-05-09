# AG2 Beta Network 模式

## 背景

AG2 beta network 的核心思想是：多 agent 协作不再依赖框架内部的群聊 manager 负责“谁下一步发言”，而是把路由、人工接力、共享状态重新交还给应用本身。

本项目在 `ag2==0.11.5` 上的落地采用了当前版本可用的 beta 基元：

- `autogen.beta.Agent`
- `autogen.beta.AgentReply`
- `autogen.beta.MemoryStream`
- `autogen.beta.config.OpenAIConfig`
- `autogen.beta.middleware.builtin.HistoryLimiter`
- `autogen.beta.middleware.builtin.TokenLimiter`
- beta `FunctionTool`

## 与 Group Chat 的概念映射

### 1. Group Chat Pattern / Manager

旧路径：

- `DefaultPattern`
- `a_run_group_chat_iter`
- `OnCondition`
- `Handoffs`

beta network 路径：

- 应用层自己维护 runtime
- agent 只返回结构化决策
- runtime 决定是否问人、是否交给下一个 agent、何时完成

## 2. handoff tool call

旧路径：

- agent 通过 `transfer_to_*` 这类 tool call 切换角色

beta network 路径：

- agent 返回结构化字段，例如 `next_step=handoff_generator`
- runtime 校验当前角色是否允许这个动作
- runtime 负责真正调用下一个 agent

## 3. 共享上下文

旧路径：

- group chat 中所有 agent 持有同一份消息副本

beta network 路径：

- 每个角色有自己的 `MemoryStream`
- 应用层维护一份共享 transcript
- handoff 时把“最新交接内容 + 共享 transcript 尾部”送给下一个角色

这意味着：

- agent 内部推理线程更独立
- session resume 也更适合围绕 transcript 做，而不是依赖旧 manager 内部历史结构

## 4. Human-in-the-Loop

旧路径：

- `UserProxyAgent`

beta network 路径：

- runtime 自己通过 `ChannelAdapter.send()` 发出问题
- 通过 `wait_reply()` 等待人类回复
- 再把回复送回当前角色继续执行

本项目里这层仍然复用了既有的：

- CLI channel
- Feishu service channel
- Weixin service channel

## 5. Tool 注册

旧路径：

- `autogen.tools.Tool`
- `register_for_llm()`
- `register_for_execution()`

beta network 路径：

- beta `FunctionTool`
- 在创建 `Agent` 时直接放入 `tools=[...]`

对本项目的影响：

- MCP 工具桥需要单独做一份 beta 版本
- memory/skill 工具也要从“注册到 ConversableAgent”改成“直接生成 beta tool 列表”

## 6. 上下文压缩

旧路径：

- `process_all_messages_before_reply` hook
- Snip / AutoCompact transform

beta network 路径：

- middleware
- `HistoryLimiter`
- `TokenLimiter`

如果未来要补自动摘要压缩，应优先写成 beta middleware，而不是继续依赖 `ConversableAgent` transform hook。

## 7. 结构化输出兼容性

beta `Agent` 一旦声明 `response_schema=...`，并且底层配置使用的是 `OpenAIConfig + chat.completions`，当前 `autogen.beta` 会自动附带：

- `response_format.type=json_schema`

这在 OpenAI 原生兼容接口上通常是成立的，但在部分“OpenAI 兼容”后端上并不一定可用。已验证的一类典型情况是：

- `https://api.deepseek.com/chat/completions`
- 返回 `400 Bad Request`
- 报错：`This response_format type is unavailable now`

因此在 beta network 场景里，结构化输出要分成两层理解：

1. “业务层必须有结构化 contract”是必须的。
2. “传输层一定能靠 `response_format=json_schema` 强约束”并不成立。

本项目当前采取的兼容策略是：

1. 对支持该能力的后端，继续保留 `response_schema=NetworkTurn`
2. 对 DeepSeek 这类不支持的后端，改为 prompt 明示 JSON contract
3. 由应用层 runtime 在最终落点自行解析 `message / next_step`

经验上，beta network 的路由正确性不能只押注在模型供应商的结构化输出能力上；应用层最好始终保留一层本地校验与兜底解析。

## 本项目迁移建议

1. single 模式可以暂时保留 legacy path，避免一次性扩大爆炸半径。
2. 多 agent 专家模式优先切到 beta network runtime。
3. prompt 中凡是提到 `transfer_to_*` 的旧指令，都要追加新的 network contract 覆盖。
4. runtime 必须显式校验 `next_step`，否则 beta network 很容易退化成“模型想交给谁就交给谁”。
5. 如果官方文档里的 beta 模块尚未进入当前 pip 版本，优先使用当前版本已经稳定暴露的 beta 基元完成概念迁移。

## 迁移完成后的代码治理

迁移到 beta network 后，最好不要长期保留旧专家模式的群聊实现作为“备用路径”。经验上应该继续做第二步清理：

1. 删除旧的 `orchestration/group.py`
2. 删除只为旧 swarm handoff 服务的工厂函数和代理创建函数
3. 删除 `AgentPool` 中针对 swarm `ConversableAgent` 的模板逻辑
4. 清理入口文件里仍直接调用旧 group chat API 的路径
5. 清理 prompt 中对 `transfer_to_*`、handoff tool、`terminate_command` 的旧描述

否则很容易出现一种危险状态：

- 运行时已经走 beta network
- 代码库里却仍残留一整套旧 group chat 实现
- 新人难以判断“到底哪条链路是真正在跑的”

这类“迁移已完成但旧实现未退场”的状态，会显著增加维护成本和误修风险。

