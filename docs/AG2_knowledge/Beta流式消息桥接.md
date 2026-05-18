# Beta流式消息桥接

## AG2 beta 侧事实

- `autogen.beta.config.openai.OpenAIClient` 在 `stream=True` 时，不是直接返回完整文本。
- 它会在 `_process_stream()` 中持续向 `Context.stream` 发送 `ModelMessageChunk(content=...)`。
- 最终结束时才再发送一次完整 `ModelMessage` / `ModelResponse`。

## 对当前项目的含义

- 如果 runtime 不订阅 `ModelMessageChunk`，那即使底层模型配置了 streaming，上层 frontend 也完全感知不到。
- 如果 frontend 直接把每个 chunk 都发到 IM 网关，会造成严重刷屏，因此 gateway 层需要做能力降级。

## 推荐落地方式

1. runtime 负责桥接：
   - 订阅 `ModelMessageChunk`
   - 调用 `frontend.stream_token()`
2. frontend 负责按渠道降级：
   - CLI：真 token 流式打印
   - 微信 / 飞书：单轮一次“正在生成回复”提示
3. final full message 仍走 `send_text()`：
   - 网关用户最终看到的是一条完整回复
   - 中间只收到低频状态提示

## 注意点

- beta streaming 和最终 `send_text()` 会同时存在，CLI 需要处理重复展示问题。
- `stream_token()` 与 `on_tool_call()` 一样，属于 best-effort 观察者，不应成为 session 成败条件。
