# 2026-05-09 自动记忆抽取

## 背景

此前 `Bobby` 已具备长期记忆的基础设施能力：

- `MEMORY.md` 统一索引
- `load_memory` / `save_memory` 工具
- system prompt 注入

但记忆沉淀仍主要依赖 Agent 在对话进行中“主动想到要存”，缺少稳定的会话收尾复盘链路。

## 本次实现

- 新增 `infrastructure/memory/extractor.py`
- 在 session 完成或终止后，自动分析聊天记录
- 只提炼 durable memory，不保存可从代码和 git 推导的信息
- 提取结果复用现有 `save_memory_file(...)` 持久化
- 保存后自动刷新 `MEMORY.md`

## 配置项

在 `harness.memory` 下新增：

- `auto_extract_enabled`
- `max_auto_memories`

默认开启自动抽取，并限制单次会话最多沉淀少量记忆，避免记忆文件失控膨胀。

## 设计取舍

- 不在主对话流程中增加额外 handoff
- 不引入新的数据库或向量库
- 不单独维护第二套存储格式

因此自动抽取只是 session 的后处理步骤，最小化了对现有多 Agent 编排链路的侵入。
