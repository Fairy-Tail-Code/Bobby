# AG2 OpenHarness 开发经验

## 2026-04-09

### 架构决策

#### 从 GroupChat 迁移到 Swarm 模式
- **原因**：GroupChat 的 auto 模式靠 LLM 自由选择发言者，缺乏结构化的 handoff 控制。Swarm 模式通过 `OnCondition` + `Handoffs` 提供确定性的条件转移，同时保留 LLM 评估条件的灵活性。
- **关键 API**：
  - `Handoffs` 对象用 `add_llm_conditions()` 添加条件，不能直接用 `=` 赋值列表
  - `OnCondition(target=AgentTarget(agent), condition=StringLLMCondition("..."))` — 必须用 `AgentTarget` 包装 agent，用 `StringLLMCondition` 包装字符串
  - Evaluator 审核通过后终止：`.set_after_work(TerminateTarget())`
  - 启动 swarm：`initiate_swarm_chat(initial_agent, messages, agents, max_rounds, context_variables)`
- **踩坑**：直接 `agent.handoffs = [OnCondition(...)]` 会把 Handoffs 对象替换为普通 list，导致 `AttributeError`。必须用 `agent.handoffs = Handoffs()` 然后 `.add_llm_conditions([...])`

#### LLM 配置从 YAML 迁移到 .env
- **原因**：敏感信息（API key）不应存储在 YAML 中，`.env` 是更标准的做法，且 `.gitignore` 已包含 `.env`
- **实现**：`infrastructure/config.py` 中手动解析 `.env` 文件（key=value 格式），按 `PLANNER_`/`GENERATOR_`/`EVALUATOR_` 前缀区分三个 Agent 的配置
- **注意**：`load_llm_config()` 现在接收 project root 目录（找 `.env`），而 `load_mcp_config()` / `load_harness_config()` 仍接收 config 子目录

### 组件集成

#### Skill 集成
- openharness 的 skill 使用 `SKILL.md`（不是 `instruction.md`），SkillLoader 已支持两种格式，优先读 `SKILL.md`
- 17 个 skill 按 Agent 角色分配：
  - Planner: repo-surveyor, fullstack-analyst, backend-analyst
  - Generator: backend-delivery, frontend-delivery, bug-fixer, git-operator, docker-operator, runtime-* toolchain
  - Evaluator: browser-tester, api-tester, verification-gate, test-writer
- Skill 内容通过 `update_system_message()` 追加到 Agent 的 system prompt 末尾

#### MCP 服务器集成
- MCP 服务器代码从 `openharness/openharness/mcp_servers/` 复制到 `infrastructure/mcp_servers/`
- 服务器都是自包含的，只依赖 `mcp` SDK，无 openharness 内部依赖
- 启动命令从 `python -m openharness.mcp_servers.xxx` 改为 `python -m infrastructure.mcp_servers.xxx`
- 用户实际使用 `uv run python -m ...` 启动（见 mcp.yaml）

### 文件变更清单
- `infrastructure/config.py` — 新增 `_load_dotenv()`, `_load_agent_env_config()`, 改写 `load_llm_config()`
- `agents/factory.py` — 新增 `setup_handoffs()`, `_inject_skills()`, Handoffs 用 AG2 正确 API
- `agents/generator.py` — 移除错误的 `AG2_openharness` 模块导入
- `orchestration/group.py` — 从 GroupChatManager 改为 `initiate_swarm_chat` / `a_initiate_swarm_chat`
- `main.py` — 使用 swarm 模式启动，接入 SkillLoader
- `config/mcp.yaml` — 指向本地 MCP 服务器模块
- `tests/test_config.py` — 改为测试 .env 加载
- `tests/test_e2e.py` — 改为测试 swarm handoffs

## 2026-04-10

### 架构决策

