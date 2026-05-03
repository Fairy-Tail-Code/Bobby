# 任务：用 AG2 a_run_group_chat_iter 事件驱动替代 polling 轮询

## 背景
当前 `infrastructure/swarm_session.py` 的 `_run()` 方法用 `a_initiate_group_chat`（阻塞式）+ `_monitor_messages`（轮询 polling 2-5秒间隔）来推送消息到飞书。需要改为 AG2 的异步迭代器 `a_run_group_chat_iter`，事件驱动。

## 调研结论（已完成）

### AG2 v0.11.5 的 API
```python
# Import（注意：不在 group __init__ 里，需要从 multi_agent_chat 直接导入）
from autogen.agentchat.group.multi_agent_chat import a_run_group_chat_iter

# 返回 AsyncRunIterResponse，支持 async for
async for event_response in await a_run_group_chat_iter(
    pattern=pattern,
    messages=messages_input,
    max_rounds=max_rounds,
    yield_on=None,  # None = yield all events
):
    # event_response 是 WrappedEvent，实际事件在 .content 里
    event = event_response.content
    # isinstance 检查
```

### 关键事件类型
```python
from autogen.events.agent_events import (
    TextEvent,           # sender, recipient, content (str) — LLM文本输出
    ToolCallEvent,       # sender, recipient, tool_calls — 工具调用
    ToolResponseEvent,   # sender, recipient, content — 工具返回
    TerminationEvent,    # termination_reason — 终止
    RunCompletionEvent,  # history, summary, cost, last_speaker, context_variables — 完整结果
    ErrorEvent,          # error — 错误
    GroupChatRunChatEvent,  # — 轮次开始
    InputRequestEvent,   # — 同步HITL
    AsyncInputRequestEvent, # — 异步HITL
)
```

### TextEvent 的 content 字段
`TextEvent.content` 可以是 `str | int | float | bool | list[dict] | None`，需要 `isinstance(content, str)` 判断。

### BasePrintReceivedEvent（TextEvent 的父类）
有 `sender: str` 和 `recipient: str` 字段。

## 要修改的文件（共3个）

### 1. `infrastructure/frontend.py` — 扩展 Protocol

当前只有 `send_text`，需要加两个可选方法：

```python
@runtime_checkable
class Frontend(Protocol):
    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message to a chat."""
        ...

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        """Stream a single token (for frontends that support streaming).

        Default: no-op. Feishu doesn't need this.
        """
        ...

    async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
        """Notify that an agent is calling a tool."""
        ...
```

### 2. `infrastructure/feishu_bot.py` — 加空实现

在 `FeishuBotService` 类里加两个方法：

```python
async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
    """Feishu doesn't support streaming — no-op."""
    pass

async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
    """Notify tool call via text message."""
    await self.send_text(chat_id, f"🔧 **{agent_name}** 正在执行工具: `{tool_name}`")
```

### 3. `infrastructure/swarm_session.py` — 核心重写

#### Import 变更
```python
# 删除
from autogen.agentchat.group.multi_agent_chat import a_initiate_group_chat

# 新增
from autogen.agentchat.group.multi_agent_chat import a_run_group_chat_iter
from autogen.events.agent_events import (
    TextEvent, ToolCallEvent, TerminationEvent,
    RunCompletionEvent, ErrorEvent,
)
```

#### `_run()` 方法重写

把当前第145-213行（从 `self._agents = self._create_agents()` 到任务完成通知）替换为：

