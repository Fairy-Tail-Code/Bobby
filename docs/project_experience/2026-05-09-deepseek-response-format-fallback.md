# 2026-05-09 DeepSeek `response_format` 兼容降级

## 背景

专家模式迁到 AG2 beta network 后，四个角色 agent 统一使用：

- `autogen.beta.Agent`
- `OpenAIConfig`
- `response_schema=NetworkTurn`

这会让 `autogen.beta` 在 `chat.completions.create()` 时自动附带：

- `response_format={"type":"json_schema", ...}`

当底层模型走 OpenAI 原生兼容能力时，这条链路正常；但切到 `https://api.deepseek.com/chat/completions` 后，请求首轮就会被拒绝：

- `400 Bad Request`
- `This response_format type is unavailable now`

## 根因

问题不在 beta network runtime 自身，也不在 MCP/tool 调用，而是在“结构化输出约束下沉到模型供应商接口”这一步：

1. 业务层需要 `NetworkTurn(message, next_step)` 这种结构化 contract
2. 但 DeepSeek 当前兼容接口不支持 `chat.completions.response_format=json_schema`
3. 因此不能把“结构化 contract 成立”直接等同于“供应商原生支持 schema response format”

## 修复策略

采用“双路径结构化输出”：

### 1. 支持原生 schema 的后端

- 继续保留 `response_schema=NetworkTurn`
- 保持现有 beta `AgentReply.content()` 校验链路

### 2. 不支持原生 schema 的后端（当前先覆盖 DeepSeek）

- 创建角色 agent 时不传 `response_schema`
- prompt 里继续强约束输出同样的 `message / next_step` JSON contract
- 在 `NetworkSwarmRuntime` 收到最终文本后，本地解析为 `NetworkTurn`
- 兼容纯 JSON 和 ```json 代码块包裹两种常见输出

## 文件变更

- `agents/beta_factory.py`
- `orchestration/network_runtime.py`
- `tests/test_network_runtime.py`
- `docs/AG2_knowledge/Network模式.md`
- `docs/requirement/4.9需求迭代.md`
- `AGENTS.md`

## 验证

新增回归覆盖：

- 原生 `response_schema` 路径继续走 `NetworkTurn` 解析
- schema 不可用时，runtime 可从纯文本 JSON 中恢复 `NetworkTurn`

重点确认的结果：

- DeepSeek 首轮不再因 `response_format` 报 400
- beta network 仍保持显式 `next_step` 路由
- 不影响支持原生 schema 的 OpenAI 兼容后端

## 经验

1. beta network 需要“业务结构化”，但不应无条件依赖“供应商原生结构化输出”。
2. 只要 runtime 本地仍校验 `NetworkTurn`，就能把供应商兼容性问题限制在角色创建层，而不是污染整个编排层。
3. 对 OpenAI 兼容接口做能力判断时，最好显式区分“API 形状兼容”和“高级特性兼容”。
