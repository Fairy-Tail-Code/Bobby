# PromptedSchema 代码围栏兼容

## 现象

- AG2 beta 的 `PromptedSchema` 会把 JSON schema 注入 prompt。
- 但在 `validate()` 阶段，它仍直接调用内部 schema 的 `validate_json()`。
- 如果模型返回 ` ```json ... ``` `，哪怕内部 JSON 完全合法，也会被当成“不是 JSON 字符串”而失败。

## 结论

- `PromptedSchema` 解决的是“没有原生 structured output 能力”的问题。
- 它不保证模型输出一定是裸 JSON。
- 对这类 provider，runtime 最好基于原始 `reply.body` 再做一次本地清洗和解析，不要把最终成功与否完全交给 `AgentReply.content()`。

## 在当前项目中的落地

1. `beta_factory.py` 继续让 DeepSeek 使用 `PromptedSchema(NetworkTurn)`。
2. `network_runtime.py` 在角色会话层读取 `reply.body` 原文。
3. 先用本地 `_extract_json_object()` 去围栏，再解析 `NetworkTurn`。
4. 解析失败时再补一次“只返回裸 JSON”的纠正请求。

## 适用边界

- 这套兼容只针对 beta network 的结构化 `NetworkTurn` 响应。
- 不改变普通文本回复和原生 `response_format=json_schema` provider 的基础行为。
