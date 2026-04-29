# OpenHarness Installer & CLI Design

## Overview

将 OpenHarness 从"源码运行"模式升级为"可执行文件 + 用户目录分离"模式。用户通过 irm/curl 一键安装，获得 `harness` CLI 命令，配置和数据统一存放在 `~/.openharness/`。

## Section 1: Directory Layout & Path Resolution

### Installed Directory Structure

```
~/.openharness/
├── bin/
│   └── harness(.exe)         # PyInstaller 打包的 CLI 可执行
├── config/
│   ├── harness.yaml          # 默认配置模板
│   ├── mcp.yaml
│   ├── skill.yaml
│   └── .env.example          # 环境变量模板（不含密钥）
├── agents/
│   └── prompts/              # Agent 系统提示词（从 bundle 拷贝，用户可编辑）
│       ├── pm.md
│       ├── planner.md
│       ├── generator.md
│       ├── evaluator.md
│       ├── single.md
│       └── user.md
├── session/                  # 空，运行时写入
├── memory/
│   └── user_profile.md       # 默认空模板
├── skills/
│   └── user/                 # 用户自定义技能（空）
├── workspace/
│   └── .tasks/
├── .openharness/             # 项目级本地数据
│   └── knowledge_queue.db
├── .install-marker           # 安装标记文件
└── .env                      # 用户实际环境变量（API keys 等）
```

### Path Resolution Strategy

优先级从高到低：

1. 环境变量 `OPENHARNESS_HOME` → 如果设置了就用它
2. 默认 `~/.openharness/`

统一通过 `get_home()` 函数获取：

```python
def get_home() -> Path:
    return Path(os.environ.get("OPENHARNESS_HOME", str(Path.home() / ".openharness")))
```

### No-Overwrite Policy

安装时检查每个文件，已存在则跳过，只写入不存在的默认文件。

## Section 2: CLI Commands (click)

### Command Structure

```
harness run <prompt>                # CLI 模式，等同 python main.py
harness server start                # 启动飞书服务（前台）
harness server stop                 # 停止服务
harness server restart              # 重启服务
harness knowledge sync              # 知识同步
harness knowledge search <query>    # 知识搜索
harness knowledge status            # 知识状态
harness install                     # 初始化/修复 ~/.openharness/ 配置
harness info                        # 显示安装信息、路径、版本
harness version                     # 版本号
```

### Implementation

```python
# cli.py
@click.group()
def cli(): ...

@cli.command()
@click.argument("prompt")
def run(prompt): ...

@cli.group()
def server(): ...

@server.command()
def start(): ...             # subprocess 启动，写 PID 文件
@server.command()
def stop(): ...              # 读 PID，发 SIGTERM

@cli.group()
def knowledge(): ...
@knowledge.command()
def sync(): ...
@knowledge.command()
@click.argument("query")
def search(query): ...
@knowledge.command()
def status(): ...

@cli.command()
def install(): ...           # 初始化 ~/.openharness/
@cli.command()
def info(): ...
@cli.command()
def version(): ...
```

### Server Process Management

- PID file: `~/.openharness/.server.pid`
- `start`: 后台 fork 进程运行 FastAPI 服务，写 PID
- `stop`: 读 PID，发 SIGTERM（Windows 用 taskkill）
- `restart`: stop + start
- Windows 上用 `CREATE_NO_WINDOW` 避免弹窗

## Section 3: Code Changes

### New File: infrastructure/paths.py

```python
def get_home() -> Path:                    # ~/.openharness 或 $OPENHARNESS_HOME
def get_config_dir() -> Path:              # get_home() / "config"
def get_session_dir() -> Path:             # get_home() / "session"
def get_memory_dir() -> Path:              # get_home() / "memory"
def get_skills_dir() -> Path:              # get_home() / "skills"
def get_workspace_dir() -> Path:           # get_home() / "workspace"
def get_env_path() -> Path:                # get_home() / ".env"
def get_server_pid_path() -> Path:         # get_home() / ".server.pid"
def get_agent_prompts_dir() -> Path:       # get_home() / "agents" / "prompts"
def get_project_dir() -> Path:             # PyInstaller sys._MEIPASS 或源码根目录
```

### Files to Modify (5)

