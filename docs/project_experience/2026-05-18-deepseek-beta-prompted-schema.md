# 2026-05-18 DeepSeek beta 路径切回 AG2 推荐用法

## 背景

在继续保留 AG2 的前提下，DeepSeek 路径此前已经暴露出三类问题：

1. 非 schema 输出需要 prompt JSON contract 降级
2. beta 事件流中的 `__ctx__` 注入需要兼容
3. `deepseek-v4-pro` 在 thinking mode 下会要求后续请求回传 `reasoning_content`

第三类问题是关键阻塞点，因为它已经不只是业务层兼容，而是当前 `ag2==0.11.5` 的 OpenAI chat-completions 客户端能力边界。

## 问题

本地 AG2 版本的事实状态是：

- `OpenAIConfig` 走 `chat.completions.create`
- 当前实现不会在后续消息回放中传回 `reasoning_content`
- `OpenAIConfig` 本身也没有暴露 `extra_body` 字段

但项目旧的非 beta 链路其实已经验证过一个更稳妥的 DeepSeek 配置：

```json
{
  "extra_body": {
    "thinking": {
      "type": "disabled"
    }
  }
}
```

这说明与其继续在 AG2 0.11.5 里硬补 reasoning replay，不如先把 beta 路径拉回到一个更贴近 AG2 推荐能力、同时又兼容 DeepSeek 的最小实现。

## 处理

### 1. 非原生结构化输出改用 PromptedSchema

此前 DeepSeek 路径是：

- `response_schema=None`
- 手写 prompt JSON contract
- runtime 再做 `_coerce_network_turn()`

本次改为：

- `response_schema=PromptedSchema(NetworkTurn)`

这样结构化输出约束回到 AG2 beta 自带能力，而不是项目侧手写一套 schema prompt 机制。

### 2. 新增 DeepSeekOpenAIConfig

新增本地轻量配置类 `DeepSeekOpenAIConfig`，只做一件事：

- 在 `chat.completions.create` 时透传：
  - `extra_body={"thinking":{"type":"disabled"}}`

它不替代整个 AG2 client，只是补齐当前 `OpenAIConfig` 在 0.11.5 版本里缺失的 provider-specific 参数入口。

## 文件

- `infrastructure/llm/deepseek_beta_config.py`
- `agents/beta_factory.py`
- `tests/test_beta_factory.py`

## 验证

本地回归覆盖了以下关键点：

- DeepSeek 角色 agent 使用 `DeepSeekOpenAIConfig`
- DeepSeek 角色 response schema 变为 `PromptedSchema`
- `config.create()._create_options` 中包含 `extra_body.thinking.disabled`
- 既有 network/tool 回归不受影响

## 经验

1. 保留 AG2 不等于必须死守 `OpenAIConfig` 原样。对 provider-specific 参数做薄适配，成本远低于重写 runtime。
2. 对不支持原生 `response_format` 的后端，`PromptedSchema` 比手写 JSON contract 更贴近 AG2 官方路径。
3. 当前阶段目标应当是“项目先可用”，不是为了形式上的纯框架使用而放任协议不匹配长期存在。
