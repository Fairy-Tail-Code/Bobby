# 2026-05-09 微信 HITL 跨事件循环修复

## 背景

微信 gateway 在 `SwarmSession -> ChannelUserProxyAgent.a_get_human_input() -> ChannelWeixinService.send() -> WeixinBotService.send_text()` 这条链路上报错：

`RuntimeError: Timeout context manager should be used inside a task`

触发条件是：

- `WeixinBotService._poll_loop()` 在 gateway 主事件循环中启动，并创建 `aiohttp.ClientSession`
- AG2 的 group chat 在内部线程中使用独立事件循环执行 `a_get_human_input()`
- 该线程中的 coroutine 直接 `await` 了主 loop 创建的 `aiohttp.ClientSession.post(...)`

`aiohttp` 的 session / timeout 上下文与创建它的 loop 强绑定，跨 loop 复用就会报错。

## 根因

这不是“微信工具又建立了一个多余事件循环”，而是 AG2 框架本身会把 group chat 放到线程里的独立事件循环执行。于是服务化 gateway 模式天然存在两个异步边界：

1. AG2 工作线程事件循环
2. gateway 主事件循环

问题点有两个：

1. 微信发送直接跨 loop 复用 `aiohttp.ClientSession`
2. HITL reply 的 `Future` 在 AG2 线程里创建，却在主 loop 里直接 `set_result()`

## 方案

### 1. 微信发送统一回到 bot 主 loop

在 `gateway/weixin/weixin_bot.py` 中新增主 loop 桥接：

- `send_text()` 不再直接操作 `self._session`
- 若当前调用 loop 不是 `self._main_loop`，使用 `asyncio.run_coroutine_threadsafe(...)`
- 在调用方侧通过 `await asyncio.wrap_future(...)` 等待主 loop 完成发送

这样 `aiohttp.ClientSession` 只会在创建它的 loop 中被使用。

### 2. 服务化 channel 的 Future 注入改为线程安全

在 `gateway/weixin/channel_weixin_service.py` 与 `gateway/feishu/channel_feishu_service.py` 中：

- `inject_reply()` 改为 `future.get_loop().call_soon_threadsafe(...)`
- `stop()` 中的 `future.cancel()` 也改为调度回 Future 所属 loop

这样主 loop 收到网关用户回复后，不会再直接跨线程操作另一个 loop 的 `Future`。

## 涉及文件

- `gateway/weixin/weixin_bot.py`
- `gateway/weixin/channel_weixin_service.py`
- `gateway/feishu/channel_feishu_service.py`
- `tests/test_gateway_threading.py`
- `docs/requirement/4.9需求迭代.md`

## 验证

本地执行了两类验证：

1. 语法检查：四个变更文件全部 `compile(..., 'exec')` 通过
2. 手工回归脚本：
   - 模拟主 loop 在后台线程运行
   - 从另一个事件循环调用 `WeixinBotService.send_text()`
   - 确认真实发送逻辑落在主 loop 线程执行
   - 确认微信/飞书 channel 的 `inject_reply()` 都能跨线程安全唤醒等待中的 `Future`

## 经验

- AG2 的 `a_run_group_chat_iter()` 不能默认假设所有 agent hook 都与 gateway 共用一个事件循环
- 只要服务端 SDK 或客户端 session 对 loop/thread 有绑定语义，就必须显式建立“回主 loop 执行”的桥接层
- `asyncio.Future` 不是线程安全对象，跨线程只能通过 `future.get_loop().call_soon_threadsafe(...)` 间接操作
