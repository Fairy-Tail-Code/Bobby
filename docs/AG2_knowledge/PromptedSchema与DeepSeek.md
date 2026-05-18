# PromptedSchema 与 DeepSeek

## 背景

AG2 beta 在结构化输出上有两条路径：

1. **原生 schema 路径**
   - `response_schema=MyModel`
   - client 侧会尽量使用 provider 的原生结构化输出能力

2. **PromptedSchema 路径**
   - `response_schema=PromptedSchema(MyModel)`
   - 不依赖 provider 原生 `response_format`
   - 而是把 JSON schema 注入 prompt，再由 AG2 做最终校验

## 什么时候该用 PromptedSchema

当后端满足任一条件时，优先考虑 `PromptedSchema`：

- 不支持 `response_format=json_schema`
- 虽然“OpenAI 兼容”，但原生 structured output 不稳定
- 需要保留 AG2 beta 的 response validation，但不想自己手写一套 schema prompt

## DeepSeek 场景的额外问题

对于 `deepseek-v4-pro` 这类 thinking 模型，除了 schema 支持问题，还会有：

- thinking mode 返回 `reasoning_content`
- 后续请求要求把这段内容原样带回

而当前 `ag2==0.11.5` 的 `OpenAIConfig + chat.completions` 路径并不会自动完成这件事。

因此在当前版本里，更稳妥的做法是：

1. 把结构化输出切到 `PromptedSchema`
2. 通过 provider-specific 参数关闭 thinking mode

## 项目侧实践

本项目当前的 DeepSeek beta 路径采用：

- `response_schema=PromptedSchema(NetworkTurn)`
- `extra_body={"thinking":{"type":"disabled"}}`

而 OpenAI 兼容后端则继续保留：

- `response_schema=NetworkTurn`
- 原生 `OpenAIConfig`

## 结论

1. `PromptedSchema` 不是退而求其次的 hack，而是 AG2 官方为“非原生结构化输出后端”准备的正式路径。
2. 对 DeepSeek 这类 thinking 模型，结构化输出问题和 reasoning replay 问题要分开看。
3. 当目标是“先把项目跑通”时，`PromptedSchema + 禁用 thinking` 往往比继续硬补 client replay 更务实。
