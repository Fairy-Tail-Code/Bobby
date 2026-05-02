node.exe : Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin 
explicitly: < /dev/null to skip, or wait longer.
所在位置 C:\Users\WUJIEAI\AppData\Roaming\npm\claude.ps1:24 字符: 5
+     & "node$exe"  "$basedir/node_modules/@anthropic-ai/claude-code/cl ...
+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (Warning: no std...or wait longer.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
现在我已经完整阅读了所有关键文件。以下是深入的性能分析报告。

---

## 性能问题深度分析报告

### 1. 内存泄漏：session_manager 的 `_sessions` 清理 + swarm_session 中 agent 资源释放

**严重程度：高**

**问题分析：**

- `session_manager.py:276-286` — `_cleanup_session` 是唯一的清理入口，通过 `_on_complete` 回调触发。但存在**竞态窗口**：如果 `_run()` 的 `finally` 块中 `_on_complete` 回调抛异常，session 将永远留在 `_sessions` 中。
- `session_manager.py:156-160` — `_create_session` 中清理旧 session 时调了 `old.terminate()` 和 `await old._channel.stop()`，但**没有清理 agent 对象**（`_agents`、`_channel_proxies` 字典）。
- `swarm_session.py:140` — `_agents` 在 `_run()` 开头创建，包含 4-6 个 `ConversableAgent`。每个 agent 持有 `chat_messages`（dict，每个 key 是另一个 agent，value 是消息列表）、LLM config、tool 注册等。这些在 session 结束后**全部留在内存中**，因为 `_agents` 和 `_channel_proxies` 从未被主动清理。
- `swarm_session.py` 没有 `__del__`、`dispose()`、`close()` 方法。整个 session 对象及其所有 agent 在 `_cleanup_session` 后虽然从 `_sessions` 移除，但如果其他地方还有引用（如 asyncio.Task 闭包），则无法被 GC。

**修复建议：**
```python
# 在 SwarmSession 中添加 dispose 方法
async def dispose(self) -> None:
    """Release all resources held by this session."""
    self._agents.clear()
    self._channel_proxies.clear()
    self._resume_messages.clear()
    self._prompt = ""
    await self._channel.stop()

# 在 session_manager._cleanup_session 中调用
def _cleanup_session(self, chat_id: str) -> None:
    session = self._sessions.pop(chat_id, None)
    if session:
        asyncio.create_task(session.dispose())
```

---

### 2. `_monitor_messages` 的 `asyncio.sleep(1)` 轮询开销

**严重程度：中**

**问题分析：**

- `swarm_session.py:363-379` — 每 1 秒轮询一次 `primary.chat_messages`。这个轮询**持续整个 session 生命周期**（可能几十分钟到几小时）。
- 每次轮询遍历 `primary.chat_messages.items()`（group chat 中通常 4-6 个 key），对每个 key 做 `msgs[self._pushed_count:]` 列表切片。
- **在 agent 不活跃期间（如等待用户回复）**，这个轮询完全是空转，每次创建一个空列表然后丢弃。
- 但 `asyncio.sleep(1)` 本身不会阻塞事件循环（它是非阻塞的），所以主要开销是**持续的 CPU 唤醒和列表切片操作**，不是事件循环阻塞。
- 随着消息数增长，`msgs[self._pushed_count:]` 的切片会在大列表上创建切片对象。

**修复建议：**
- 用 `asyncio.Event` 替代轮询。在 agent 产生消息时 set event，monitor 等待 event：
```python
# 替代轮询：用事件驱动
self._message_event = asyncio.Event()

async def _monitor_messages(self) -> None:
    while not self._terminated:
        await self._message_event.wait()
        self._message_event.clear()
        # 处理消息...
        # 在 agent 的 hook 或 _push_message 后 set event
```

---

### 3. MCP 连接管理：每次 session 是否新建连接

**严重程度：低**

**问题分析：**

- `mcp/manager.py` — `McpManager` 是**全局共享**的，连接在应用启动时建立（`connect()`），所有 agent 复用同一个 `ClientSession`。
- `tool_bridge.py:33-66` — `register_tools_for_agent` 只是在 agent 上注册工具的函数引用，底层调用的是共享的 `mcp_manager.call_tool()`，不创建新连接。
- `mcp/manager.py:96-132` — `call_tool` 使用 `asyncio.wait_for` 包裹，有超时保护。多个 agent 调用同一 MCP server 的工具时，通过同一个 `ClientSession` 串行化。
- **但 MCP 的 stdio transport 本质是进程级管道**，一个 session 对应一个子进程。如果 MCP server 本身泄漏或变慢，会影响所有依赖它的 agent。
- **没有连接健康检查**：如果 MCP 子进程崩溃，session 不会被清理，后续调用会报错但不恢复。

**修复建议：**
- 添加定期健康检查（如 `session.list_tools()` 探活）
- 添加自动重连机制
- 当前架构本身不是性能瓶颈，优先级较低

---

### 4. asyncio 事件循环是否被阻塞

**严重程度：高**

**问题分析：**

- `swarm_session.py:183-187` — `a_initiate_group_chat` 是 AG2 的核心调用，它内部会串行调用多个 LLM API。**每次 LLM 调用都是 await 的 HTTP 请求**，理论上不会阻塞事件循环。
- 但 `_monitor_messages` 和 `a_initiate_group_chat` 在**同一个事件循环中并行运行**（monitor_task 和 _run task）。monitor 每 1 秒执行一次 `primary.chat_messages.items()` 遍历 + 列表切片，如果 `chat_messages` 很大（数百条消息），这个操作可能在 GC 压力大时产生延迟。
- `channel_feishu_service.py:56` — `wait_reply` 用 `asyncio.wait_for(future, timeout=3600)` 等待用户回复，最长 1 小时。这不会阻塞事件循环（它只是一个挂起点），但**占用的 Future 和回调会留在内存中**。
- **真正的阻塞风险在 LLM API 调用**：如果使用同步 HTTP 客户端（如 `requests` 而非 `httpx`/`aiohttp`），会阻塞整个事件循环。需要确认 AG2 内部的 LLM 调用是否为真异步。
- `session_manager.py:160` — `await old._channel.stop()` 在 `_create_session` 中被调用，如果 `_channel.stop()` 内部有耗时的清理操作，会阻塞 `handle_message` 的处理。

**修复建议：**
- 确认 AG2 的 LLM 客户端使用异步 HTTP
- 给 `handle_message` 中的异步操作加超时
- 监控事件循环延迟：`loop.call_later(1, callback)` 检测实际延迟

---

### 5. agent 的 `chat_messages` 随轮次增长

**严重程度：高**

**问题分析：**

这是**最可能的根因**。在 AG2 的 group chat 中：
- 每个 agent 都维护一个 `chat_messages: dict[Agent, list[dict]]`，记录它与其他所有 agent 的对话。
- 在 swarm 模式下，有 4 个 AI agent + 4 个 channel proxy = 8 个 agent。
- 每个 agent 的 `chat_messages` 会包含**所有 group chat 消息的完整副本**。
- 以 `max_rounds=15` 为例，每轮可能产生多条消息（LLM 输出 + tool calls + tool responses + transfer），实际消息数可能达到 **100-300 条**。
- `swarm_session.py:374` — `_monitor_messages` 每 1 秒遍历 `primary.chat_messages.items()`，这是一个 dict，每个 value 是消息列表。随着消息增长，这个遍历 + 切片操作开销增大。
- **如果 `context.auto_compact_enabled=False`（默认为 True）**，消息会无限增长。即使 auto_compact 开启，在触发压缩阈值之前，内存中仍保留所有历史消息。
- `config.py:73-78` — `ContextConfig` 的 `max_messages=60`、`max_tokens=80000` 是压缩触发条件，但 AG2 的 `TransformMessages` 是在**回复生成前**压缩，不影响内存中 `chat_messages` 的增长。

**修复建议：**
- 确保 `context.enabled=True` 和 `auto_compact_enabled=True`
- 调低 `max_messages` 阈值（如 30-40）
- 在 `_monitor_messages` 中不需要遍历所有 `chat_messages.items()`，只需检查总数变化

---

### 6. channel_proxy 的 polling 机制

**严重程度：低（Feishu 模式）/ 中（其他模式）**

**问题分析：**

- `channel_proxy.py:89-100` — Feishu 模式使用 `ChannelFeishuService.wait_reply()`，内部是 `asyncio.wait_for(future, timeout)`，**不轮询**，是事件驱动的。这是正确的实现。
- Legacy 路径（email/dingtalk）使用 `while time.monotonic() < deadline: await asyncio.sleep(polling_interval)`，默认 30 秒轮询。如果 `polling_interval` 配得小，会有不必要的轮询开销。
- `channel_feishu_service.py:32` — `_pending_futures` 字典只在 `wait_reply` 的 `finally` 中清理（`self._pending_futures.pop(request_id, None)`）。如果 `wait_for` 超时，future 会在 finally 中被 pop。但如果 agent 异常退出，future 可能不会被清理（`stop()` 方法会处理，但需要被调用）。
- **在 Feishu 模式下，这个模块不是性能瓶颈**。

**修复建议：**
- 当前 Feishu 实现已优化（Future-based），无需大改
- 确保 `stop()` 在所有退出路径上被调用
- 给 legacy 路径的 `_polling_interval` 设合理下限

---

## 优先级排序修复清单

| 优先级 | 问题 | 严重程度 | 预估影响 |
|--------|------|----------|----------|
| **P0** | agent `chat_messages` 无限增长 | 高 | 长会话直接导致内存溢出、GC 压力剧增、事件循环延迟 |
| **P0** | session/agent 资源无 dispose | 高 | 已完成 session 的 agent 对象、消息列表、tool 注册全部留在内存 |
| **P1** | 事件循环可能被阻塞 | 高 | 所有异步操作变慢，用户感受"无反应" |
| **P2** | `_monitor_messages` 轮询开销 | 中 | 持续 CPU 唤醒，随消息增长切片开销增大 |
| **P3** | channel_proxy legacy 轮询 | 低/中 | 仅影响非 Feishu 渠道 |
| **P4** | MCP 连接健康检查 | 低 | 当前不是瓶颈，但影响可靠性 |

### 核心结论

**用户反馈的"server 长时间运行后变迟钝"最可能的根因是：**

1. **多个 session 累积的 agent 对象和 chat_messages 没有被释放**（P0），导致内存持续增长
2. **GC 压力增大后，事件循环延迟增加**（P1），所有异步操作（包括用户消息处理）变慢
3. **`_monitor_messages` 在大消息列表上每秒做切片操作**（P2），进一步加剧延迟

**建议立即着手 P0 + P1 的修复**，即添加 session dispose 机制 + 验证 context 压缩是否生效 + 监控事件循环延迟。
