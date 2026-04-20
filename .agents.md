# 进入此项目优先阅读

## 规则
1. 对于所有关键性变更，必须以markdown的形式写入 `docs/project_experience/` 中，并在下方目录中列出
2. 当用户在对话中提出新的需求而没有加到需求迭代.md，你需要主动更新需求迭代.md，如果是新的一天则新加一个标题，以天为迭代粒度
3. 对于AG2项目的理解和知识点，按不同功能、场景分类存入 `docs/AG2_knowledge/` 中，并在下方目录中列出

## docs/project_experience/（关键变更记录）

- [AG2_openharness开发经验.md](docs/project_experience/AG2_openharness开发经验.md) — 2026-04-09 架构决策、组件集成、文件变更清单
- [AG2_openharness开发经验.md](docs/project_experience/AG2_openharness开发经验.md) — 2026-04-10 MCP全量启用、Skill-MCP对齐、渐进式披露
- [AG2_openharness开发经验.md](docs/project_experience/AG2_openharness开发经验.md) — 2026-04-15 多角色邮件HITL、MCP subprocess死锁修复
- [AG2_openharness开发经验.md](docs/project_experience/AG2_openharness开发经验.md) — 2026-04-17 飞书产品化服务：WS桥接、Future回复注入、消息监控、session管理
- [AG2_openharness开发经验.md](docs/project_experience/AG2_openharness开发经验.md) — 2026-04-17 Session上下文持久化与恢复：SessionSnapshot、harness resume/list命令
- [AG2_openharness开发经验.md](docs/project_experience/AG2_openharness开发经验.md) — 2026-04-20 群聊用户识别（owner_open_id）、Workspace文件操作加锁（FileLock）

## docs/AG2_knowledge/（AG2 框架知识库）

- [Swarm模式.md](docs/AG2_knowledge/Swarm模式.md) — Swarm 编排 API、Handoffs、OnCondition、ContextVariables、register_reply限制
- [Agent与工具注册.md](docs/AG2_knowledge/Agent与工具注册.md) — ConversableAgent 创建、Tool 注册、MCP 桥接
- [MCP集成.md](docs/AG2_knowledge/MCP集成.md) — openharness MCP 服务器列表、启动方式、连接方式、Skill-MCP依赖映射
- [Handoff机制.md](docs/AG2_knowledge/Handoff机制.md) — AG2 handoff tool call 机制、常见错误、MCP Server subprocess stdin 死锁坑
- [HITL.md](docs/AG2_knowledge/HITL.md) — Human-in-the-Loop 模式、多角色邮件代理、SMTP/IMAP 踩坑记录
- [飞书服务化.md](docs/AG2_knowledge/飞书服务化.md) — 飞书机器人常驻服务架构、组件交互、消息拦截、Future回复注入、使用方式
