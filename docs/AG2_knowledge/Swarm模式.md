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
