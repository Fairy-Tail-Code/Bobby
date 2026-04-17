# 飞书产品化服务设计

> 日期: 2026-04-17
> 状态: 已确认

## 目标

将 AG2 OpenHarness 从 CLI 工具改造为飞书机器人服务，实现：
- 常驻服务器运行，用户通过飞书交互
- 单进程多协程并发，每个用户/群聊独立 swarm 会话
- 保留多角色 HITL（PM/Planner/Generator/Evaluator 各有 channel proxy）
- 用户可见全部 agent 对话流，工具调用显示为"正在执行 xxx"
- 支持群聊和单聊两种模式
- 支持终止任务（暂停暂不支持）
- 不考虑用户注册

## 架构

### 方案选择

**FastAPI + asyncio 会话池**（方案 A）

```
飞书用户 <--WS/REST--> FastAPI 服务 <---> SessionManager
                                       ├── session_1: [PM, Planner, Generator, Evaluator, channel_proxies]
                                       ├── session_2: [...]
                                       └── session_3: [...]
```

理由：改动最小，复用现有 ChannelUserProxyAgent + FeishuChannel 架构，只需加路由层和会话管理层。

### 组件结构

```
server.py (FastAPI)
  ├── FeishuBotService          # 飞书消息收发 + 路由
  ├── SessionManager            # 会话生命周期管理
  │     ├── sessions: dict[chat_id, SwarmSession]
  │     ├── create_session(chat_id, user_input)
  │     ├── get_or_create(chat_id)
  │     └── terminate_session(chat_id)
  └── SwarmSession              # 单个用户的一次 swarm 运行
        ├── agents: dict        # 4 AI agents + 4 channel proxies
        ├── task: asyncio.Task  # swarm 运行的协程
        └── chat_id: str        # 飞书 chat_id
```

### 共享资源

- **MCP servers 全局共享**：启动时创建一份 McpManager，所有 session 复用。MCP server 是独立子进程，无需每用户开一套。
- **飞书 WS 连接全局共享**：一个 lark-oapi WS Client 接收所有用户消息。

## 消息流

### 用户发消息

```
用户发消息到飞书 (群聊/单聊)
  → 飞书 WS 推送 im.message.receive_v1 事件
  → FeishuBotService._on_message()
    → 无活跃 session → 创建 SwarmSession，以用户消息作为 prompt 启动 swarm
    → 有活跃 session 且不是终止指令 → 注入到 session 的 pending reply
    → 终止指令 ("终止"/"停止"/"abort") → terminate_session()
```

### Agent 输出推送

```
Agent 在 swarm 中生成回复
  → 消息拦截 hook 触发
    → 工具调用 → 推送 "🔧 {agent_name} 正在执行 {tool_name}..."
    → LLM 文本输出 → 推送 "【{agent_name}】\n{content}"
  → 飞书 Bot API 发送到对应 chat_id
```

### 终止

```
用户发送"终止"
  → session.task.cancel()
  → 推送 "⚠️ 任务已终止"
  → 清理会话资源
```

## 关键改造点

### 1. 飞书消息模式变更

现有 `FeishuChannel` 是 P2P 单聊 request-reply 模式。改造为：
- 支持群聊模式（`receive_id_type="chat_id"`）
- 支持单聊模式（`receive_id_type="open_id"`）
- 不再是 send → poll_reply 模式，而是 send 推送 + inject_reply 注入

### 2. Channel Proxy 回复注入

现有 `ChannelUserProxyAgent.a_get_human_input()` 通过 polling 等待回复。改造为：
- 使用 `asyncio.Event` + `asyncio.Future` 替代 polling
- `inject_human_reply(text)` 设置 Future 结果
- `a_get_human_input()` await Future

### 3. Swarm 消息拦截

在 `arun_swarm` 外层包装消息监听：
- 通过 AG2 的 agent hook（如 `register_reply` 或 `process_all_messages_before_reply`）拦截每条 agent 输出
- 判断消息类型（工具调用 vs LLM 文本）
- 调用 FeishuBotService 推送到飞书

### 4. Agent Factory 改造

现有 `create_all_agents()` 接收全局配置创建 agents。改造为：
- 支持会话级创建：每个 session 调用 `create_all_agents()` 获得独立的 agent 实例
- channel proxy 共享同一个飞书连接但用不同的 chat_id/open_id
- session 完成后 agent 实例被 GC 回收

## 文件变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `server.py` | 新增 | FastAPI 入口，启动服务 |
| `infrastructure/feishu_service.py` | 新增 | 飞书消息收发服务（群聊+单聊，send + event） |
| `infrastructure/session_manager.py` | 新增 | 会话池：创建/查找/终止 session |
| `infrastructure/swarm_session.py` | 新增 | 单个 swarm 会话封装：agent 创建、消息拦截、生命周期 |
| `infrastructure/channel_feishu.py` | 改造 | 支持 inject_reply 模式，支持群聊 chat_id |
| `agents/channel_proxy.py` | 改造 | 用 asyncio.Event 替代 polling 等待回复 |
| `orchestration/group.py` | 改造 | 加入消息拦截回调，推送 agent 输出到飞书 |
| `agents/factory.py` | 小改 | 支持会话级 agent 创建参数 |

## 不做的事

- **用户注册/认证**：当前阶段不做，任何飞书用户都可以直接使用
- **暂停任务**：asyncio Task 暂停复杂度高，先只支持终止
- **流式输出**：飞书消息 API 不支持流式编辑，先全量推送
- **工具调用结果全量展示**：只显示调了什么工具和调完后的回复
- **Session 持久化/恢复**：当前会话结束后不保存状态
