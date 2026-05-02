# 前端解耦设计：飞书可插拔化

> 日期: 2026-05-03
> 状态: 已实施
> 对应提交: `a520141`

## 背景

AG2 OpenHarness 最初完全围绕飞书构建——`FeishuBotService` 同时承担消息接收和发送，`SwarmSession` 和 `SessionManager` 直接依赖飞书类型。这导致：

- 无法添加其他前端（CLI、Web、App）
- 核心逻辑与飞书实现紧耦合，难以独立测试
- `channel_proxy.py` 中用 `isinstance(ChannelFeishuService)` 破坏了 `ChannelAdapter` 抽象

目标是让飞书变成**可插拔的前端之一**（默认且必须开启，因为目前没有其他前端），但核心代码不再直接依赖飞书。

## 架构变更

### 变更前

```
server.py
  └── FeishuBotService (硬编码)
        ├── SessionManager._bot: FeishuBotService
        └── SwarmSession._bot: FeishuBotService
              └── self._channel = ChannelFeishuService(bot, chat_id)  (硬编码)
```

核心模块直接 `from infrastructure.feishu_bot import FeishuBotService`。

### 变更后

```
server.py (前端工厂)
  ├── Frontend Protocol ─── send_text(chat_id, text)
  └── ChannelAdapter      ─── send() + wait_reply()
        │
        ├── FeishuBotService (实现 Frontend)  ← 飞书前端
        └── ChannelFeishuService (实现 ChannelAdapter) ← 飞书 HITL 通道

SessionManager._frontend: Frontend          (不依赖具体实现)
SwarmSession._frontend:   Frontend          (不依赖具体实现)
SwarmSession._channel:    ChannelAdapter     (通过 channel_factory 注入)
```

核心模块只依赖 `Frontend` Protocol 和 `ChannelAdapter` 抽象基类，不依赖任何飞书类型。

## 新增接口

### 1. Frontend Protocol

文件: `infrastructure/frontend.py`

```python
@runtime_checkable
class Frontend(Protocol):
    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message to a chat."""
        ...
```

职责：**向用户推送消息**（通知、状态、agent 输出）。任何前端只需实现这一个方法。

### 2. ChannelAdapter.wait_reply()

文件: `infrastructure/channel/channel.py`（基类扩展）

```python
class ChannelAdapter(ABC):
    # ... 已有方法 ...
    async def wait_reply(self, request_id: str, timeout: float = 300) -> str:
        """Block until a human reply arrives for the given request."""
        raise NotImplementedError
```

职责：**HITL 请求的同步等待**。`ChannelFeishuService` 通过 `asyncio.Future` 实现，其他前端可以用 `input()`、HTTP polling 等方式。

## 改动明细

| 文件 | 改动 | 说明 |
|------|------|------|
| `infrastructure/frontend.py` | **新建** | Frontend Protocol 定义 |
| `infrastructure/channel/channel.py` | **扩展** | ChannelAdapter 基类加 `wait_reply()` |
| `infrastructure/swarm_session.py` | **重构** | `bot: FeishuBotService` → `frontend: Frontend`；`channel_factory` 注入替代硬编码；`hitl_mode` 参数化替代 `"feishu"` 字符串 |
| `infrastructure/session_manager.py` | **重构** | `_bot` → `_frontend`；透传 `channel_factory` 和 `hitl_mode` 到 SwarmSession |
| `agents/channel_proxy.py` | **修复** | 删除 `isinstance(ChannelFeishuService)` hack，统一调用 `self._channel.wait_reply()` |
| `server.py` | **重构** | 创建 FeishuBotService 后作为 `Frontend` 注入；传入 `channel_factory=lambda chat_id: ChannelFeishuService(bot, chat_id)` |

### 未改动的文件

- `agents/PM.py`, `planner.py`, `generator.py`, `evaluator.py`, `single.py` — 本身无飞书依赖，无需改动
- `infrastructure/feishu_bot.py` — 保持原样，它是 Frontend 的一个实现
- `infrastructure/channel/channel_feishu_service.py` — 保持原样，自然继承 `wait_reply()`
- `config/config.py` — `FeishuConfig` 是配置层的自然耦合，暂保留

## 消息流（变更后）

```
用户发消息
  → Frontend (FeishuBotService) 接收
    → SessionManager.handle_message()
      → 新消息 → _create_session()
        → SwarmSession(frontend=bot, channel_factory=..., hitl_mode="feishu")
          → self._channel = channel_factory(chat_id)
      → 已有 session → session.inject_reply(text)

Agent 输出
  → SwarmSession._flush_message()
    → self._frontend.send_text(chat_id, text)    # 通过 Frontend Protocol

Agent 需要人工回复
  → ChannelUserProxyAgent.a_get_human_input()
    → self._channel.send(...)                     # 推送请求到用户
    → self._channel.wait_reply(...)               # 等待用户回复

用户回复
  → Frontend 接收 → session.inject_reply()
    → self._channel.inject_reply(request_id, text)
      → Future.set_result() → 解除 wait_reply() 阻塞
```

## 如何添加新前端

添加一个新前端（如 CLI）只需三步：

### Step 1: 实现 Frontend Protocol

```python
class CLIFrontend:
    async def send_text(self, chat_id: str, text: str) -> None:
        print(text)  # 直接输出到终端
```

### Step 2: 实现 ChannelAdapter

```python
class CLIChannel(ChannelAdapter):
    async def send(self, recipient, subject, body, request_id):
        print(f"\n🔔 {subject}\n{body}")
    
    async def wait_reply(self, request_id, timeout=300):
        return input("请回复: ")  # 或 asyncio + stdin
    
    async def inject_reply(self, request_id, text):
        # 对于 CLI，wait_reply 本身就是阻塞等待，不需要 inject
        pass
```

### Step 3: 在 server.py 中注入

```python
frontend = CLIFrontend()
session_manager = SessionManager(
    frontend=frontend,
    channel_factory=lambda chat_id: CLIChannel(),
    hitl_mode="cli",
    ...
)
```

核心逻辑（agents、session、orchestration）完全不用碰。

## 验证

- 所有 6 个改动文件 `py_compile` 通过
- `swarm_session.py` 无 `FeishuBotService` import（仅注释中提及）
- `session_manager.py` 无 `FeishuBotService` import（仅注释中提及）
- `channel_proxy.py` 无 `ChannelFeishuService` import
- 飞书模式启动正常，WS 连接成功，MCP servers 全部就绪
