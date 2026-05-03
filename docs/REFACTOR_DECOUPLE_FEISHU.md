# 重构计划：解耦飞书，使前端可插拔

## 目标
将飞书从一个硬依赖变为可选项（默认仍开启）。解耦后可以方便地添加 CLI、Web、App 等其他前端。

## 约束
- **不改飞书现有行为**，重构后飞书模式必须和之前完全一样
- **每一步都是可运行可测试的**，不要一次改太多
- **不改核心 agent 文件**（PM.py, planner.py, generator.py, evaluator.py, single.py），它们已经干净了
- **不改 ChannelAdapter 的已有实现**（email, dingtalk），只扩展接口

## 耦合分析（需要修改的 4 个关键点）

### 耦合点 1: `infrastructure/swarm_session.py`
- 构造函数接收 `bot: FeishuBotService`，硬编码
- 硬编码创建 `ChannelFeishuService(bot, chat_id)`
- 多处直接调用 `self._bot.send_text(chat_id, ...)`
- `setup_handoffs(agents, "feishu")` 硬编码字符串

### 耦合点 2: `infrastructure/session_manager.py`
- `from infrastructure.feishu_bot import FeishuBotService` 作为类型
- `self._bot: FeishuBotService | None` 类型标注
- 多处调用 `self._bot.send_text(chat_id, text)`

### 耦合点 3: `agents/channel_proxy.py`
- `isinstance(self._channel, ChannelFeishuService)` 破坏抽象
- 使用 `wait_reply()` 但它不在 ChannelAdapter 基类中

### 耦合点 4: `server.py`
- 直接 `from infrastructure.feishu_bot import FeishuBotService`
- 直接创建 FeishuBotService 实例
- 整个启动流程绑定飞书

## 分步实施计划

### Step 1: 定义 `Frontend` Protocol
文件: `infrastructure/frontend.py`（新建）

```python
"""Frontend abstraction — decouples core from any specific UI channel."""
from __future__ import annotations
from typing import Protocol, runtime_checkable

@runtime_checkable
class Frontend(Protocol):
    """Bidirectional frontend interface.
    
    Inbound: the frontend calls on_message(chat_id, open_id, chat_type, text)
    Outbound: core calls frontend.send_text(chat_id, text)
    """
    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message to a chat."""
        ...
```

### Step 2: 让 FeishuBotService 实现 Frontend
文件: `infrastructure/feishu_bot.py`

FeishuBotService 已经有 `send_text()` 方法，所以它自然满足 Protocol。
不需要改代码，只需确认签名匹配。

### Step 3: 修改 SwarmSession — 用 Frontend 替代 FeishuBotService
文件: `infrastructure/swarm_session.py`

改动:
1. 构造函数 `bot: FeishuBotService` → `frontend: Frontend`（用 Protocol 类型）
2. `self._bot` → `self._frontend`
3. 所有 `self._bot.send_text(...)` → `self._frontend.send_text(...)`
4. Channel 创建改为通过工厂方法或参数注入，不再硬编码 `ChannelFeishuService`
5. `setup_handoffs(agents, "feishu")` 的 "feishu" 改为从参数传入
6. 删除 `from infrastructure.feishu_bot import FeishuBotService` 导入

Channel 创建的工厂方法方案:
- 构造函数增加 `channel_factory: Callable[[str], ChannelAdapter]` 参数
- `self._channel = channel_factory(chat_id)` 替代硬编码
- 在 server.py 中传入 `lambda chat_id: ChannelFeishuService(bot, chat_id)`

### Step 4: 修改 SessionManager — 用 Frontend 替代 FeishuBotService  
文件: `infrastructure/session_manager.py`

改动:
1. `from infrastructure.frontend import Frontend`
2. `self._bot: FeishuBotService | None` → `self._frontend: Frontend | None`
3. 所有 `self._bot.send_text(...)` → `self._frontend.send_text(...)`
4. 删除 `from infrastructure.feishu_bot import FeishuBotService` 导入
5. 构造函数参数 `bot` → `frontend`

### Step 5: 修改 channel_proxy.py — 消除 isinstance hack
文件: `agents/channel_proxy.py`

改动:
1. 给 ChannelAdapter 基类添加 `async def wait_reply(self, request_id: str) -> str` 方法（抛 NotImplementedError）
2. ChannelFeishuService 已经实现了 wait_reply，无需改
3. 删除 `isinstance` 检查，统一用 `self._channel.wait_reply()`
4. 删除 `from infrastructure.channel.channel_feishu_service import ChannelFeishuService`

### Step 6: 修改 server.py — 前端工厂
文件: `server.py`

改动:
1. 仍然加载 feishu_config（因为默认用飞书）
2. 创建 FeishuBotService 实例
3. 把 bot 作为 Frontend 传给 SessionManager
4. 传入 channel_factory lambda
5. 添加注释标记，后续可以换成其他前端

### Step 7: 验证
- 启动服务，确保飞书模式完全正常
- 确认所有 agent 文件无飞书依赖
- 确认 swarm_session.py 无 FeishuBotService 导入
- 确认 session_manager.py 无 FeishuBotService 导入

## 文件修改清单

| 文件 | 操作 |
|------|------|
| `infrastructure/frontend.py` | 新建 — Frontend Protocol |
| `infrastructure/channel/channel.py` | 修改 — ChannelAdapter 加 wait_reply |
| `infrastructure/swarm_session.py` | 修改 — 解耦 3 处硬编码 |
| `infrastructure/session_manager.py` | 修改 — 用 Frontend 替代 FeishuBotService |
| `agents/channel_proxy.py` | 修改 — 去掉 isinstance |
| `server.py` | 修改 — 工厂模式创建前端 |
| `agents/factory.py` | 可能需要微调 |

## 不改的文件
- agents/PM.py, planner.py, generator.py, evaluator.py, single.py ✅ 已干净
- infrastructure/feishu_bot.py — 保持原样，它是 Frontend 的一个实现
- infrastructure/channel/channel_feishu.py, channel_feishu_service.py — 保持原样
- config/config.py — FeishuConfig 暂保留，是配置层的自然耦合
