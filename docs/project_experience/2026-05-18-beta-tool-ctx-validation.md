# 2026-05-18 AG2 beta 工具参数校验修复

## 背景

专家模式迁到 AG2 beta network 后，MCP 工具不再走 legacy `Tool.register_for_llm/register_for_execution`，而是走 beta `FunctionTool`。

beta 路径的关键差异是：

- 调用工具时会额外注入内部参数 `__ctx__`
- fast_depends 会基于函数签名构造参数模型
- Pydantic 会按这个模型校验传入参数

如果工具函数只声明业务参数、没有 `__ctx__` 或 `**kwargs`，beta 注入内部参数后就会触发校验失败。

## 问题

本次修复前，`infrastructure/mcp/beta_tool_bridge.py` 处于两个不完整状态之间：

1. 主线旧实现只有 `async def tool_func(**kwargs)`，beta 虽然能接住 `__ctx__`，但拿不到稳定的显式签名做参数推断。
2. 一版本地尝试改成动态 `exec` 生成显式签名，但对零参数工具会拼出：

```python
async def get_gitee_current_user(, **kwargs) -> str:
```

这会在 session 初始化阶段直接触发 `SyntaxError`，导致整个专家模式起不来。

此外，如果简单给可选参数设置 `= None` 并原样透传到 MCP server，还会把“用户没传这个字段”错误变成“显式传了 null”。

## 处理

本次对 beta MCP 工具桥做了三件事：

1. 从 MCP `input_schema.properties/required` 动态提取参数定义
2. 生成显式 keyword-only async 签名，并始终保留 `**kwargs`
3. 构造调用参数时过滤掉 beta 内部注入项和未提供的可选参数

实现要点：

- 有参数时生成：`async def tool(*, path: str, start_line: int | None = None, **kwargs)`
- 无参数时生成：`async def tool(**kwargs)`
- `kwargs` 只用于吞掉 `__ctx__` 这类 beta 内部字段，不参与 MCP 入参透传
- 最终下发给 `mcp_manager.call_tool()` 的参数字典只包含 schema 里定义过、且本次实际提供的字段

## 文件

- `infrastructure/mcp/beta_tool_bridge.py`
- `tests/test_beta_tool_bridge.py`
- `docs/requirement/4.9需求迭代.md`

## 验证

新增回归覆盖：

- 零参数工具 + `__ctx__` 注入
- 含可选参数工具，未提供可选字段时不透传 `None`

本地环境未安装 `autogen`，因此没有完成完整 pytest 执行；本次先用代码级回归测试和语法检查确保变更闭环。

## 经验

1. beta `FunctionTool` 不是简单替换 legacy `Tool` 的 import，函数签名本身就是协议的一部分。
2. 处理内部注入参数时，不能只想着“能接住”；还要保证这些内部字段不会混进真正的 MCP 参数字典。
3. 动态生成函数时，零参数场景必须单独处理，否则很容易拼出 `func(, **kwargs)` 这类只在运行时暴露的语法错误。
