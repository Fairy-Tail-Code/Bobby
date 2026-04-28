# AG2 OpenHarness

基于 [AG2 (AutoGen)](https://github.com/ag2ai/ag2) 的多智能体全栈开发框架。项目运行时配置、会话、记忆、技能和工作区统一放在用户目录 `~/.openharness/`（或 `OPENHARNESS_HOME` 指定的目录）下，而不是仓库根目录。

## 快速开始

### 1. 安装依赖

```bash
git clone <repo-url>
cd AG2_openharness
uv sync
playwright install chromium
```

### 2. 初始化用户目录

```bash
python cli.py install
```

安装后会创建：

```text
~/.openharness/
├── .env
├── .env.example
├── config/
│   ├── harness.yaml
│   ├── mcp.yaml
│   └── skill.yaml
├── session/
├── memory/
├── skills/
└── workspace/
```

其中：

- `.env` 和 `.env.example` 在 `~/.openharness/`
- YAML 配置在 `~/.openharness/config/`
- `session/` 初始为空

### 3. 配置原来放在 `.env` 里的内容

编辑 `~/.openharness/.env`，填入各角色的 LLM 配置：

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

如果你之前把这些内容放在仓库根目录 `.env`，现在应迁移到 `~/.openharness/.env`。

### 4. 运行

```bash
python cli.py run "构建一个带暗色主题的任务管理应用"
```

开发态也可以直接运行：

```bash
python main.py "构建一个带暗色主题的任务管理应用"
python server.py
```

但这两种方式都会读取用户目录下的配置：

- `~/.openharness/.env`
- `~/.openharness/config/harness.yaml`
- `~/.openharness/config/mcp.yaml`
- `~/.openharness/config/skill.yaml`

## 常用命令

```bash
python cli.py info
python cli.py knowledge status
python cli.py knowledge sync
python cli.py knowledge search "React 路由"
```

## 运行时目录说明

- `config/`：运行时 YAML 配置
- `.env`：LLM、邮箱、飞书、钉钉等环境变量
- `session/`：会话快照
- `memory/`：长期记忆和用户资料
- `skills/`：用户技能包
- `workspace/`：默认工作区

所有内置 MCP 工具在未显式传入工作目录时，默认使用 `~/.openharness/workspace/`。

## 配置说明

### `~/.openharness/config/harness.yaml`

```yaml
harness:
  mode: swarm
  evaluation:
    score_threshold: 7
  context:
    enabled: true
    max_messages: 500
    max_tokens: 200000
    auto_compact_enabled: true
    max_rounds: 500
  hitl:
    mode: stdin
```

### `~/.openharness/config/mcp.yaml`

用于启用或关闭内置 MCP 服务器，例如 `shell`、`git`、`workspace`、`browser`、`docker`、`database`。

### `~/.openharness/config/skill.yaml`

用于指定不同角色可加载的技能和可使用的 MCP 服务。

## 知识共享

在 `~/.openharness/config/harness.yaml` 中启用：

```yaml
harness:
  knowledge:
    enabled: true
    server_url: "http://localhost:8900"
    offline_enabled: true
    pull_enabled: true
```

知识库本地数据默认写入：

- `~/.openharness/knowledge_queue.db`
- `~/.openharness/collected/`

## 测试

```bash
pytest tests/
```

## 仓库内哪些内容不是运行时配置

以下目录属于源码或默认模板，不是运行时写入位置：

- `install/defaults/`：安装时拷贝到用户目录的模板
- `config/config.py`：配置加载代码
- `skills/system/`：内置技能源码

不要再把运行时配置写回仓库根目录的 `.env`、`config/`、`session/` 或 `workspace/`。
