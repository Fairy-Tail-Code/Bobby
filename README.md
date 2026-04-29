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

### 升级

重新下载最新版 `harness` 二进制（不覆盖配置）：

```powershell
# Windows
irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 | iex -Upgrade
```

```bash
# macOS / Linux
INSTALL_UPGRADE=true curl -fsSL https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.sh | bash
```

安装脚本会自动：

1. 检查依赖（Python 3.12+, uv, Git）
2. 从 GitHub Release 下载 `harness` 可执行文件
3. 创建 `~/.openharness/` 目录结构
4. 写入默认配置（不覆盖已有）
5. 将 `~/.openharness/bin` 加入 PATH

安装完成后重新打开终端，然后：

```bash
harness info          # 查看安装信息
```

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

## CLI 命令参考

```
harness run <prompt>                    CLI 模式运行任务
harness server start [-f]              启动飞书服务（-f 前台运行）
harness server stop                    停止飞书服务
harness server restart                 重启飞书服务
harness knowledge sync                 知识库同步
harness knowledge search <query>       知识库搜索
harness knowledge status               知识库状态
harness install                        初始化/修复 ~/.openharness/
harness info                           显示安装信息
harness version                        版本号
```

### 示例

```bash
harness run "构建一个带暗色主题的任务管理应用"
harness server start
harness server stop
harness knowledge search "React 路由"
```

## 从源码运行（开发者）

```bash
git clone https://github.com/iamikunnnnn/Bobby.git
cd Bobby
uv sync
playwright install chromium

# 初始化用户目录
python cli.py install

# 编辑配置
# (编辑 ~/.openharness/.env)

# 运行
python cli.py run "你的需求描述"
python main.py "你的需求描述"     # 等效
python server.py                  # 启动飞书服务
```

## 目录结构

安装完成后，用户数据统一存放在 `~/.openharness/`（可通过 `OPENHARNESS_HOME` 环境变量覆盖）：

```
~/.openharness/
├── bin/
│   └── harness(.exe)        # CLI 可执行文件
├── config/
│   ├── harness.yaml         # 运行模式、评估、上下文等配置
│   ├── mcp.yaml             # MCP 服务器配置
│   ├── skill.yaml           # 各角色技能分配
│   └── .env.example         # 环境变量模板
├── session/                 # 会话快照（运行时写入）
├── memory/
│   └── user_profile.md      # 用户画像
├── skills/
│   └── user/                # 用户自定义技能
├── workspace/
│   └── .tasks/              # 任务管理
├── .openharness/            # 本地数据
│   ├── knowledge_queue.db   # 知识队列
│   └── collected/           # 收集的知识
├── .install-marker          # 安装标记
└── .env                     # API 密钥等环境变量
```

| 目录 | 说明 |
|------|------|
| `config/` | 运行时 YAML 配置 |
| `.env` | LLM、邮箱、飞书、钉钉等密钥 |
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
    mode: stdin             # stdin | email | dingtalk | feishu
  acpx:
    model: sonnet           # Claude Code 委托模式
  knowledge:
    enabled: true
    server_url: "http://localhost:8900"
    offline_enabled: true
    pull_enabled: true
```

### mcp.yaml

控制内置 MCP 服务器的启用。安装模式下使用 `harness _mcp <name>`，开发模式下使用 `uv run python -m infrastructure.mcp_servers.<name>_server`。

### skill.yaml

定义各角色（pm, planner, generator, evaluator, single）可加载的技能和可使用的 MCP 服务。

## 知识共享

在 `harness.yaml` 中启用后，OpenHarness 会自动收集和同步开发经验：

```yaml
harness:
  knowledge:
    enabled: true
    server_url: "http://localhost:8900"
```

```bash
harness knowledge status    # 查看状态
harness knowledge sync      # 手动同步
harness knowledge search "React 路由"  # 搜索
```

## 发布流程

### 发布新版本

```bash
git tag v1.x.x
git push origin v1.x.x
```

GitHub Actions 会自动在 Windows / macOS / Linux 三平台构建 PyInstaller 二进制，并发布到 GitHub Release。

### CI/CD 注意事项

- 仓库需设为 **Public**，否则 `irm`/`curl` 一键安装无法访问
- Settings → Actions → General → Workflow permissions → 选 **Read and write permissions**
- CI 使用官方 PyPI（`UV_INDEX_URL=https://pypi.org/simple/`），不依赖国内镜像

## 仓库结构（源码相关，非运行时）

```
install/defaults/           安装时拷贝到用户目录的默认模板
infrastructure/paths.py     路径解析（~/.openharness/ 或 OPENHARNESS_HOME）
config/config.py            配置加载代码
skills/system/              内置技能（20 个）
agents/prompts/             Agent 系统提示词
cli.py                      CLI 入口
harness.spec                PyInstaller 构建配置
.github/workflows/release.yml  CI/CD 发布流程
```
