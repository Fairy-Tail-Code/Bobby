# 2026-05-18 工具调用通知降级

## 背景

- AG2 beta network 第二轮真实触发 tool call 后，`ToolCallEvent` 会经过 `_RoleSession._on_tool_call()` 通知前端。
- 微信网关在发送“正在执行工具”提示时，腾讯 iLink 偶发返回 `ret=-2 errmsg=unknown`。
- 当前实现会把这个通知异常直接向上抛回 beta stream，导致工具本身已经开始执行，但整条 session 被通知链路打断。

## 处理

- 在 `orchestration/network_runtime.py` 的 `_RoleSession._on_tool_call()` 中，将前端 `on_tool_call` 改为 best-effort。
- 如果前端通知失败，只记录 `warning` 日志，不再让异常传播回 AG2 beta 的 stream / executor。
- 保持 `MemoryStream` history 继续写入 `ToolCallEvent`，避免因为通知失败丢失事件历史。

## 原则

- 工具调用通知属于观测性副作用，不应成为 tool execution 的成败条件。
- 真正面向用户的主回复仍保持原有发送语义；本次只对 tool-call toast / 提示类消息降级。

## 验证

- 新增回归测试：当前端 `on_tool_call` 主动抛错时，`role_session.stream.send(ToolCallEvent)` 仍能完成，且 history 中保留工具事件。
