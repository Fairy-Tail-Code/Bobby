# 2026-05-18 AG2 beta stream `__ctx__` 回调兼容修复

## 背景

前面已经修过两层 beta network 兼容问题：

- 工具函数参数签名要兼容 `__ctx__`
- 非 schema 后端的纯文本回复需要 runtime 降级

但实际服务化运行中又出现了新的阶段性故障：首轮问答正常，第二轮一旦真的发生 tool call，session 就在 beta stream 链路里报错退出。

## 问题

报错表面上出现在：

- `orchestration/network_runtime.py::_on_tool_call`

异常是：

- `ValidationError`
- `context Field required`

进一步验证后发现，问题不只在我们自己的前端观察者回调，当前安装的 AG2 beta 版本里 `MemoryStream` 默认还会：

- `self.subscribe(storage.save_event)`

而 `MemoryStorage.save_event()` 的签名仍是：

```python
async def save_event(self, event, context)
```

但是 beta stream 在运行时实际注入的是：

- `__ctx__`

这意味着只要 tool event 真正进入 stream，默认存储订阅和我们自己的订阅回调都会被 fast_depends 当场校验失败。

## 处理

本次没有直接改第三方包，而是在项目侧做了本地兼容封装：

### 1. 为角色会话创建兼容 stream

新增 `_create_compat_memory_stream()`：

- 先创建原始 `MemoryStream`
- 取出 `stream.history.storage`
- 清掉默认 `_subscribers`
- 重新注册一个 `save_event_compat(event, __ctx__=...)`

这样保留了原有 history 能力，同时把默认存储订阅改成兼容当前 beta 注入方式的版本。

### 2. 修正前端工具事件观察者

`_on_tool_call()` 改为：

- 接收 `__ctx__`
- 允许额外 `**kwargs`

避免我们自己的观察者再次复现同类问题。

## 文件

- `orchestration/network_runtime.py`
- `tests/test_network_runtime.py`

## 验证

新增回归：

- 直接构造 `_RoleSession`
- 手动 `stream.send(ToolCallEvent, Context(...))`
- 校验：
  - 不再抛 `context Field required`
  - event 成功写入 `stream.history`
  - `frontend.on_tool_call()` 正常收到通知

同时复跑了此前的：

- beta network 主链路
- 非 schema JSON 降级
- 纯文本提问降级
- beta tool `__ctx__` 参数兼容

## 经验

1. beta `__ctx__` 兼容不能只修业务工具函数，事件流订阅回调也属于同一套协议面。
2. 这类问题很容易表现成“第一轮正常，第二轮一用工具就炸”，因为只有真正产生 stream event 时才会触发。
3. 对当前版本 AG2 beta，更稳妥的做法是项目侧把高频依赖点先包一层兼容适配，而不是假设第三方内部所有回调都已经迁到同一注入约定。
