# 任务：为 AG2_openharness 添加 Docker 容器化支持

## 目标
在项目根目录下新增 3 个文件，使项目能通过 `docker-compose up -d` 一键部署飞书服务模式（server.py）。

## 项目路径
`C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness`

## 背景
- 这是一个基于 AG2 框架的多智能体平台
- 入口是 `server.py`，启动一个 asyncio 长驻进程，通过飞书 WebSocket 长连接（lark_oapi）与飞书通信
- **不需要暴露 HTTP 端口**，容器只需能访问外网
- 项目使用 `uv` 管理依赖（所有 MCP server 都通过 `uv run python -m ...` 以 stdio 子进程方式启动）
- 项目有 `pyproject.toml` 和 `requirements.txt`（uv export 生成，748 行，带 hash）
- Python 版本：3.12
- 项目不使用数据库，无需额外数据服务

## 需要创建的文件

### 1. `.dockerignore`
排除以下内容以减小镜像体积：
```
__pycache__/
.claude/
.env
session/
Discarded_plan/
.git/
.gitignore
*.pyc
*.pyo
.python-version
.tasks/
*.md
!skills/*/SKILL.md
!skills/*/README.md
docs/
```

### 2. `Dockerfile`
要求：
- 基础镜像：`python:3.12-slim`
- 安装 `uv`（用于运行 MCP server 子进程）：使用官方安装方式 `COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/`
- 工作目录：`/app`
- 先复制 `pyproject.toml` 和 `requirements.txt`，然后安装依赖（利用 Docker 缓存层）
- 依赖安装命令：`uv pip install --system -r requirements.txt`（因为 requirements.txt 是 uv export 的完整锁定文件）
- 再复制剩余项目代码
- 入口：`CMD ["python", "server.py"]`
- 设置环境变量 `PYTHONUNBUFFERED=1` 确保日志实时输出
- 设置工作目录 `/app`

### 3. `docker-compose.yml`
要求：
- 服务名：`openharness`
- build context：`.`
- 使用 `host` 网络模式（`network_mode: host`），确保容器能访问宿主机网络和外部 API
- env_file：`.env`
- volumes 挂载：
  - `.env:/app/.env:ro`（只读）
  - `./config:/app/config:ro`（只读）
  - `./session:/app/session`（可读写，用于保存会话数据）
- restart：`unless-stopped`
- container_name：`ag2-openharness`

## 验收标准
1. 三个文件创建在项目根目录
2. `.dockerignore` 正确排除了不需要的文件
3. `Dockerfile` 能成功构建镜像（语法正确，层次合理）
4. `docker-compose.yml` 配置完整，能一键启动
5. 不修改任何现有文件

## 注意事项
- **不要修改任何现有文件！** 只新增 3 个文件
- 不要创建虚拟环境
- 不要安装任何包或下载任何库
- 只生成代码文件
