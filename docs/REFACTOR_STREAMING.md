# 重构计划：事件驱动消息系统 + 流式输出

## 目标
1. 干掉 `_monitor_messages()` polling 轮询机制
2. 改用 AG2 的 `a_run_group_chat_iter` 异步迭代器，事件驱动
3. Frontend Protocol 扩展流式支持：`stream_token()` + `on_message_complete()`
4. 飞书不受影响（stream_token 空实现，on_message_complete 走原 send_text）
5. 为 CLI 前端铺路（stream_token → 实时 print）

## AG2 事件系统调研结果

### 关键 API

```python
# 当前用的（阻塞式，等全部完成才返回）
result, context, last_speaker = await a_initiate_group_chat(
    pattern=pattern, messages=messages, max_rounds=max_rounds
)

# 应该改用的（异步迭代器，逐事件返回）
async for event in await a_run_group_chat_iter(
    pattern=pattern, messages=messages, max_rounds=max_rounds,
    yield_on=[TextEvent, ToolCallEvent, TerminationEvent]
):
    # event 是 BaseEvent 子类
    if isinstance(event.content, TextEvent):
        # 完整文本消息（sender, recipient, content）
    elif isinstance(event.content, ToolCallEvent):
        # 工具调用（sender, recipient, tool_calls）
    elif isinstance(event.content, TerminationEvent):
        # 结束
    elif isinstance(event.content, RunCompletionEvent):
        # 完整结果（history, summary, cost, last_speaker）
```

### 事件类型（来自 autogen.events.agent_events）

| 事件类 | 字段 | 用途 |
|--------|------|------|
| `TextEvent` | sender, recipient, content | LLM 文本输出（完整消息） |
| `ToolCallEvent` | sender, recipient, tool_calls | 工具调用 |
| `ToolResponseEvent` | sender, recipient, content | 工具返回 |
| `InputRequestEvent` | — | AG2 请求用户输入（同步） |
| `AsyncInputRequestEvent` | — | AG2 请求用户输入（异步） |
| `TerminationEvent` | termination_reason | 对话终止 |
| `RunCompletionEvent` | history, summary, cost, last_speaker | 完整运行结果 |
| `GroupChatRunChatEvent` | — | group chat 轮次开始 |
| `ErrorEvent` | error | 错误 |

### 重要发现
- `TextEvent` 是**完整消息级别**，不是 token 级别。AG2 的 swarm 内部虽然用了 IOStream，但 `a_run_group_chat_iter` 只在消息完成时 yield TextEvent。
- 如果要真正的 token 级别流式，需要接入 OpenAI client 的 streaming callback，不是 AG2 的事件系统。
- **当前方案**：先用 `a_run_group_chat_iter` 替换 polling，实现消息级事件驱动。token 级流式作为后续优化。

## 分步实施计划

### Step 1: 扩展 Frontend Protocol

文件: `infrastructure/frontend.py`

```python
@runtime_checkable
class Frontend(Protocol):
    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a complete text message."""
        ...

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        """Stream a single token. Default: no-op (for frontends that don't support streaming)."""
        ...  # 飞书: pass; CLI: print(token, end="", flush=True)

    async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
        """Notify a tool call is starting. Default: send_text with tool name."""
        ...
```

注意：这些都是 Protocol 方法，飞书 Frontend（FeishuBotService）不需要改——Protocol 不强制实现带 `...` 的方法。但为了安全，给 FeishuBotService 加显式的空实现。

### Step 2: 给 FeishuBotService 加流式空实现

文件: `infrastructure/feishu_bot.py`

```python
async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
    """Feishu doesn't support streaming — no-op."""
    pass

async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
    """Delegate to send_text for tool call notification."""
    await self.send_text(chat_id, f"🔧 **{agent_name}** 正在执行工具: `{tool_name}`")
```

### Step 3: 重写 SwarmSession._run() — 用 a_run_group_chat_iter

文件: `infrastructure/swarm_session.py`

这是核心改动。把：

```python
# 旧：启动 polling monitor，阻塞等结果
monitor_task = self._start_message_monitor()
result, context, last_speaker = await a_initiate_group_chat(...)
monitor_task.cancel()
await self._flush_remaining_messages(result.chat_history)
```

