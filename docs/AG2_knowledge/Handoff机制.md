# AG2 Handoff 机制详解

## 核心发现（2026-04-13）

**AG2 的 `OnCondition` + `StringLLMCondition` 不是文本匹配机制，而是 tool/function call 机制。**

LLM 必须调用 handoff tool function 才能触发转移，不能仅输出文本。

## 机制原理

### 1. Handoff Tool 的生成

当为 agent 配置 handoff 时：

```python
evaluator.handoffs = Handoffs()
evaluator.handoffs.add_llm_conditions([
    OnCondition(
        target=AgentTarget(generator),
        condition=StringLLMCondition("TRANSFER TO GENERATOR"),
    ),
])
```

AG2 在 `create_on_condition_handoff_functions()` 中自动完成以下操作：

1. **生成 tool function name**：`transfer_to_{AgentName}_{index}`（如 `transfer_to_Generator_1`）
2. **将 StringLLMCondition 的文本作为 tool description**（如 "TRANSFER TO GENERATOR"）
3. **注册到 agent 的 tool 列表**，LLM 可通过 function call 调用

源码位置：`autogen/agentchat/group/group_utils.py:181-197`

### 2. Handoff 的触发流程

```
LLM 调用 transfer_to_Generator_1()
  → GroupToolExecutor 检测到 tool call
  → tool function 返回 TransitionTarget 对象
  → determine_next_agent() 从 tool executor 获取 next target
  → 转移到目标 agent
```

### 3. 无 Tool Call 时的回退

如果 LLM **没有调用任何 handoff tool**，`determine_next_agent()` 会：

1. 检查 tool executor 的 next target → 无
2. 检查 agent 的 `after_work` → 按 `after_work` 配置处理
3. 如 `after_work = TerminateTarget()` → 直接终止对话

源码位置：`autogen/agentchat/group/group_utils.py:439-526`

## 常见错误

### 错误：在 Prompt 中指示模型输出文本触发转移

```markdown
## Handoff Rules
When you are done, you MUST end your message with: `TRANSFER TO GENERATOR`
```

这会导致 LLM 将 "TRANSFER TO GENERATOR" 作为纯文本输出，AG2 不会检测到任何 tool call，直接走 `after_work` 逻辑终止对话。

**现象**：
```
Evaluator (to chat_manager):
...（评估内容）...
TRANSFER TO GENERATOR

***** AfterWork handoff (Evaluator): Terminate *****
>>>>>>>> TERMINATING RUN: No next speaker selected
```

### 正确做法：指示模型调用 handoff tool

```markdown
## Handoff Rules
You have handoff tool functions in your tool list (e.g. functions starting with `transfer_to_`).
To transfer, you MUST call the corresponding tool function.
Do NOT write transfer phrases as plain text.
```

## 相关源码文件

| 文件 | 作用 |
|------|------|
| `autogen/agentchat/group/llm_condition.py` | StringLLMCondition 定义 |
| `autogen/agentchat/group/on_condition.py` | OnCondition 定义 |
| `autogen/agentchat/group/handoffs.py` | Handoffs 容器，`set_llm_function_names()` |
| `autogen/agentchat/group/group_utils.py` | `create_on_condition_handoff_functions()`、`determine_next_agent()` |
| `autogen/agentchat/group/group_tool_executor.py` | Tool call 检测和 TransitionTarget 提取 |

## 其他 MCP Server 的坑

### browser_server.py：Sync API 与 asyncio 冲突

FastMCP 的 stdio transport 在 asyncio 事件循环中运行。Playwright Sync API 内部也启动自己的事件循环，两者冲突。

**错误**：`It looks like you are using Playwright Sync API inside the asyncio loop.`

**修复**：将整个 server 从 `playwright.sync_api` 改为 `playwright.async_api`：
- `sync_playwright` → `async_playwright`
- 所有 tool 函数 → `async def`
- 所有 Playwright 调用加 `await`
- `threading.Lock` → `asyncio.Lock`

### git_server.py：subprocess 死锁

MCP stdio 传输下，`subprocess.run()` 不设 `stdin=DEVNULL` 时，git 子进程继承 MCP 通信管道作为 stdin。当 git 尝试交互式提示时会导致死锁。

**修复**：
- 所有 `subprocess.run()` 添加 `stdin=subprocess.DEVNULL`
- 设置 `GIT_TERMINAL_PROMPT=0` 环境变量
- 添加 subprocess timeout
