# Cron 系统实现

本文档描述 OpenHarness 项目中 Cron 定时任务的**实际实现**。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         Agent / 用户                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MCP Tool Call
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Agent Cron MCP Server                           │
│  infrastructure/mcp_servers/agent_cron_server.py                 │
│                                                                   │
│  Tools:                                                          │
│  - schedule_task(task_id, cron_expression, prompt, mode)         │
│  - cancel_task(task_id)                                           │
│  - list_tasks()                                                   │
│  - get_task_status(task_id)                                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     TaskScheduler                                 │
│  infrastructure/cron/task_scheduler.py                           │
│                                                                   │
│  - APScheduler (AsyncIOScheduler)                                │
│  - 任务持久化 (JSON: cron_tasks.json)                            │
│  - job_id ↔ task_id 映射                                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 到达触发时间
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Runner                                  │
│  infrastructure/cron/agent_runner.py                             │
│                                                                   │
│  run_cron_task():                                                │
│  - 创建 AgentSession                                             │
│  - 等待执行完成 (3600s timeout)                                   │
│  - 保存历史记录                                                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                    AgentSession                                   │
│  infrastructure/session/agent_session.py                         │
│                                                                   │
│  - create_session_runtime()                                      │
│    ├─ single: SingleAgentRuntime                                │
│    └─ swarm: NetworkSwarmRuntime (PM → Planner → Generator...)   │
│  - 运行完成后保存快照和记忆                                       │
└─────────────────────────────────────────────────────────────────┘
```

## 文件结构

```
infrastructure/
├── cron/
│   ├── cron_task.py           # CronTask 数据类，CronTaskStatus 枚举
│   ├── task_scheduler.py      # TaskScheduler 类，核心调度逻辑
│   └── agent_runner.py        # run_cron_task()，创建并执行 Agent
├── mcp_servers/
│   └── agent_cron_server.py   # MCP Server，暴露 schedule_task 等工具
└── session/
    └── agent_session.py       # AgentSession，cron 任务复用此执行

config/
├── cron_config.py             # CronConfig 数据类，load_cron_config()
└── cron.yaml                  # 配置模板 (enabled, storage_path, timeout)

install/defaults/
└── cron.yaml                  # 默认配置

cli.py                         # 注册 agent_cron MCP server
```

## 核心组件

### 1. CronTask 数据模型

`infrastructure/cron/cron_task.py`

```python
@dataclass
class CronTask:
    task_id: str
    cron_expression: str
    prompt: str
    mode: str = "swarm"           # single 或 swarm
    chat_id: str = "cron"
    status: CronTaskStatus = CronTaskStatus.PENDING
    created_at: str = ""
    last_run_at: str = ""
    next_run_at: str = ""
    last_result: str = ""
    last_error: str = ""
    run_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
```

**状态流转**:
```
PENDING → RUNNING → PENDING (成功)
              └──→ FAILED (失败)
              └──→ CANCELLED (取消)
```

### 2. TaskScheduler

`infrastructure/cron/task_scheduler.py`

```python
class TaskScheduler:
    def __init__(self, session_manager: SessionManager, storage_path: str):
        self.scheduler = AsyncIOScheduler()      # APScheduler
        self.session_manager = session_manager    # 共享 SessionManager
        self.storage_path = Path(storage_path)   # cron_tasks.json
        self.tasks: dict[str, CronTask] = {}
        self._job_map: dict[str, str] = {}       # task_id → job_id
