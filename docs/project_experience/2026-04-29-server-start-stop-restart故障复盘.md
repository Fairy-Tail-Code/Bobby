# 2026-04-29 server start/stop/restart 故障复盘

## 现象

用户最开始执行：

```powershell
harness server start
```

CLI 返回：

```text
Service started in background (PID 12880).
```

但后续继续执行：

```powershell
harness server restart
harness server stop
harness server start
```

出现了连续失败：

- `taskkill /PID 12880 /F` 返回非 0，CLI 抛 `CalledProcessError`
- `os.kill(pid, 0)` 在 Windows 上抛 `OSError: [WinError 11]`
- 用户从 `start` 看不到完整启动日志，只能看到一个 PID

## 根因

这次问题不是单点故障，而是三类问题叠加。

### 1. 后台启动把“Popen 成功”误判成“服务启动成功”

旧实现中，`harness server start` 默认走后台模式：

- `subprocess.Popen(...)` 一成功就立即写 `~/.openharness/.server.pid`
- 立刻回显 `Service started in background (PID ...)`

但这里验证的只是“子进程被创建过”，不是“服务已经完成初始化并持续存活”。

如果服务进程启动后很快退出：

- PID 文件会被保留下来
- CLI 仍然向用户宣称启动成功
- 后续 stop/restart/start 都会建立在错误状态上继续执行

### 2. Windows 下 stale PID 没有被正确识别和清理

旧实现有两个错误假设：

- 假设 `taskkill` 失败时会表现成 `ProcessLookupError`
- 假设 `os.kill(pid, 0)` 对失效 PID 会稳定抛 `ProcessLookupError`

但在这次 Windows 环境里，真实表现是：

- `taskkill /PID 12880 /F` 返回 `Access denied`
- `os.kill(12880, 0)` 抛 `OSError: [WinError 11]`

旧代码没有把这些错误当成 stale PID 处理，所以：

- `server stop` 直接崩
- `server restart` 因为先调用 `stop`，也直接崩
- `server start` 因为先读旧 PID 再检查，仍然会被卡住

### 3. CLI 默认后台启动，不利于诊断

用户期望 `harness server start` 的行为接近：

```powershell
python server.py
```

也就是：

- 直接在当前终端看到完整日志
- 能立刻看到配置、MCP、飞书服务等初始化异常

旧实现相反：

- 默认后台
- 默认只输出 PID
- 子进程异常不直接暴露给用户

这让“真实启动失败”被掩盖成了“看起来启动成功，后面命令陆续坏掉”。

## 这次排查中确认的事实

排查过程中确认了以下几点：

1. `~/.openharness/.server.pid` 中保留了旧 PID `12880`
2. 该 PID 已不再是最初的 harness 服务进程
3. Windows 对该 PID 的查询/终止表现为异常而不是“正常不存在”
4. 安装版 `harness.exe` 在当前沙箱环境中还额外触发了 PyInstaller 临时解包目录权限问题

第 4 点不是这次 CLI 逻辑 bug 的主根因，但说明 onefile 二进制在部分环境里还会受 `%TEMP%` 解包权限影响。同日还发现 Agent prompts 因从 `%TEMP%` 加载导致 `FileNotFoundError`（prompts 已迁移到 `~/.openharness/agents/prompts/`，见开发经验 2026-04-29 条目）。

## 修复方案

### 1. 调整 `server start` 默认行为

现在：

- `harness server start` 默认前台运行
- 直接输出完整日志
- 行为和 `python server.py` 对齐

后台启动改成显式选项：

```powershell
harness server start --background
```

### 2. 调整 `server restart` 默认行为

现在：

- `harness server restart` 默认前台重启
- `harness server restart --background` 才是后台重启

### 3. 为后台模式补日志文件

后台模式现在会把日志写到：

```text
~/.openharness/server.log
```

并新增：

```powershell
harness server logs
```

用于输出日志文件路径。

### 4. 统一 stale PID 自愈逻辑

现在 `server stop` / `server start --background` 会自动处理：

- PID 文件存在但进程已退出
- PID 文件内容损坏，无法解析为整数
- Windows 下 `taskkill` / `os.kill(pid, 0)` 的异常返回

这类情况都会被视为 stale PID，并清理 `~/.openharness/.server.pid`。

### 5. 后台启动增加最小存活检查

后台模式不再是 `Popen` 成功就算成功，而是：

1. 启动子进程
2. 等待短暂时间
3. 检查子进程是否立刻退出

如果秒退，则直接报错，并提示查看 `server.log`。

## 经验总结

### 1. “进程被拉起”不等于“服务启动成功”

凡是服务类 CLI：

- 不能把 `Popen` 成功当成健康启动
- 至少要有短暂存活检查
- 更好的是做 readiness/health check

### 2. PID 文件机制必须假设会脏

PID 文件天然不可靠，必须默认考虑：

- 进程已退出
- PID 被系统复用
- PID 文件内容损坏
- Windows 和 Unix 的错误模型不同

处理原则应该是：

- 优先自愈
- 不要把 stale PID 当成致命错误

### 3. 默认行为应优先可观测性

对开发/调试类命令：

- 默认前台输出日志比默认后台更合理
- 后台应该是显式 opt-in
- 如果后台运行，必须同步提供日志位置

### 4. Windows 进程管理不能照搬 Unix 假设

这次暴露出一个典型问题：

- `os.kill(pid, 0)` 在 Windows 上并不稳定等价于“检查进程是否存在”
- `taskkill` 的失败形式也不是 Python 标准异常那一套

因此跨平台进程管理逻辑必须针对 Windows 单独设计和测试。

### 5. 安装版二进制需要单独验证

源码运行通过，不代表 PyInstaller onefile 运行一定没问题。后续涉及 CLI/安装器/服务入口时，应该至少补以下验证：

- `python cli.py server start`
- 打包后的 `harness.exe server start`
- Windows 本机真实终端中的 `start/stop/restart`

## 后续建议

1. 如果继续保留 PyInstaller onefile，建议补一轮 `%TEMP%`/解包目录权限兼容性排查。
2. 可以考虑为后台模式增加 `status` 命令，而不是只依赖 PID 文件。
3. 如果服务后续更复杂，建议增加显式健康检查，而不是仅依赖“短暂未退出”。
4. 这类跨平台 CLI 行为，必须保留 Windows 回归测试。