#### MCP 全量启用 + Skill-MCP 对齐 + 渐进式披露
- **原因**：原先只有 shell MCP 启用，skill 和 MCP 无依赖关系声明，所有 skill 全量注入 system message，浪费 context window
- **三合一改进**：
  1. **MCP 全量启用**：mcp.yaml 中 9 个服务器全部取消注释
  2. **声明式依赖**：SKILL.md frontmatter 新增 `summary` 和 `mcp_servers` 字段，启动时校验 skill-MCP 对齐
  3. **渐进式披露**：system message 只注入 skill 摘要目录，agent 通过 `load_skill` tool 按需获取完整指令

#### SkillRegistry 替代 SkillLoader
- **原因**：SkillLoader 只能列出和加载指令，无法表达依赖、校验对齐、生成摘要
- **SkillRegistry 新增能力**：
  - 解析 frontmatter 中的 `mcp_servers` 依赖声明
  - `validate_alignment()` 校验 skill 依赖的 MCP 是否已连接
  - `build_summary_block()` 生成紧凑的摘要目录用于注入
  - `load_instruction()` 保留原有能力

#### load_skill Tool
- 每个 agent 注册一个 `load_skill` AG2 Tool
- Agent 调用 `load_skill("browser-tester")` 获取完整 SKILL.md 内容
- 只允许加载分配给当前 agent 的 skill，防止越权

### 文件变更清单
- `config/mcp.yaml` — 取消注释，全部 9 个 MCP 服务器启用
- `skills/*/SKILL.md` — 15 个文件新增 `summary` 和 `mcp_servers` frontmatter 字段
- `infrastructure/skills/registry.py` — 新建 SkillRegistry、SkillMeta、AlignmentIssue
- `infrastructure/skills/tool.py` — 新建 load_skill tool 的创建和注册函数
- `infrastructure/skills/__init__.py` — 更新 re-export
- `agents/factory.py` — 改用 SkillRegistry，注入摘要替代全量指令，注册 load_skill tool
- `main.py` — 改用 SkillRegistry，增加对齐校验逻辑
- `tests/test_skill_loader.py` — 重写为 SkillRegistry 测试（10 个用例全通过）

## 2026-04-15

### 架构决策

#### 多角色邮件 HITL（Human-in-the-Loop）

- **背景**：原系统只有 1 个 stdin UserProxyAgent，无法支持多人协作。需要让不同角色的负责人通过邮件参与 agent 工作流。
- **方案**：3 个 `EmailUserProxyAgent` 替代 1 个 `UserProxyAgent`，每个角色对应一个邮箱收件人，通过 SMTP 发邮件、IMAP 轮询收回复。
- **设计选择**：
  - 用 1 个系统邮箱（非 3 个独立邮箱），3 个角色只是收件人地址
  - 邮件匹配通过主题中的唯一 request_id（非 In-Reply-To），因为 QQ 等邮箱 SMTP 会替换 Message-ID
  - 支持 `hitl.mode: email|stdin` 切换，完全向后兼容
- **角色划分**：
  - PlannerOwner：补充需求信息、澄清模糊需求
  - GeneratorOwner：审批风险操作（删除数据库、force push 等）
  - EvaluatorOwner：确认审核决策

#### MCP subprocess stdin 死锁修复

- **问题**：`shell_server` 的 `subprocess.run()` 未设 `stdin=subprocess.DEVNULL`，子进程继承 MCP stdio 管道导致死锁，所有 shell 命令 180 秒超时
- **修复**：`shell_server.py`、`docker_server.py` 的所有 `subprocess.run()` 加 `stdin=subprocess.DEVNULL`
- **根因**：MCP stdio 传输下，子进程继承 stdin 管道，占用 MCP 通信通道

#### Agent 提示词更新

- Generator 和 Evaluator 的提示词从"3-agent swarm"更新为"multi-agent swarm with human-in-the-loop"
- 新增 `transfer-to-User` 的 Handoff Rules 说明，让 LLM 知道何时可以向对应负责人求助

### 文件变更清单

