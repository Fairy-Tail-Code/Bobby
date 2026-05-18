# 2026-05-18 beta network 流式消息桥接

## 背景

- AG2 beta `OpenAIClient` 在开启 `stream=True` 时，会向 `MemoryStream` 发送 `ModelMessageChunk`。
- 但当前项目的 beta network runtime 只监听了 `ToolCallEvent`，没有把增量文本转发给 frontend。
- 同时微信、飞书 gateway 的 `stream_token()` 仍是 no-op，导致多 agent 专家模式虽然底层开启了 streaming，但上层完全不可见。

## 处理

- 在 `orchestration/network_runtime.py` 中，为 `_RoleSession` 增加 `ModelMessageChunk` observer。
- observer 将 chunk 通过 `frontend.stream_token(chat_id, agent_name, token)` 转发给前端，并对失败做 best-effort 降级，只记日志不打断主流程。
- 微信、飞书 gateway 的 `stream_token()` 改为“每轮一次”的生成提示，而不是逐 token 发消息：
  - 微信：`✍️ 【PM】正在生成回复...`
  - 飞书：`✍️ PM 正在生成回复...`
- CLI frontend 增加 streamed body 去重，避免 beta network 下出现“先打印 token，再整段重复打印全文”。

## 原则

- IM gateway 不适合逐 token 真流式刷屏；可行方案是把流式链路打通后，在 gateway 层退化成低频提示。
- beta stream observer 属于观测层，失败不能反向影响 agent turn。

## 验证

- 新增 `ModelMessageChunk -> frontend.stream_token()` 回归测试。
- 新增微信 `stream_token()` 跨 loop 且单轮只提示一次的回归测试。
