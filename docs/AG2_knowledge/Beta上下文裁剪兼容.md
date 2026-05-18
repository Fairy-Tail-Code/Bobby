# Beta上下文裁剪兼容

## 背景

- 仓库里原先有两套上下文治理：
  - legacy `snip.py / auto_compact.py`
  - beta `HistoryLimiter / TokenLimiter`
- 其中 `snip.py` 挂在 `TransformMessages` 上，只对旧 `ConversableAgent` 生效。
- beta middleware 是另一条完全不同的执行链。

## 关键结论

- `snip.py` 和 beta limiter 在概念上都属于“裁剪上下文”，但它们不是同一运行链路，也不会在同一个 beta agent 上自动双重生效。
- beta 路径不能直接复用 legacy `MessageHistoryLimiter`，因为接口层不同。

## beta 路径的额外约束

- beta 事件历史里存在：
  - `ModelResponse(tool_calls=...)`
  - `ToolResultsEvent(...)`
- 如果裁剪时把这两类事件拆开，就会产生孤儿 `tool` 消息。
- OpenAI 兼容接口会直接报：
  - `Messages with role 'tool' must be a response to a preceding message with 'tool_calls'`

## 推荐落地

1. beta 路径使用独立 middleware，而不是复用 legacy transform。
2. 裁剪时把以下事件视为一个不可拆分 segment：
   - 一个带 `tool_calls` 的 `ModelResponse`
   - 后续连续的 `ToolResultsEvent`
3. 当预算不足时，可以少保留一些普通历史，但不能输出无效的 tool-call 序列。