- `agents/email_proxy.py` — **新建**，EmailUserProxyAgent 类（SMTP 发送 + IMAP 轮询 + 主题 request_id 匹配）
- `agents/user.py` — 新增 `create_email_user_proxies()`，保留 stdin fallback
- `agents/factory.py` — `create_all_agents()` 支持 email 模式，`setup_handoffs()` 支持按角色路由
- `agents/prompts/planner.md` — Team Structure 新增 PlannerOwner，Handoff Rules 更新
- `agents/prompts/generator.md` — Team Structure 新增 GeneratorOwner，Handoff Rules 新增 transfer-to-User
- `agents/prompts/evaluator.md` — Team Structure 新增 EvaluatorOwner，Handoff Rules 新增 transfer-to-User
- `infrastructure/config.py` — 新增 SmtpConfig、ImapConfig、HitlConfig 数据类和加载器
- `infrastructure/mcp_servers/shell_server.py` — 修复 subprocess stdin 死锁
- `infrastructure/mcp_servers/docker_server.py` — 修复 subprocess stdin 死锁
- `config/harness.yaml` — 新增 `hitl` 配置段
- `.env` — 新增 SMTP/IMAP 凭据和 3 个角色邮箱
- `main.py` — 加载邮件配置，动态构建 agents_list

## 2026-04-17

### 架构决策

#### 飞书产品化服务 — 从 CLI 到常驻服务

- **背景**：将 AG2 OpenHarness 从命令行工具改造为飞书机器人服务，用户通过飞书交互，后台运行多 agent swarm。
- **方案选型**：FastAPI + asyncio 会话池（单进程多协程），每个飞书聊天独立一个 SwarmSession。
  - 淘汰方案 B（消息队列 + Worker 进程池）——复杂度过高，当前阶段不需要
  - 淘汰方案 C（飞书卡片式）——卡片有 24 小时更新限制，不适合长时间运行的 swarm 任务
- **设计文档**：`docs/superpowers/specs/2026-04-17-feishu-service-design.md`
- **实施计划**：`docs/superpowers/plans/2026-04-17-feishu-service.md`

### 核心架构

```
飞书用户 ←WS/REST→ FeishuBotService ←→ SessionManager
                                         ├── SwarmSession(chat_id_1)
                                         │     └── [PM, Planner, Generator, Evaluator + 4 ChannelProxy]
                                         ├── SwarmSession(chat_id_2)
                                         │     └── [...]
                                         └── ...
```

- **FeishuBotService**（`infrastructure/feishu_bot.py`）：飞书 WS 长连接接收消息 + REST API 发送消息，支持群聊（@机器人触发）和单聊
- **ChannelFeishuService**（`infrastructure/channel_feishu_service.py`）：ChannelAdapter 实现，用 asyncio.Future 替代传统 polling 等待用户回复
- **SwarmSession**（`infrastructure/swarm_session.py`）：单会话封装，创建独立 agent 集合，运行 swarm，监控消息推送到飞书
- **SessionManager**（`infrastructure/session_manager.py`）：会话池，路由飞书消息到正确的 session
- **server.py**：服务入口，加载配置、连接 MCP、启动飞书服务

### 关键技术决策

#### 1. WS 线程 → 主事件循环桥接

飞书 SDK 的 WS Client 内部管理自己的事件循环（`ws_mod.loop`），在独立 daemon 线程中运行。主服务是 asyncio 事件循环。两者之间的桥接：

```python
# WS 线程中收到消息 → 调度到主循环
asyncio.run_coroutine_threadsafe(
    self._on_message(chat_id, open_id, chat_type, text),
    self._main_loop,  # 主事件循环引用
)
```

`_main_loop` 存储在 `FeishuBotService` 实例上（非全局变量），通过 `set_main_loop()` 在启动时设置。

#### 2. asyncio.Future 替代 polling

旧的 `ChannelUserProxyAgent` 用 `poll_reply` 轮询等待回复（30 秒间隔）。新方案：

