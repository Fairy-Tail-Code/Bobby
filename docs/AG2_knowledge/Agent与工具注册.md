# AG2 Agent 与工具注册

## ConversableAgent

所有 Agent 的基类，核心参数：

```python
ConversableAgent(
    name="AgentName",
    system_message="系统提示词",
    description="Agent 描述（GroupChat/Swarm 用于选择 agent）",
    llm_config={"config_list": [{"model": "...", "base_url": "...", "api_key": "..."}], "temperature": 0.7},
    human_input_mode="NEVER",  # ALWAYS | TERMINATE | NEVER
)
```

### 关键方法
- `agent.system_message` — 获取当前 system message（字符串）
- `agent.update_system_message(new_text)` — 更新 system message
- `agent.name` — Agent 名称

## 工具注册（Tool Registration）

### 方式一：AG2 Tool 类（适合动态注册）
```python
from autogen.tools import Tool

def my_func(query: str) -> str:
    return "result"

tool = Tool(
    name="tool_name",
    description="What it does",
    func_or_tool=my_func,
    parameters_json_schema={"type": "object", "properties": {"query": {"type": "string"}}},
)
tool.register_for_llm(agent)       # 注册给 LLM 调用
tool.register_for_execution(agent) # 注册执行函数
```

### 方式二：装饰器（适合静态定义）
```python
@agent.register_for_llm(description="What it does")
@agent.register_for_execution()
def tool_func(query: str) -> str:
    return "result"
```

## MCP 工具集成

MCP 工具是异步的（`mcp` SDK），AG2 工具执行可能是同步的。桥接方式：

```python
def create_sync_tool_func(mcp_manager, server_name, tool_name):
    """包装异步 MCP 调用为同步函数"""
    def tool_func(**kwargs):
        coro = mcp_manager.call_tool(server_name, tool_name, kwargs)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)
    tool_func.__name__ = tool_name
    return tool_func
```

## LLM Config

支持 OpenAI 兼容接口：
```python
llm_config = {
    "config_list": [{
        "model": "model-name",
        "base_url": "http://localhost:11434/v1",
        "api_key": "key",
    }],
    "temperature": 0.7,
}
```
