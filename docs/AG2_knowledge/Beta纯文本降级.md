# AG2 Beta 纯文本降级

## 背景

在 beta network 模式下，理想状态是每个角色都返回结构化 `NetworkTurn`：

```json
{"message":"...","next_step":"..."}
```

对支持 `response_format=json_schema` 的后端，这通常可以靠 `response_schema` 强约束。  
但在不支持 schema 的兼容后端上，项目只能改为“prompt 约束 + runtime 本地解析”。

## 核心风险

只靠 prompt 约束时，模型仍可能偶发输出：

- 自然语言寒暄
- 身份前缀，例如 `[PM]`
- 纯文本问题，而不是 JSON object

如果 runtime 只会做 `model_validate_json()`，这类输出会直接触发：

- `json_invalid`
- session 中断

## 推荐做法

beta network 的非 schema 路径应该至少有两层防线：

1. **Prompt 层**
   - 明确要求只输出单个 JSON object
   - 明确禁止 `[PM]` / `[Planner]` 身份前缀
   - 给出正确示例，而不是只写抽象规则

2. **Runtime 层**
   - 先尝试正常 JSON 解析
   - 失败后，基于角色和文本内容做有限、安全的纯文本降级

## 适合降级的场景

优先处理这些低风险高频场景：

- PM 首轮向用户提问
- 其他角色明确向用户提问
- Evaluator 明确表达“验收通过”

原因是这些场景的意图相对单一，推断错误成本较低。

## 不适合激进猜测的场景

下面这些不建议做过强推断：

- Planner / Generator 的复杂 handoff 语义
- 多步交接混在一段自由文本里
- 同时包含“提问用户”和“交给下一个角色”的模糊表达

这类情况如果无法可靠判断，宁可保留报错，也不要让 runtime silently route 到错误角色。

## 实践结论

1. beta network 的“文本 JSON 降级”本质上也是协议设计，不只是解析技巧。
2. 服务化场景里，runtime 容错比实验环境更重要；高频首轮问答不应因为格式问题直接炸掉。
3. 对不支持 schema 的后端，prompt 强约束和 runtime 轻量兜底要同时存在。