```

**核心方法**:

| 方法 | 说明 |
|------|------|
| `initialize()` | 加载保存的任务并启动 scheduler |
| `schedule_task()` | 创建新任务，验证 cron 表达式，添加到 scheduler |
| `cancel_task()` | 取消任务，移除 scheduler job |
| `list_tasks()` | 格式化返回所有任务列表 |
| `get_task_status()` | 返回单个任务的详细状态 |
| `_execute_task()` | 内部方法，被 scheduler 触发时调用 |

**任务执行流程** (`_execute_task`):
```python
async def _execute_task(self, task_id: str) -> None:
    task = self.tasks[task_id]
    task.status = CronTaskStatus.RUNNING
    task.last_run_at = datetime.now().isoformat()

    try:
        result = await run_cron_task(
            session_manager=self.session_manager,
            prompt=task.prompt,
            mode=task.mode,
            chat_id=task.chat_id,
            task_id=task_id,
        )
        if result["success"]:
            task.status = CronTaskStatus.PENDING
            task.last_result = result
        else:
            task.status = CronTaskStatus.FAILED
            task.last_error = result["error"]
        task.run_count += 1
    except Exception as e:
        task.status = CronTaskStatus.FAILED
        task.last_error = str(e)
    finally:
        await self._save_tasks()
```

### 3. Agent Runner

`infrastructure/cron/agent_runner.py`

```python
async def run_cron_task(
    session_manager: SessionManager,
    prompt: str,
    mode: str,
    chat_id: str,
    task_id: str,
) -> dict[str, Any]:
    # 1. 创建唯一的 chat_id 避免冲突
    task_chat_id = f"cron_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 2. 创建 AgentSession（复用主流程的执行逻辑）
    session = AgentSession(
        chat_id=task_chat_id,
        frontend=session_manager._frontend,
        mcp_manager=session_manager._mcp_manager,
        llm_config=session_manager._llm_config,
        harness_config=session_manager._harness_config,
        skill_registry=session_manager._skill_registry,
        session_dir=session_manager._session_dir,
        mode=mode,
        agent_pool=session_manager._agent_pool,
        channel_factory=session_manager._channel_factory,
    )

    # 3. 启动并等待完成（3600s 超时）
    session.start(prompt)
    await asyncio.wait_for(session.task, timeout=3600)

    # 4. 保存历史记录
    session_file = session_dir / f"cron_history_{task_id}_{timestamp}.json"
    with open(session_file, "w") as f:
        json.dump(session.transcript, f, ensure_ascii=False, indent=2)

    return {"success": True, "task_id": task_id, ...}
```

### 4. Agent Cron MCP Server

`infrastructure/mcp_servers/agent_cron_server.py`

```python
agent_cron_server = FastMCP("openharness-agent-cron", log_level="ERROR")

@agent_cron_server.tool()
async def schedule_task(
    task_id: str,
    cron_expression: str,
    prompt: str,
    mode: str = "single",
) -> str:
    """创建定时任务"""
    scheduler = get_task_scheduler()
    return await scheduler.schedule_task(task_id, cron_expression, prompt, mode)

@agent_cron_server.tool()
async def cancel_task(task_id: str) -> str:
    """取消定时任务"""
    scheduler = get_task_scheduler()
    return await scheduler.cancel_task(task_id)

@agent_cron_server.tool()
async def list_tasks() -> str:
    """列出所有任务"""
    scheduler = get_task_scheduler()
    return scheduler.list_tasks()

@agent_cron_server.tool()
async def get_task_status(task_id: str) -> str:
    """获取任务状态"""
    scheduler = get_task_scheduler()
    return scheduler.get_task_status(task_id)
```

### 5. MCP Server 配置

`install/defaults/mcp.yaml`

```yaml
agent_cron:
  transport: stdio
  command: harness
  args: ["_mcp", "agent_cron"]
  startup_timeout: 30
```

`cli.py` 中的注册:

```python
_MCP_SERVERS = {
    # ...
    "agent_cron": "infrastructure.mcp_servers.agent_cron_server",
}
```

## 配置

`config/cron_config.py`

```python
@dataclass
class CronConfig:
    enabled: bool = True
    storage_path: str = ""          # 默认 ~/.openharness/cron_tasks.json
    task_timeout: int = 3600        # 单位：秒