```python
async def _run(self) -> None:
    """Build agents, iterate events from group chat, and push to frontend."""
    try:
        self._agents = self._create_agents()

        if self._mode == "single":
            agents_list = [self._agents["assistant"]]
            for key in ("assistant_owner", "user"):
                if key in self._agents:
                    agents_list.append(self._agents[key])
            initial_agent = self._agents["assistant"]
        else:
            agents_list = [
                self._agents["pm"],
                self._agents["planner"],
                self._agents["generator"],
                self._agents["evaluator"],
            ]
            for key in ("pm_owner", "planner_owner", "generator_owner", "evaluator_owner"):
                if key in self._agents:
                    agents_list.append(self._agents[key])
            initial_agent = self._agents["pm"]

        pattern = DefaultPattern(
            initial_agent=initial_agent,
            agents=agents_list,
        )

        # Choose messages source
        if self._is_resume:
            valid_names = {a.name for a in agents_list}
            messages_input = self._preprocess_resume_messages(
                self._resume_messages, valid_names,
            )
            if not messages_input:
                logger.warning(
                    "All resume messages filtered out, falling back to prompt: chat_id=%s",
                    self.chat_id,
                )
                messages_input = self._prompt
                self._is_resume = False
        else:
            messages_input = self._prompt

        # === Event-driven iteration ===
        chat_history: list[dict] = []
        last_speaker_name = ""
        session_id = SessionSnapshot.generate_id()

        async for event_response in await a_run_group_chat_iter(
            pattern=pattern,
            messages=messages_input,
            max_rounds=self._harness_config.max_rounds,
        ):
            event = event_response.content

            if isinstance(event, TextEvent):
                content = event.content
                sender = event.sender
                if content and isinstance(content, str):
                    stripped = content.strip()
                    if (
                        stripped
                        and not re.match(r"^(Transfer to|TERMINATE|APPROVED|REJECTED)", stripped, re.IGNORECASE)
                        and not sender.endswith("_owner")
                    ):
                        await self._frontend.send_text(
                            self.chat_id,
                            f"【{sender}】\n{stripped}",
                        )

            elif isinstance(event, ToolCallEvent):
                for tc in (event.tool_calls or []):
                    fn_name = tc.get("function", {}).get("name", "unknown")
                    if not fn_name.startswith("transfer_to_") and fn_name != "terminate_command":
                        await self._frontend.on_tool_call(
                            self.chat_id, event.sender, fn_name,
                        )

            elif isinstance(event, RunCompletionEvent):
                chat_history = event.history
                last_speaker_name = event.last_speaker
                self._save_snapshot(
                    messages=chat_history,
                    session_id=session_id,
                    status="completed",
                )
                await self._frontend.send_text(
                    self.chat_id,
                    f"✅ 任务完成！最后发言: {last_speaker_name}\n"
                    f"📋 会话ID（可用于恢复）: {session_id}",
                )

            elif isinstance(event, ErrorEvent):
                logger.error("Group chat error: %s", event.error)

        # Knowledge collection (fire-and-forget)
        if chat_history:
            await self._collect_and_sync_knowledge(chat_history, session_id)

    except asyncio.CancelledError:
        messages = self._extract_messages_from_agents()
        session_id = SessionSnapshot.generate_id()
        self._save_snapshot(
            messages=messages,
            session_id=session_id,
            status="terminated",
        )
        await self._frontend.send_text(
            self.chat_id,
            f"⚠️ 任务已终止\n"
            f"📋 会话ID（可用于恢复）: {session_id}",
        )
    except Exception:
        logger.exception("SwarmSession error: chat_id=%s", self.chat_id)
        await self._frontend.send_text(self.chat_id, "❌ 任务执行出错，请查看日志")
    finally:
        self._terminated = True
        if self._on_complete:
            try:
                self._on_complete(self.chat_id)
            except Exception:
                logger.exception("on_complete callback failed: chat_id=%s", self.chat_id)
```

#### 删除以下方法（不再需要）
- `_start_message_monitor()` (第391-393行)
- `_monitor_messages()` (第395-414行)
- `_push_message_to_feishu()` (第416-474行)
- `_flush_remaining_messages()` (第476-485行)

#### 删除不再使用的实例变量
在 `__init__` 中删除 `self._pushed_count: int = 0`（第116行）

## ⚠️ 注意事项

1. **不要动 `_create_agents()`、`_create_single_agents()`、`_create_swarm_agents()`** — 这些不需要改
2. **不要动 `inject_reply()`、`terminate()`、`dispose()`** — 这些不需要改
3. **不要动 `_save_snapshot()`、`_preprocess_resume_messages()`、`_strip_terminate_from_last_message()`** — 这些不需要改
4. **不要动 `_collect_and_sync_knowledge()`** — 不需要改
5. **不要动 `_extract_messages_from_agents()`** — CancelledError 时仍需要
6. **`_pushed_count` 变量** — 删除 `_run()` 中对它的引用，以及 `__init__` 中的声明
7. **ToolCallEvent 的 tool_calls 字段** — 是 `list[dict]`，每个 dict 有 `"function": {"name": ...}`，需要 `event.tool_calls or []` 防空
8. **RunCompletionEvent 的 history 字段** — 就是 `chat_history`（`list[dict]`），和原来 `result.chat_history` 一样
9. **RunCompletionEvent 的 last_speaker** — 是 `str`（agent name），不是 agent 对象！原来 `last_speaker.name`，现在直接用 `event.last_speaker`

## 验证
改完后所有修改的文件都要 `python -m py_compile` 通过。
