# 2026-05-09 Bobby 记忆系统

## 背景

`Bobby` 原先的长期记忆主要依赖 prompt 约束和 `memory_manager` skill，Agent 需要自己理解何时读写 `memory/` 目录，本质上是“提示词约定”，不是“系统能力”。


- 将 `MEMORY.md` 作为统一索引入口
- 将记忆类型显式建模为 `user / feedback / project / reference`
- 将记忆读写注册为 AG2 Tool，而不是只靠 skill 说明
- 将记忆索引注入到 system prompt，形成两层访问路径：
  - 第 1 层：启动时读取 `MEMORY.md`
  - 第 2 层：需要细节时调用 `load_memory`

## 本次实现

### 1. 新增 `infrastructure/memory/`

新增模块：

- `types.py`：`MemoryType`、`MemoryRecord`
- `paths.py`：解析记忆目录、索引文件、锁文件
- `store.py`：记忆文件保存、加载、扫描
- `index.py`：`MEMORY.md` 重建与截断读取
- `injection.py`：构建并注入 `## Project Memory` prompt block
- `tool.py`：注册 `load_memory` / `save_memory`

### 2. 记忆存储能力从“skill约定”升级为“内建工具”

原先 prompt 中只是告诉模型“使用 memory_manager 技能管理 memory”。

现在每个核心 Agent 都会：

- 自动注入 memory block
- 自动注册 `load_memory__<agent>` 工具
- 自动注册 `save_memory__<agent>` 工具

因此记忆行为不再依赖模型先想到去读某个 skill，而是直接成为工具层能力。

### 3. `MEMORY.md` 索引化

保存记忆时会自动重建 `MEMORY.md`，每条索引使用：

```md
- [Title](file.md) - one line description
```

同时保留了索引上限控制：

- `max_index_lines`
- `max_index_bytes`
- 单条索引长度截断

### 4. 兼容旧版 `user_profile.md`

考虑到 `Bobby` 旧安装结构中默认存在 `memory/user_profile.md`，本次扫描逻辑会把它当作 legacy user memory 暴露出来，避免历史用户资料在切换新结构后完全失联。

### 5. Agent 构造链同步接入

不仅更新了 `agents/factory.py`，还同步接入：

- `infrastructure/agent_pool.py`
- `infrastructure/session/swarm_session.py`

这样单次直建、模板池复用、session 恢复链路拿到的 Agent 都会拥有一致的 memory 能力。



本次实现优先落地的是 **记忆读写层**

已实现：

- `MEMORY.md` 索引入口
- 显式的四类记忆
- prompt 注入
- `load_memory` / `save_memory` 工具化
- 文件锁保护下的持久化


## 影响文件

- `config/config.py`
- `agents/factory.py`
- `infrastructure/agent_pool.py`
- `infrastructure/session/swarm_session.py`
- `agents/prompts/single.md`
- `agents/prompts/planner.md`
- `agents/prompts/generator.md`
- `agents/prompts/evaluator.md`
- `install/defaults/harness.yaml`
- `README.md`
- `tests/test_config.py`
- `tests/test_memory.py`
- `infrastructure/memory/*`

## 验证

由于当前环境没有现成的 `pytest` 可执行依赖，本次通过两类方式验证：

- 逐文件 `compile(...)` 语法校验
- 记忆保存 / 索引重建 / prompt 注入 / agent 构造的 smoke script 验证
