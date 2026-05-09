# 2026-05-09 Session Shell / Runtime 分层重构

## 背景

此前 `infrastructure/session/swarm_session.py` 同时承担了两类职责：

1. 会话壳层职责
   - chat 级生命周期
   - snapshot 持久化
   - reply 注入
   - memory / knowledge 收尾
2. 编排执行职责
   - `single` 模式下直接跑 legacy group chat
   - `swarm` 模式下直接创建并运行 beta network runtime

这种结构虽然能跑，但已经出现两个明显问题：

- `SwarmSession` 这个名字与真实职责不一致，因为它实际上还负责 `single` 模式
- 一个类内部同时承载两套执行路径，后续维护时很难判断“这里到底是 session 问题，还是 orchestration 问题”

## 本次重构目标

在不改变核心三层思路的前提下，把职责边界重新拉直：

- `infrastructure`：保留 session shell、channel、snapshot、memory/knowledge 收尾
- `orchestration`：承接所有“如何执行一次任务”的 runtime 逻辑
- `agents`：继续负责 agent 创建、工具注册、prompt 与 handoff 约束

## 实施方案

### 1. 重命名 session 壳层

- 删除 `infrastructure/session/swarm_session.py`
- 新增 `infrastructure/session/agent_session.py`
- `AgentSession` 只保留：
  - `start / start_resume / terminate / dispose`
  - snapshot 保存
  - reply 注入
  - memory extract / knowledge sync
  - 根据 mode 创建 runtime 并收口结果

### 2. 把 single 路径下沉到 orchestration

- 新增 `orchestration/single_runtime.py`
- 原本 `SwarmSession._run_single_session()` 里的 legacy group-chat 流程迁入该 runtime
- `SingleAgentRuntime` 负责：
  - 创建 single 模式 agent
  - 跑 `a_run_group_chat_iter`
  - 向前端发送中间文本 / tool call
  - 返回统一的运行结果

### 3. 为多 runtime 引入统一结果模型

- 新增 `orchestration/run_result.py`
- 用 `OrchestrationRunResult` 统一收口：
  - `transcript`
  - `last_speaker`
  - `status`

### 4. 引入 runtime factory

- 新增 `orchestration/runtime_factory.py`
- `AgentSession` 不再写死 `_run_single_session/_run_network_swarm`
- 改为：
  - `single` → `SingleAgentRuntime`
  - 其他专家模式 → `NetworkSwarmRuntime`

### 5. 清理会话层对私有字段的依赖

补了一轮小治理，避免只是“换名字不换耦合”：

- `session_manager` 不再直接依赖 `_channel.stop()`，改为 `dispose()`
- 新增 `AgentSession.mode / channel / task` 公开接口
- `cron` runner 不再读旧 `SwarmSession` 私有实现
- 删除无实际作用的 `hitl_mode` 透传参数

## 文件变更

- `infrastructure/session/agent_session.py`
- `infrastructure/session/session_manager.py`
- `infrastructure/cron/agent_runner.py`
- `orchestration/single_runtime.py`
- `orchestration/network_runtime.py`
- `orchestration/runtime_factory.py`
- `orchestration/run_result.py`
- `main.py`
- `cli.py`
- `server.py`
- `tests/test_single_runtime.py`
- `tests/test_network_runtime.py`

## 验证

通过以下定向验证：

- `tests/test_network_runtime.py`
- `tests/test_single_runtime.py`
- `tests/test_session_snapshots.py`

结果：

- `8 passed`

## 经验

1. session shell 与 runtime 最大的区别是：session 负责“这次任务活多久、如何收尾”，runtime 负责“任务过程中谁说话、怎么流转”。
2. 如果一个类同时承载生命周期和编排逻辑，迁移到新 runtime 后很容易留下“已经不适合的旧名字”和“双路径混居”问题。
3. 对这种迁移型代码，先统一返回结果模型，再拆 runtime，会比直接在原类里一点点剪代码更稳。
