# AG2 Beta 工具参数校验

## 背景

在本项目里，beta network 模式下的工具注册走的是：

- `autogen.beta.tools.final.function_tool.tool`
- `FunctionTool`

它和 legacy `autogen.tools.Tool` 的差异之一，是 beta 工具执行链会更强依赖 Python 函数签名本身。

## 为什么会踩坑

beta 工具调用链里同时存在三件事：

1. 框架会注入内部上下文参数，例如 `__ctx__`
2. fast_depends 会根据函数签名生成参数依赖模型
3. Pydantic 会据此校验实际传入的 tool call 参数

因此，如果函数签名只声明了业务参数，却没有为 `__ctx__` 预留落点，beta 在执行时就可能出现：

- 额外字段校验失败
- 参数绑定失败

## 在 MCP 动态工具桥中的特殊性

MCP tool 的参数不是静态写死在代码里的，而是运行时从每个 MCP server 的 `inputSchema` 里发现的。

这意味着：

- 不能手写固定函数签名
- 也不能一直偷懒只用 `**kwargs`

原因是只用 `**kwargs` 虽然能吞掉 `__ctx__`，但 beta 侧拿不到稳定的显式参数定义，参数验证与推断会退化。

## 落地原则

在 beta MCP 工具桥里，正确做法是：

1. 从 `input_schema.properties` 和 `required` 动态提取参数
2. 生成显式的 keyword-only async 函数签名
3. 无论是否有业务参数，都保留 `**kwargs` 吞掉 `__ctx__`
4. 调用 MCP server 前，只透传 schema 中真实定义过的业务参数
5. 对未提供的可选参数，不要强行传 `None`

## 推荐签名形态

有业务参数时：

```python
async def read_file(
    *,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    **kwargs,
) -> str:
    ...
```

零参数工具时：

```python
async def get_gitee_current_user(**kwargs) -> str:
    ...
```

这里的 `kwargs` 不是给 MCP server 透传任意字段，而是专门留给 AG2 beta 内部注入参数。

## 实践结论

1. beta 模式里，函数签名本身就是运行时协议。
2. “接住 `__ctx__`”和“给 beta 足够的参数类型信息”两个目标必须同时满足。
3. 零参数工具是最容易漏掉的边界场景，动态生成签名时必须单独处理。
