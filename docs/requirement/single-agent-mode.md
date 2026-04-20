# 4/20 普通模式 / 专家模式

## 需求

在飞书服务中支持运行时切换两种模式：
- **专家模式（swarm）**：现有 PM → Planner → Generator → Evaluator 多 Agent 协作
- **普通模式（single）**：单个全能 Assistant 直接与用户对话，通过 claude_code 委派编码

用户在飞书中通过命令切换，下一次发起新任务时生效。普通模式下群聊不区分 open_id（所有人可回复）。

## 设计决策

### 模式切换方式

运行时飞书命令，非配置文件。每个 chat_id 独立维护当前模式。

| 命令 | 效果 |
|---|---|
| `harness 普通模式` / `harness normal` | 切换到普通模式 |
| `harness 专家模式` / `harness expert` / `harness swarm` | 切换到专家模式 |

### 单 Agent 设计

- 1 个 Assistant（全能） + 1 个 assistant_owner proxy
- Assistant 不直接写代码，通过 claude_code MCP 委派给 CC
- LLM 配置复用 GENERATOR
- 技能合并 Planner + Generator 的关键技能
- 不区分 open_id（群聊中任何人都能回复）

### 两个独立维度

| 维度 | 配置项 | 说明 |
|---|---|---|
| Agent 模式 | `harness.mode` / 飞书命令 | swarm / single |
| 交互通道 | `harness.hitl.mode` | stdin / email / dingtalk / feishu |

两个维度正交，可自由组合（如 single + feishu）。

## 已完成

- ✅ `infrastructure/config.py` — HarnessConfig 加 `mode: str = "swarm"`，load_harness_config 解析
- ✅ `config/harness.yaml` — 顶层加 `mode: swarm` 配置项（默认值，飞书运行时可覆盖）
- ✅ `agents/single.py` — 新建，`create_single()` 复用 generator LLM 配置
- ✅ `agents/prompts/single.md` — 新建，全能助手提示词
- ✅ `agents/factory.py` — 加 SINGLE_SKILLS / SINGLE_MCP_SERVERS / `create_single_agent()` / `setup_single_handoffs()`，`create_all_agents(mode=)` 根据 mode 分支
- ✅ `infrastructure/swarm_session.py` — `__init__` 接受 `mode` 参数，`_create_agents()` / `_run()` / `_monitor_messages()` / `_extract_messages_from_agents()` 全部支持双模式
- ✅ `infrastructure/session_manager.py` — 加 `_chat_modes` 存储、模式切换命令解析、普通模式跳过 open_id 检查
- ✅ `main.py` — 根据 mode 构建 agents_list 和选择 initial_agent

## 关键文件

| 文件 | 职责 |
|---|---|
| `agents/single.py` | 单 Agent 创建 |
| `agents/prompts/single.md` | 单 Agent 系统提示词 |
| `agents/factory.py` | Agent 工厂，模式分支逻辑 |
| `infrastructure/swarm_session.py` | 会话级 agent 创建和运行 |
| `infrastructure/session_manager.py` | 飞书模式切换命令和 chat_id 级模式存储 |