改为：

```python
# 新：事件驱动迭代
from autogen.events.agent_events import (
    TextEvent, ToolCallEvent, ToolResponseEvent,
    TerminationEvent, RunCompletionEvent, ErrorEvent,
    GroupChatRunChatEvent, InputRequestEvent, AsyncInputRequestEvent,
)
from autogen.agentchat.group import a_run_group_chat_iter

async for event_response in await a_run_group_chat_iter(
    pattern=pattern,
    messages=messages_input,
    max_rounds=self._harness_config.max_rounds,
):
    event = event_response.content  # unwrap
    if isinstance(event, TextEvent):
        # 文本消息 → 推送到前端
        if event.content and isinstance(event.content, str):
            stripped = event.content.strip()
            if stripped and not re.match(r"^(Transfer to|TERMINATE|APPROVED|REJECTED)", stripped, re.IGNORECASE):
                if not event.sender.endswith("_owner"):
                    await self._frontend.send_text(
                        self.chat_id,
                        f"【{event.sender}】\n{stripped}",
                    )
    elif isinstance(event, ToolCallEvent):
        # 工具调用 → 通知
        for tc in event.tool_calls:
            fn_name = tc.get("function", {}).get("name", "unknown")
            if not fn_name.startswith("transfer_to_") and fn_name != "terminate_command":
                await self._frontend.on_tool_call(self.chat_id, event.sender, fn_name)
    elif isinstance(event, RunCompletionEvent):
        # 完成 → 保存 snapshot
        self._save_snapshot(messages=event.history, session_id=session_id, status="completed")
        await self._frontend.send_text(
            self.chat_id,
            f"✅ 任务完成！最后发言: {event.last_speaker}\n📋 会话ID: {session_id}",
        )
    elif isinstance(event, ErrorEvent):
        logger.error("Group chat error: %s", event.error)
```

### Step 4: 删除 polling 相关代码

删除：
- `_start_message_monitor()`
- `_monitor_messages()`
- `_push_message_to_feishu()`
- `_flush_remaining_messages()`

这些全部被事件驱动替代了。

### Step 5: 更新 import

文件: `infrastructure/swarm_session.py`

```python
# 删除
from autogen.agentchat.group.multi_agent_chat import a_initiate_group_chat

# 新增
from autogen.agentchat.group import a_run_group_chat_iter
from autogen.events.agent_events import (
    TextEvent, ToolCallEvent, ToolResponseEvent,
    TerminationEvent, RunCompletionEvent, ErrorEvent,
)
```

### Step 6: 验证

1. 所有改动文件 `python -m py_compile` 通过
2. 启动服务，飞书模式测试：
   - 发消息触发任务 → 能看到 agent 输出
   - 工具调用通知正常
   - HITL 请求/回复正常
   - 任务完成通知正常
   - 终止任务正常
3. 确认没有 polling 日志（不再有 sleep 循环）

## 文件修改清单

| 文件 | 操作 |
|------|------|
| `infrastructure/frontend.py` | 扩展 — 加 stream_token + on_tool_call |
| `infrastructure/feishu_bot.py` | 小改 — 加空实现方法 |
| `infrastructure/swarm_session.py` | **重写** — 事件驱动替代 polling |
| `server.py` | 不改 |

## 不改的文件
- `infrastructure/session_manager.py` — 不涉及
- `agents/channel_proxy.py` — 不涉及
- 核心 agents — 不涉及

## 风险点

1. **`a_run_group_chat_iter` 的 import 路径** — 需要确认在项目用的 AG2 版本中可用。如果不可用，备选方案是 `a_run_group_chat` + 自定义 IOStream handler。
2. **HITL (InputRequestEvent)** — AG2 的 HITL 可能通过 InputRequestEvent 触发，需要确认 channel_proxy 的 `a_get_human_input` 是否兼容事件驱动模式。如果不兼容，HITL 部分暂时保持不动。
3. **event.content 嵌套** — RunIterResponse 的结构是 `event_response.content` 包含实际 Event 对象，需要确认解包方式。

## 验证策略

先在飞书模式下验证所有功能正常（因为飞书是默认前端，且 stream_token 是空操作，风险最低）。验证通过后再开发 CLI 前端。
