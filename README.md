# AG2 OpenHarness

基于 [AG2 (AutoGen)](https://github.com/ag2ai/ag2) 的多智能体全栈应用生成框架。通过 PM、Planner、Generator、Evaluator 四个专业智能体的 Swarm 协作，自动化完成从需求分析到代码交付的全流程。

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                     User / HITL                      │
│         (stdin / Email / DingTalk / Feishu)          │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │          PM             │  需求管理，PRD 撰写
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │        Planner          │  技术拆解，架构设计
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │       Generator         │  编码实现，代码委派
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │       Evaluator         │  质量评审，测试验证
          └────────────┬────────────┘
                       │
                  审核通过 / 回退
```

### 两种运行模式

- **Swarm 模式** (`mode: swarm`)：四智能体协作，适用于复杂项目
- **Single 模式** (`mode: single`)：单一 Assistant 直接对话，适用于简单任务

## 快速开始

### 前置要求

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- OpenAI 兼容 API（智谱、OpenAI、SiliconFlow 等）

### 安装

```bash
# 克隆仓库
git clone <repo-url>
cd AG2_openharness

# 安装依赖
uv sync
# 或
pip install -r requirements.txt

# 安装 Playwright 浏览器（用于浏览器测试）
playwright install chromium
```

### 配置

```bash
# 复制环境变量模板并填写
cp .env.example .env
```

编辑 `.env`，填入你的 LLM API 配置：

```dotenv
PLANNER_MODEL=GLM-4-Plus
PLANNER_BASE_URL=https://open.bigmodel.cn/api/paas/v4
PLANNER_API_KEY=your_api_key_here
PLANNER_TEMPERATURE=0.7

GENERATOR_MODEL=GLM-4-Plus
GENERATOR_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GENERATOR_API_KEY=your_api_key_here
GENERATOR_TEMPERATURE=0.4

# ... 其余角色配置类似
```

### 运行

```bash
# CLI 模式
python main.py "构建一个带暗色主题的任务管理应用"

# 飞书服务模式（需配置飞书应用）
python server.py
```

## 项目结构

```
AG2_openharness/
├── main.py                    # CLI 入口
├── server.py                  # 飞书 Bot 服务入口
├── config/
│   ├── harness.yaml           # 框架主配置（模式、轮数、评估维度等）
│   └── mcp.yaml               # MCP 服务器配置
├── agents/
│   ├── factory.py             # 智能体工厂（创建、技能注入、Handoff 设置）
│   ├── PM.py                  # PM 智能体
│   ├── planner.py             # Planner 智能体
│   ├── generator.py           # Generator 智能体
│   ├── evaluator.py           # Evaluator 智能体
│   ├── single.py              # Single 模式 Assistant
│   ├── user.py                # 用户代理（含 HITL 通道适配器）
│   └── prompts/               # 系统 Prompt 模板
├── orchestration/
│   ├── group.py               # Swarm 群聊编排
│   └── termination.py         # 终止条件
├── infrastructure/
│   ├── config.py              # 配置加载（.env + YAML）
│   ├── swarm_session.py       # Session 管理
│   ├── session_manager.py     # 飞书服务模式 Session 管理
│   ├── feishu_bot.py          # 飞书 Bot SDK 封装
│   ├── mcp/
│   │   ├── manager.py         # MCP 服务器生命周期管理
│   │   └── tool_bridge.py     # MCP 工具注册到 AG2 Agent
│   ├── mcp_servers/           # 内置 MCP 服务器
│   │   ├── shell_server.py    # Shell 命令执行
│   │   ├── git_server.py      # Git 操作
│   │   ├── gitee_server.py    # Gitee API
│   │   ├── browser_server.py  # Playwright 浏览器自动化
│   │   ├── docker_server.py   # Docker Compose 管理
│   │   ├── database_server.py # SQLite 数据库操作
│   │   ├── http_api_server.py # HTTP API 测试
│   │   ├── workspace_server.py# 文件工作区管理
│   │   ├── docs_web_server.py # 文档抓取
│   │   └── claude_code_server.py  # Claude Code 委派
│   ├── channel/               # HITL 通道适配器
│   │   ├── channel_email.py
│   │   ├── channel_dingtalk.py
│   │   └── channel_feishu_service.py
│   ├── context/               # 上下文压缩
│   │   ├── snip.py            # Level 1: 消息裁剪
│   │   └── auto_compact.py    # Level 4: LLM 自动摘要
│   └── skills/                # 技能注册与注入
├── skills/                    # 可插拔技能包（23 个内置技能）
├── tests/                     # 测试
├── utils/                     # 工具函数
└── docs/                      # 设计文档与 AG2 知识库
```

## 核心特性

### 多智能体 Swarm 协作

基于 AG2 的 Swarm Pattern，四个专业智能体通过 Handoff 机制自动流转：

| 智能体 | 职责 | 可用技能 |
|--------|------|----------|
| PM | 需求澄清、PRD 撰写、进度跟踪 | workspace, shell |
| Planner | 技术架构设计、任务拆解 | repo-surveyor, fullstack-analyst, backend-analyst, git-operator |
| Generator | 代码编写、Claude Code 委派 | claude-code, backend-delivery, frontend-delivery, bug-fixer, docker-operator 等 |
| Evaluator | 代码审查、自动化测试 | browser-tester, api-tester, test-writer, verification-gate |

### HITL（Human-in-the-Loop）

支持四种人机交互模式，在 `config/harness.yaml` 中配置：

```yaml
hitl:
  mode: stdin  # stdin | email | dingtalk | feishu
```

- **stdin**：终端直接交互
- **email**：通过 SMTP/IMAP 收发邮件审批
- **dingtalk**：钉钉机器人消息推送
- **feishu**：飞书 Bot 长连接消息推送

### MCP 工具生态

内置 10 个 MCP 服务器，通过 `config/mcp.yaml` 按需启用：

```yaml
mcp_servers:
  shell:
    transport: stdio
    command: uv
    args: ["run", "python", "-m", "infrastructure.mcp_servers.shell_server"]
```

所有 MCP 工具自动注册到对应智能体，支持 Shell、Git、浏览器、Docker、数据库、HTTP API 等操作。

### 技能系统

23 个可插拔技能包位于 `skills/` 目录，每个技能包含：
- `SKILL.md`：技能描述与 Prompt
- `agents/openai.yaml`：Agent 配置
- `templates/`：输出模板（可选）
- `assets/`：JSON Schema（可选）

技能通过 `SkillRegistry` 自动扫描并按智能体角色分配。

### 上下文管理

两级上下文压缩策略，防止 token 溢出：

- **Level 1 — Snip Compact**：保留最近 N 条消息 + 首条消息
- **Level 4 — Auto Compact**：LLM 自动摘要压缩历史上下文

在 `config/harness.yaml` 中配置：

```yaml
context:
  enabled: true
  max_messages: 500
  max_tokens: 200000
  auto_compact_enabled: true
```

### Claude Code 委派（`claude -p` 模式）

Generator 通过 `claude_code` MCP 服务器调用 `claude -p` 进行非交互式编码委派。支持两种调用方式：
- `claude_prompt`：直接传入 Prompt 字符串
- `claude_prompt_file`：从文件读取 Prompt（适用于长 Prompt）

需本地安装 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)，配置字段保留 `acpx` 名称：

```yaml
acpx:
  model: sonnet             # Claude 模型别名（sonnet, opus, haiku）
  default_timeout: 600      # 单次任务超时（秒）
  max_retries: 2            # 失败后最大重试次数
```

## 配置参考

### `.env` 环境变量

| 变量 | 说明 |
|------|------|
| `{ROLE}_MODEL` | 角色使用的 LLM 模型名（PM/PLANNER/GENERATOR/EVALUATOR） |
| `{ROLE}_BASE_URL` | LLM API Base URL |
| `{ROLE}_API_KEY` | LLM API Key |
| `{ROLE}_TEMPERATURE` | 生成温度 |
| `GITEE_ACCESS_TOKEN` | Gitee 访问令牌 |
| `SMTP_HOST/USER/PASSWORD` | 邮件 SMTP 配置 |
| `IMAP_HOST/USER/PASSWORD` | 邮件 IMAP 配置 |
| `DINGTALK_CLIENT_ID/SECRET` | 钉钉应用凭证 |
| `FEISHU_APP_ID/SECRET` | 飞书应用凭证 |
| `HITL_{ROLE}_EMAIL` | 各角色对应的人类操作员邮箱 |
| `HITL_{ROLE}_DINGTALK_USER_ID` | 各角色对应的钉钉用户 ID |
| `HITL_{ROLE}_FEISHU_OPEN_ID` | 各角色对应的飞书用户 Open ID |

### `config/harness.yaml`

```yaml
harness:
  mode: swarm              # swarm | single
  evaluation:
    score_threshold: 7
    dimensions:
      - name: design_quality
        weight: high
        threshold: 7
  tech_stack:
    frontend: "react+vite"
    backend: "fastapi"
    database: "sqlite"
  context:
    enabled: true
    max_messages: 500
    max_tokens: 200000
    auto_compact_enabled: true
    max_rounds: 500
  hitl:
    mode: stdin
    polling_interval: 30
    timeout: 3600
```

## 测试

```bash
pytest tests/
```

## 技术栈

- **框架**：AG2 (AutoGen) >= 0.7.0
- **LLM**：OpenAI 兼容 API（智谱 GLM、OpenAI、SiliconFlow 等）
- **工具协议**：MCP (Model Context Protocol) >= 1.27.0
- **浏览器自动化**：Playwright
- **通讯集成**：飞书 SDK (lark-oapi)、SMTP/IMAP、钉钉
- **Python**：>= 3.12

## License

MIT
