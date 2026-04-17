# AG2 Group Chat Pattern 模式

## 核心概念

AG2 新版（0.9+）使用 `Pattern` + `initiate_group_chat` 编排多 Agent 协作，通过 `Handoffs` + `OnCondition` 定义条件化转移。

## 重要：新旧 API 不兼容

### 旧版（不要用）
```python
# swarm_agent.py — 不支持新版 Handoffs API
from autogen.agentchat.contrib.swarm_agent import initiate_swarm_chat
```
旧版 `initiate_swarm_chat` 有自己的转移机制，**不认识** `Handoffs` 对象。Planner 输出后会直接 "No next speaker selected" 异常终止。

### 新版（正确用法）
```python
from autogen.agentchat.group.patterns import DefaultPattern
from autogen.agentchat.group.multi_agent_chat import initiate_group_chat, a_initiate_group_chat

pattern = DefaultPattern(
    initial_agent=planner,
    agents=[planner, generator, evaluator],
    context_variables=context_variables,
)
chat_result, context_vars, last_speaker = initiate_group_chat(
    pattern=pattern,
    messages="用户 prompt",
    max_rounds=15,
)
```

`DefaultPattern` 直接读取每个 agent 的 `handoffs` 属性来驱动转移。

## 关键类

### Handoffs
每个 `ConversableAgent` 有 `handoffs` 属性（类型 `Handoffs`），管理三类条件：
- `context_conditions` — 无需 LLM 的上下文条件（`OnContextCondition`）
- `llm_conditions` — 需要 LLM 评估的条件（`OnCondition`）
- `after_works` — 兜底转移，无其他条件触发时执行

### OnCondition
LLM 评估的条件转移：
```python
OnCondition(
    target=AgentTarget(agent),          # 必须用 AgentTarget 包装
    condition=StringLLMCondition("..."),  # 必须用 StringLLMCondition 包装
)
```

### TerminateTarget
兜底终止：
```python
agent.handoffs.set_after_work(TerminateTarget())
```

## 其他 Pattern 类型
- `AutoPattern` — GroupChatManager 自动选择 speaker
- `RoundRobinPattern` — 轮流发言
- `RandomPattern` — 随机选择

## ContextVariables
```python
from autogen import ContextVariables
ctx = ContextVariables()
ctx.set("retries", 0)
```

## 踩坑记录

1. **旧 swarm 不兼容新 Handoffs**：`initiate_swarm_chat` 不识别 `Handoffs` + `OnCondition`，必须用 `DefaultPattern` + `initiate_group_chat`
2. **不能直接赋值 list**：`agent.handoffs = [...]` 破坏对象，必须 `agent.handoffs = Handoffs()` 然后用 API 添加
3. **AgentTarget 是必须的**：`OnCondition(target=agent)` 报 Pydantic 错误
4. **StringLLMCondition 是必须的**：`OnCondition(condition="string")` 报 Pydantic 错误
5. **返回值是三元组**：`(ChatResult, ContextVariables, ConversableAgent)`

## register_reply 的重要限制（2026-04-17 发现）

`register_reply` 的 hook 在 agent **生成回复之前**触发，不是之后。

### 执行流程

```python
# conversable_agent.py a_generate_reply():
for reply_func_tuple in self._reply_func_list:
    if self._match_trigger(trigger, sender):
        final, reply = reply_func(recipient, messages, sender, config)
        if final:
            return reply
# 所有 hook 都返回 (False, None) 后，继续执行默认的 LLM 回复
```

### 关键事实

1. **`messages` 是完整对话历史**（`self._oai_messages[sender]`），不是新消息
2. **`messages[-1]` 是触发消息**（上一个 agent 的输出），不是当前 agent 的输出
3. **返回 `(False, None)` 继续下一个 hook**，返回 `(True, reply)` 终止并使用该回复
4. **没有 post-reply hook**：AG2 不提供任何在 agent 生成回复之后触发的回调

### 对消息拦截的影响

如果用 `register_reply` 在 position=0 拦截消息并推送到飞书：
- 每个 agent 的 hook 推送的是**收到的消息**（上一个 agent 的输出），不是自己的输出
- 同一条消息被多个 agent 的 hook 重复推送
- Agent 的实际输出永远不会被捕获

### 替代方案

**可行但有限**：
- 轮询 `agent.chat_messages` 检测新增消息（当前采用的方案）
- Subclass `GroupChat` 重写 `append` 方法
- 手动实现 group chat 循环替代 `a_initiate_group_chat`

**不可行**：
- `process_all_messages_before_reply` — 也是 pre-processing
- `update_agent_state_before_reply` — 也是 pre-processing
- `send()` 方法 hook — group chat 中消息由 GroupChatManager 管理，不走 agent.send()

## Handoff 内部工具（2026-04-17 发现）

AG2 的 handoff 机制不是通过字符串匹配或回调实现的，而是通过让 LLM 生成特殊的 **tool call** 来执行转移。

### 内部工具类型

| 工具名 | 作用 | 来源 |
|--------|------|------|
| `transfer_to_{AgentName}_{N}` | 转移到指定 agent | `OnCondition(target=AgentTarget(agent))` |
| `terminate_command` | 终止整个 swarm 对话 | `set_after_work(TerminateTarget())` |

### 关键问题

1. **所有 agent 都能看到所有 handoff 工具**：AG2 将 handoff 工具注册给 group chat 中的每个 agent，而不仅仅是配置了该 handoff 的 agent。这意味着 Generator 可以看到并调用 `terminate_command`，即使只有 Evaluator 配置了 `TerminateTarget()`。

2. **LLM 可能误用 handoff 工具**：如果 LLM 看到 `terminate_command` 在自己的工具列表中，可能会在认为任务完成时调用它。对于 `after_work=StayTarget()` 的 agent，这会导致工具调用无法正确处理而卡死。

3. **工具名后缀带数字**：如 `transfer_to_Evaluator_1`，数字后缀是 AG2 内部生成的，可能随 group chat 成员变化。

### 防护措施

- 在 agent 的 prompt 中明确禁止调用不属于自己角色的 handoff 工具（如 Generator 不能调用 `terminate_command`）
- 消息展示层过滤掉 `transfer_to_*` 和 `terminate_command`，不展示给用户
