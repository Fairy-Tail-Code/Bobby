# AG2 Beta 事件流上下文兼容

## 背景

在当前项目使用的 AG2 beta 版本里，很多执行链路已经改为通过：

- `__ctx__`

注入运行时上下文。

这不仅影响工具函数，也影响：

- stream subscribers
- interrupters
- 历史存储回调

## 典型坑位

如果回调仍写成旧式签名：

```python
async def callback(event, context):
    ...
```

当 beta stream 以 `__ctx__` 注入时，fast_depends 会把它当成：

- 缺少必填字段 `context`

然后在 Pydantic 校验阶段直接报错。

## 在 MemoryStream 中的具体表现

`MemoryStream` 默认会订阅存储层的 `save_event`。  
如果这个默认回调仍使用旧式 `context` 参数，那么只要 stream 中真的发出 event，就可能报：

- `ValidationError`
- `context Field required`

这类问题经常会被误判成“业务 tool call 出错”，但真实根因是在事件流订阅层。

## 项目侧建议

对当前版本 beta，推荐做法是：

1. 对高频使用的 `MemoryStream` 做本地兼容包装
2. 把默认 `save_event` 订阅替换成接受 `__ctx__` 的 wrapper
3. 自己注册的 stream observer 也统一接受 `__ctx__` 或 `**kwargs`

## 验证建议

不要只测“首轮对话是否成功”，还要专门测：

- 第二轮或后续轮次的真实 tool call
- `stream.send(ToolCallEvent, Context(...))`

因为很多上下文注入问题只有在事件真正流过 stream 时才会暴露。

## 结论

1. beta 模式里的上下文注入协议横跨工具执行和事件流，不是单点问题。
2. `MemoryStream` 默认行为也可能受版本兼容影响，不能想当然认为第三方内部回调已全部迁到 `__ctx__`。
3. 服务化多轮会话里，“第二轮一用工具就炸”时，优先检查 stream subscriber 签名。
