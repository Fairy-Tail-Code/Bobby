# AG2 OpenHarness

基于 [AG2 (AutoGen)](https://github.com/ag2ai/ag2) 的多智能体全栈开发框架。

## 一键安装

### Windows

```powershell
irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 | iex
```

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.sh | bash
```

安装脚本会自动：

1. 检查依赖（Python 3.12+, uv, Git）
2. 克隆仓库到 `~/.openharness/repo/` 并执行 `uv sync`
3. 创建 `~/.openharness/` 目录结构
4. 写入默认配置（不覆盖已有）
5. 将 venv 的 `bin` 加入 PATH

安装完成后重新打开终端，然后：

```bash
harness info          # 查看安装信息
```

### 升级

安装脚本会自动检查版本。运行安装脚本时会显示：
- **Latest version**: 远程仓库最新版本
- **Local version**: 本地当前版本

如果有新版本可用，会提示使用 `-Upgrade` 标志更新：

```powershell
# Windows
irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 -OutFile install.ps1
.\install.ps1 -Upgrade
```

```bash
# macOS / Linux
INSTALL_UPGRADE=true curl -fsSL https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.sh | bash
```

**版本管理机制**：
- 使用 Git Tags（v0.0.1, v0.0.2...）进行版本控制
- 版本号定义在 `pyproject.toml` 的 `[project]` 部分的 `version` 字段
- 修改版本号并推送到 main 分支后，GitHub Actions 自动创建 Release 和 Tag
- 安装脚本通过 GitHub API 获取最新版本，并与本地 git tag 比较

## 安装后配置

编辑 `~/.openharness/.env`，填入 LLM 配置：

```dotenv
PM_MODEL=GLM-4-Plus
PM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
PM_API_KEY=your_api_key_here
PM_TEMPERATURE=0.7

PLANNER_MODEL=GLM-4-Plus
PLANNER_BASE_URL=https://open.bigmodel.cn/api/paas/v4
PLANNER_API_KEY=your_api_key_here
PLANNER_TEMPERATURE=0.7

GENERATOR_MODEL=GLM-4-Plus
GENERATOR_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GENERATOR_API_KEY=your_api_key_here
GENERATOR_TEMPERATURE=0.4

EVALUATOR_MODEL=GLM-4-Plus
EVALUATOR_BASE_URL=https://open.bigmodel.cn/api/paas/v4
EVALUATOR_API_KEY=your_api_key_here
EVALUATOR_TEMPERATURE=0.2
```

或运行交互式配置向导：

```bash
harness setup
```

## CLI 命令参考

```
harness run <prompt>                    CLI 模式运行任务
harness server start [-f]              启动当前配置的 gateway（可同时启用飞书/微信）
harness server stop                    停止 gateway
harness server restart                 重启 gateway
harness install                        初始化/修复 ~/.openharness/
harness setup                          交互式配置向导（含飞书/微信扫码网关与多选）
harness info                           显示安装信息
harness version                        版本号
```

### 示例

```bash
harness run "构建一个带暗色主题的任务管理应用"
harness server start
harness server stop
```

## 从源码运行（开发者）

```bash
git clone https://github.com/iamikunnnnn/Bobby.git
cd Bobby
uv sync

# 初始化用户目录
python cli.py install

# 编辑配置
# (编辑 ~/.openharness/.env 或运行 python cli.py setup)

# 运行
python cli.py run "你的需求描述"
python server.py                  # 启动当前配置的一个或多个 gateway
```

## 目录结构

安装完成后，用户数据统一存放在 `~/.openharness/`（可通过 `OPENHARNESS_HOME` 环境变量覆盖）：

```
~/.openharness/
├── repo/                    # 源码仓库（git clone + uv sync）
│   └── .venv/               # Python 虚拟环境（harness 命令在此）
├── config/
│   ├── harness.yaml         # 运行模式、评估、上下文等配置
│   ├── mcp.yaml             # MCP 服务器配置
│   └── skill.yaml           # 各角色技能分配
├── agents/
│   └── prompts/             # Agent 系统提示词（用户可编辑）
├── session/                 # 会话快照（运行时写入）
├── memory/
│   └── user_profile.md      # 用户画像
├── skills/
│   └── user/                # 用户自定义技能
├── workspace/
│   └── .tasks/              # 任务管理
├── .install-marker          # 安装标记
└── .env                     # API 密钥等环境变量
```

| 目录 | 说明 |
|------|------|
| `repo/` | 源码仓库，`harness` 命令来自 `.venv` |
| `config/` | 运行时 YAML 配置 |
| `.env` | LLM、邮箱、飞书、微信、钉钉等密钥 |
| `agents/prompts/` | Agent 系统提示词，支持用户自定义 |
| `session/` | 会话快照，支持 `harness resume` |
| `memory/` | 长期记忆和用户资料 |
| `skills/user/` | 用户自定义技能 |
| `workspace/` | 默认工作区 |

## 配置说明

### harness.yaml

```yaml
harness:
  mode: swarm              # swarm（多 Agent）| single（单 Agent）
  evaluation:
    score_threshold: 7
  context:
    enabled: true
    max_messages: 500
    max_tokens: 200000
    auto_compact_enabled: true
    max_rounds: 500
  hitl:
    mode: stdin             # stdin | email | dingtalk | gateway
    gateways: []            # 仅 mode=gateway 时生效，例如 [feishu, weixin]
  claude_code:
    model: sonnet           # Claude Code 委托模式
  memory:
    enabled: true
    dir: memory             # 相对 OPENHARNESS_HOME，默认 ~/.openharness/memory
    auto_extract_enabled: true
    max_auto_memories: 3
```

`harness setup` 里选择 `messaging gateway` 后，可以在终端勾选 `feishu`、`weixin` 中的一个或多个平台。扫码成功后会直接写回 `.env`，`harness server start` 会同时启动所有已勾选 gateway，并把两边消息汇入同一个 `SessionManager`。

记忆系统会把 `MEMORY.md` 索引自动注入到各角色的 system prompt 中，并为 agent 注册 `load_memory` / `save_memory` 工具。适合保存用户偏好、行为反馈、项目决策、外部系统引用这类无法从代码和 git 直接推导的信息。

当 session 完成或终止时，系统还会自动复盘聊天记录，提炼少量 durable memories 并写回同一个 `memory/` 目录。命中已有同名 memory 时，会先读取旧内容做合并，再决定是否写回。这个行为可通过 `harness.memory.auto_extract_enabled` 关闭。

### mcp.yaml

控制内置 MCP 服务器的启用。`command: harness` 指向 venv 中的 entry point。

### skill.yaml

定义各角色（pm, planner, generator, evaluator, single）可加载的技能和可使用的 MCP 服务。

## 仓库结构

```
install/
  install.ps1              Windows 安装脚本
  install.sh               macOS/Linux 安装脚本
  defaults/                安装时拷贝到用户目录的默认模板
infrastructure/paths.py    路径解析（~/.openharness/ 或 OPENHARNESS_HOME）
config/config.py           配置加载代码
skills/system/             内置技能（20 个）
agents/prompts/            Agent 系统提示词源文件（安装时拷贝到 ~/.openharness/agents/prompts/）
cli.py                     CLI 入口
pyproject.toml             项目配置（harness entry point 定义在此）
```