| File | Change |
|------|--------|
| `server.py` | `PROJECT_DIR`/`CONFIG_DIR` → `get_home()`/`get_config_dir()`；session_dir → `get_session_dir()` |
| `main.py` | 同上 |
| `agents/factory.py` | `SKILLS_DIR` → `get_skills_dir()`；config_dir → `get_config_dir()` |
| `config/config.py` | 所有 `load_*_config(project_dir)` 改为从 `get_home()` 取 `.env`，从 `get_config_dir()` 取 yaml |
| `infrastructure/session_manager.py` | `session_dir` 默认值改为 `get_session_dir()` |

### PyInstaller Resource Handling

- `skills/system/` 目录打包进可执行文件
- `agents/prompts/` 目录打包进可执行文件，首次运行时拷贝到 `~/.openharness/agents/prompts/`
- `get_project_dir()` 在打包时返回 `sys._MEIPASS`，开发时返回 `Path(__file__).parent`
- system skills 始终从 `get_project_dir() / "skills" / "system"` 读取
- agent prompts 从 `~/.openharness/agents/prompts/` 读取（`get_agent_prompts_dir()`），不在临时目录
- user skills 从 `get_skills_dir() / "user"` 读取

### Not in User Directory

- `skills/system/` — 跟随可执行文件
- `agents/`、`infrastructure/` — 编译进可执行文件

### In User Directory (User-Editable)

- `agents/prompts/` — 从 bundle 拷贝到 `~/.openharness/agents/prompts/`，用户可自定义 Agent 提示词

## Section 4: Installer Scripts

### Unified Flow

```
1. Banner
2. Check hard deps: Python 3.10+, uv, git
3. Check soft deps: Node.js (warn only)
4. Create ~/.openharness/ directory structure
5. Download pre-built harness binary from GitHub Release
6. Initialize default config files (no overwrite)
7. Add ~/.openharness/bin to PATH
8. Write install marker
9. Print summary
```

### install.ps1 (Windows)

```
Functions:
├── Write-Banner
├── Test-Python                     # hard dep
├── Install-Uv                      # winget → pip → manual
├── Test-Git                        # hard dep
├── Get-HarnessHome                 # ~/.openharness/
├── Initialize-DirectoryStructure
├── Install-HarnessBinary           # download from GitHub Release
├── Initialize-DefaultConfigs       # no overwrite
├── Set-PathVariable                # user PATH persist
├── Write-InstallMarker
└── Main                            # try/catch wrapper
```

Dependency priority: `winget → chocolatey → scoop → manual`

### install.sh (macOS/Linux)

```
Functions:
├── banner()
├── check_python()                  # hard dep
├── install_uv()                    # brew → pip → curl script
├── check_git()                     # hard dep
├── get_harness_home()
├── init_directory_structure()
├── install_harness_binary()
├── init_default_configs()
├── set_path_variable()             # ~/.bashrc / ~/.zshrc / ~/.profile
├── write_install_marker()
└── main()
```

Dependency priority: `brew → apt/yum/dnf → manual`

### Install Marker

```json
{
  "version": "1.0.0",
  "installed_at": "2026-04-28T10:00:00Z",
  "platform": "windows",
  "channel": "irm-install"
}
```

### One-line Install Commands

```powershell
# Windows
irm https://raw.githubusercontent.com/<org>/openharness/main/install.ps1 | iex
```

```bash
# macOS/Linux
curl -fsSL https://raw.githubusercontent.com/<org>/openharness/main/install.sh | bash
```

### CI/CD (GitHub Actions)

```yaml
# .github/workflows/release.yml
on:
  push:
    tags: ['v*']
jobs:
  build:
    strategy:
      matrix:
        include:
          - os: windows-latest
            artifact: harness.exe
          - os: macos-latest
            artifact: harness
          - os: ubuntu-latest
            artifact: harness
    steps:
      - uses: actions/checkout@v4
      - run: uv run pyinstaller cli.py --onefile --name harness
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/harness*
```

## Tech Stack

- **Packaging**: PyInstaller (onefile mode)
- **CLI**: click (subcommands, help generation)
- **Install Scripts**: PowerShell (Windows) + Bash (macOS/Linux)
- **CI/CD**: GitHub Actions (3-platform build + GitHub Release upload)
- **Process Management**: PID file + SIGTERM (Unix) / taskkill (Windows)
