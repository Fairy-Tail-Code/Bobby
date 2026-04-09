# AG2 Swarm 模式

## 核心概念

Swarm 是 AG2 提供的多 Agent 协作模式，通过**条件化转移**（handoffs）控制 Agent 之间的流转，比 GroupChat 的 LLM 自由选择更结构化。

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

### AfterWork / TerminateTarget
兜底行为：
```python
agent.handoffs.set_after_work(TerminateTarget())  # 无条件终止
```

## 启动 Swarm

```python
from autogen.agentchat.contrib.swarm_agent import initiate_swarm_chat, a_initiate_swarm_chat

# 同步
chat_result, context_vars, last_speaker = initiate_swarm_chat(
    initial_agent=planner,
    messages="用户 prompt",
    agents=[planner, generator, evaluator],
    max_rounds=15,
    context_variables=context_variables,  # 可选，共享上下文
)

# 异步
chat_result, context_vars, last_speaker = await a_initiate_swarm_chat(...)
```

## ContextVariables

跨 Agent 共享的可变状态：
```python
from autogen import ContextVariables

ctx = ContextVariables()
ctx.set("retries", 0)
ctx.get("retries")  # 0
```

## 注意事项

1. **不能直接赋值 list**：`agent.handoffs = [...]` 会破坏 Handoffs 对象，必须用 `agent.handoffs = Handoffs()` 然后用 API 添加
2. **AgentTarget 是必须的**：`OnCondition(target=agent)` 会报 Pydantic 验证错误，必须 `OnCondition(target=AgentTarget(agent))`
3. **StringLLMCondition 是必须的**：`OnCondition(condition="string")` 同样报错，必须 `OnCondition(condition=StringLLMCondition("string"))`
4. **返回值是三元组**：`(ChatResult, ContextVariables, ConversableAgent)` — 最后一个参数是最后发言的 agent
