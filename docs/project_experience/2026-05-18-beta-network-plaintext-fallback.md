# 2026-05-18 AG2 beta network 纯文本回复降级修复

## 背景

专家模式迁到 beta network 后，对支持 schema 的后端会直接使用 `response_schema=NetworkTurn`。  
但在 DeepSeek 这类不支持 `response_format=json_schema` 的后端上，只能退回到：

- prompt 明示 JSON contract
- runtime 本地解析 `message / next_step`

这条降级链路此前只覆盖了“模型愿意输出 JSON”这一种情况。

## 问题

实际运行中，PM 首轮可能仍然按原始角色 prompt 的习惯先输出自然语言，例如：

```text
[PM] 你好！我是这个开发团队的产品经理……
你想做一个什么样的项目？
```

而 `orchestration/network_runtime.py` 的字符串解析逻辑此前只有：

1. 尝试从文本里提取 JSON object
2. 交给 `NetworkTurn.model_validate_json()`
3. 失败后直接抛 `ValueError`

这会让一个本质上“只是没按 JSON 外壳输出”的首轮提问，直接升级成 session 级故障。

## 处理

本次修复分成两层：

### 1. 收紧非 schema contract

在 `agents/beta_factory.py` 中，对非 schema 后端补充更强的输出约束：

- 只输出单个 JSON object
- 不要输出 `[PM]` / `[Planner]` 这类身份前缀
- 不要先寒暄再补 JSON
- 给出明确的正确示例

### 2. runtime 增加纯文本安全降级

在 `orchestration/network_runtime.py` 中：

- `_coerce_network_turn()` 增加 `role_key`
- 当字符串不是合法 JSON 时，不再立刻报错
- 先尝试基于纯文本内容推断安全的 `next_step`

当前实现优先覆盖高频且低风险的情形：

- 只要文本明显是在向人提问，就降级为 `ask_user`
- PM 角色的纯文本首轮默认优先按 `ask_user` 处理
- 角色前缀如 `[PM]` 会在落 transcript 前被清掉

这样即使模型偶发忘记输出 JSON，编排层也仍能继续把问题转给用户，而不是直接炸掉会话。

## 文件

- `orchestration/network_runtime.py`
- `agents/beta_factory.py`
- `tests/test_network_runtime.py`
- `tests/test_beta_factory.py`

## 验证

使用现有运行环境的 `.venv` 直接调用测试函数，已通过：

- `test_network_runtime_runs_full_swarm_flow`
- `test_network_runtime_rejects_invalid_next_step_for_role`
- `test_network_runtime_parses_plain_json_for_schema_incompatible_backend`
- `test_network_runtime_falls_back_to_plain_text_question_for_pm`
- `test_swarm_network_agents_disable_response_schema_for_deepseek`
- `test_swarm_network_agents_keep_response_schema_for_openai_compatible_backends`

## 经验

1. “不支持 schema”不等于“模型会稳定 obey prompt JSON contract”。
2. beta network 的降级路径不能只做 JSON 解析，还要考虑模型偶发回自然语言时的应用层容错。
3. 首轮 PM 提问属于高频路径，优先把它做成可恢复场景，能显著降低实际服务化运行时的崩溃率。
