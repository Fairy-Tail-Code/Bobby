# 2026-05-18 PromptedSchema 代码围栏兼容

## 背景

- DeepSeek beta 路径已经切到 `PromptedSchema(NetworkTurn)`，避免 `response_format=json_schema` 与 thinking 回放问题。
- 但实际运行中，模型仍可能输出：

```json
{
  "message": "请补充需求",
  "next_step": "ask_user"
}
```

- 当前 AG2 0.11.5 的 `PromptedSchema.validate()` 会直接把整段字符串交给 `pydantic.validate_json()`。
- 一旦返回值带 markdown code fence，校验会在 `AgentReply.content()` 内部直接抛错，还没走到项目自己的 `_coerce_network_turn()` 兜底。

## 处理

- `orchestration/network_runtime.py` 不再依赖 `reply.content(retries=1)` 取得 `NetworkTurn`。
- 改为优先读取 `reply.body` 原文，然后复用项目自己的 `_coerce_network_turn()`：
  - 先去掉 markdown code fence
  - 再解析 JSON
  - 仍保留纯文本提问降级逻辑
- 如果原文仍无法解析，则额外补一次“只返回裸 JSON”的纠正请求，再尝试本地解析。

## 原则

- `PromptedSchema` 只负责给模型加结构化提示，不再假设它能完全约束最终字符串格式。
- 编排层对 `NetworkTurn` 的最终落地解析要掌握在本地 runtime 手里，避免被 markdown 包装等表层格式差异打断 session。

## 验证

- 新增回归测试：`PromptedSchema(NetworkTurn)` 返回带 ```json 围栏的响应时，`_RoleSession.ask()` 仍能解析为 `NetworkTurn`。
