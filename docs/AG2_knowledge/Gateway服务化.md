# Gateway 服务化

## 结论

AG2 在服务化场景下，不能假设“所有异步代码都跑在同一个事件循环里”。

典型结构是：

- gateway 主事件循环：负责 WebSocket、long polling、HTTP client session、消息收发
- AG2 工作线程事件循环：`a_run_group_chat_iter()` / `a_get_human_input()` 等内部执行上下文

一旦某个 gateway SDK、`aiohttp.ClientSession`、或 `asyncio.Future` 与创建它的 loop 绑定，就必须显式做跨线程桥接。

## 本项目里的具体场景

### 微信 gateway

- `WeixinBotService._poll_loop()` 在主 loop 中创建 `aiohttp.ClientSession`
- `ChannelUserProxyAgent.a_get_human_input()` 可能在 AG2 内部线程 loop 中执行
- 如果该线程直接 `await self._session.post(...)`，会触发 `aiohttp` 的 loop 绑定错误

修复方式：

- 在 `WeixinBotService.send_text()` 内判断当前 loop
- 若不是 bot 主 loop，则使用 `asyncio.run_coroutine_threadsafe(...)` 把真正发送调度回主 loop

### 服务化 HITL 回复注入

- pending reply 的 `Future` 通常是在 AG2 工作线程 loop 中创建
- gateway 收到用户回复后，往往是在主 loop 中处理
- 主 loop 不能直接 `future.set_result(...)` 或 `future.cancel()`

正确方式：

- 使用 `future.get_loop().call_soon_threadsafe(...)`
- 把 `set_result()` / `cancel()` 调度回 Future 自己所属的 loop

## 设计原则

1. 网络客户端在哪个 loop 创建，就只在哪个 loop 使用。
2. 服务化 gateway 向 AG2 暴露的是“线程安全的桥接接口”，不是底层 session 本身。
3. 跨线程交付结果时，只传值，不直接操作另一个 loop 的异步原语。

## 常见信号

如果看到下面这些报错，优先检查是否跨 loop 误用了异步资源：

- `RuntimeError: Timeout context manager should be used inside a task`
- `attached to a different loop`
- `Non-thread-safe operation invoked on an event loop other than the current one`