- `ChannelFeishuService.send()` 发送消息时同时创建一个 `asyncio.Future`
- `ChannelFeishuService.wait_reply()` await 该 Future，带超时
- `ChannelFeishuService.inject_reply()` 从飞书消息注入，调用 `future.set_result(text)`
- `ChannelUserProxyAgent.a_get_human_input()` 通过 `isinstance` 判断：是 `ChannelFeishuService` 则用 Future，否则走旧 polling 路径

**安全前提**：`inject_reply` 和 `wait_reply` 在同一个 asyncio 事件循环上运行（`set_result` 和 `await` 串行化），无需额外同步。

#### 3. 消息拦截：register_reply 不可行 → 消息监控

**最初方案（失败）**：用 `agent.register_reply([ConversableAgent, None], hook, position=0)` 拦截 agent 输出。

**失败原因**：`register_reply` 的 hook 在 agent **生成回复之前**触发。`messages` 参数是完整的对话历史，`messages[-1]` 是触发当前 agent 回复的上一条消息（不是 agent 自己的输出）。这意味着：
- 每个 agent 的 hook 推送的都是**收到的消息**而非**自己的输出**
- 同一条消息会被多个 agent 的 hook 重复推送
- Agent 的实际输出永远不会被推送到飞书

**最终方案**：消息监控任务（`_monitor_messages`），每秒轮询 agent 的 `chat_messages` 属性，检测新增消息并推送到飞书。虽然不够优雅，但在 AG2 没有提供 post-reply hook 的情况下是最可靠的方案。

#### 4. DefaultPattern vs AutoPattern

现有 `orchestration/group.py` 使用 `DefaultPattern`。`SwarmSession` 使用 `AutoPattern`。两者都是 `Pattern` 基类的子类：
- `DefaultPattern`（`pattern.py`）—— 基类，直接读取 agent 的 `handoffs` 属性
- `AutoPattern`（`auto.py`）—— 扩展，默认 after_work 使用 GroupChatManager 选择

两者都支持 `setup_handoffs` 设置的 handoff 配置。`AutoPattern` 更适合服务模式（自动 speaker 选择）。

### 踩坑记录

#### 1. 已完成的 session 不清理导致内存泄漏

`SwarmSession._run()` 完成后只设置 `_terminated = True`，不从 `SessionManager._sessions` 中移除。如果同一用户再次发消息，`_create_session` 会覆盖旧 session 但不调用 `_channel.stop()`。

**修复**：`_create_session` 中先清理旧 session：
```python
old = self._sessions.get(chat_id)
if old:
    await old._channel.stop()
```

#### 2. 非文本消息静默丢弃

飞书用户发送图片/文件/表情时，`_on_ws_message` 直接 return 无反馈，用户以为机器人坏了。

**修复**：非文本消息时回复"暂不支持该消息类型，请发送文字消息。"

#### 3. Windows 信号处理

`loop.add_signal_handler(signal.SIGTERM, ...)` 在 Windows 上抛出 `NotImplementedError`。

**修复**：信号注册包裹 try/except，回退到 `KeyboardInterrupt` 捕获 Ctrl+C。

### 文件变更清单

- `infrastructure/feishu_bot.py` — **新建**，FeishuBotService（WS 接收 + REST 发送 + 群聊/单聊）
- `infrastructure/channel_feishu_service.py` — **新建**，ChannelAdapter（Future-based reply injection）
- `infrastructure/swarm_session.py` — **新建**，单会话封装（agent 创建 + 消息监控 + 生命周期）
- `infrastructure/session_manager.py` — **新建**，会话池路由（创建/注入/终止）
- `server.py` — **新建**，服务入口
- `agents/channel_proxy.py` — **修改**，`a_get_human_input` 支持 Future 等待
- `docs/superpowers/specs/2026-04-17-feishu-service-design.md` — **新建**，设计文档
- `docs/superpowers/plans/2026-04-17-feishu-service.md` — **新建**，实施计划