```

`install/defaults/cron.yaml`

```yaml
enabled: true
storage_path: "./data/cron_tasks.json"
task_timeout: 3600
```

## 数据持久化

任务保存在 JSON 文件中 (`cron_tasks.json`):

```json
{
  "tasks": [
    {
      "task_id": "daily_sync",
      "cron_expression": "0 9 * * *",
      "prompt": "同步知识库",
      "mode": "single",
      "chat_id": "cron",
      "status": "pending",
      "created_at": "2026-05-11T10:00:00",
      "last_run_at": "2026-05-11T09:00:00",
      "next_run_at": "2026-05-12T09:00:00",
      "last_result": "Completed successfully, history length: 15",
      "last_error": "",
      "run_count": 5,
      "metadata": {}
    }
  ],
  "saved_at": "2026-05-11T10:00:00"
}
```

## 与设计文档的对比

| 设计文档推荐 | 当前实现 | 状态 |
|-------------|---------|------|
| 支持 cron/interval/date 三种触发器 | 仅支持 cron 表达式 | 部分实现 |
| 支持白名单 action (agent_prompt, mcp_tool, 等) | 直接执行 prompt，复用 AgentSession | 简化实现 |
| 支持 pause/resume | 不支持，只有 cancel | 未实现 |
| 支持执行历史表 (job_runs) | 仅保存简化的 last_result/last_error | 简化实现 |
| 支持立即执行 (run_now) | 不支持 | 未实现 |
| 使用数据库持久化 | 使用 JSON 文件 | 简化实现 |
| 支持时区配置 | 使用 APScheduler 默认时区 | 隐式实现 |

## 使用示例

### Agent 创建定时任务

```python
# Agent 通过 MCP Tool 调用
result = await mcp_manager.call_tool(
    server_name="agent_cron",
    tool_name="schedule_task",
    arguments={
        "task_id": "daily_summary",
        "cron_expression": "0 9 * * *",      # 每天早上 9 点
        "prompt": "生成昨天的开发日报",
        "mode": "single"
    }
)
# 返回: "Task 'daily_summary' scheduled successfully.\nCron: 0 9 * * *\nNext run: 2026-05-12T09:00:00"
```

### 查询任务状态

```python
result = await mcp_manager.call_tool(
    server_name="agent_cron",
    tool_name="get_task_status",
    arguments={"task_id": "daily_summary"}
)
# 返回详细的任务状态信息
```

### 取消任务

```python
result = await mcp_manager.call_tool(
    server_name="agent_cron",
    tool_name="cancel_task",
    arguments={"task_id": "daily_summary"}
)
```

## 已知限制

1. **仅支持 cron 表达式**：不支持 interval 和 date 类型
2. **无暂停/恢复功能**：只有创建和取消
3. **无立即执行功能**：必须等待调度时间
4. **执行历史简化**：只保存最后一次结果
5. **JSON 持久化**：不适合高并发或分布式场景
6. **单机运行**：TaskScheduler 和 SessionManager 需要共享状态
7. **超时固定**：3600 秒硬编码在 agent_runner.py
8. **无错误重试机制**：任务失败后不会自动重试

## 待改进方向

1. **支持 interval 和 date 触发器**
2. **添加 pause/resume 功能**
3. **支持 run_now 立即执行**
4. **迁移到数据库持久化**
5. **添加重试策略**
6. **支持任务依赖**
7. **更完善的执行历史和审计日志**
8. **支持任务超时配置（非硬编码）**
9. **支持任务优先级**
10. **支持任务并发策略控制**

## 总结

当前实现是一个**最小可行版本 (MVP)** 的 Cron MCP：

- ✅ 支持通过 MCP Tool 创建/取消/查询 cron 任务
- ✅ 使用 APScheduler 实现可靠的调度
- ✅ 任务执行复用现有的 AgentSession 执行流程
- ✅ 任务持久化到 JSON 文件
- ✅ 支持 single 和 swarm 两种模式

- ❌ 功能相对简化，缺少一些高级特性
- ❌ 不适合生产环境的高可用场景

这个实现适合作为原型和轻量级使用，如果需要更强的功能，可以按照设计文档中的方向逐步扩展。
