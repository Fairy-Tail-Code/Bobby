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
