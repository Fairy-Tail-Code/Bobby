# 进入此项目优先阅读

## 约束
开发之前必须建立worktree

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
- [2026-05-06-gateway-setup-feishu-weixin.md](docs/project_experience/2026-05-06-gateway-setup-feishu-weixin.md) — setup 直出二维码、飞书 domain 对齐、微信 gateway 接入
- [2026-05-09-memory-system-cc-haha-alignment.md](docs/project_experience/2026-05-09-memory-system-alignment) — Bobby 记忆系统对齐 cc-haha：MEMORY.md、load/save memory、prompt 注入、Agent 接入
- [2026-05-09-auto-memory-extraction.md](docs/project_experience/2026-05-09-auto-memory-extraction.md) — Session 收尾自动复盘对话，提炼 durable memory 并写回 MEMORY.md
- [2026-05-09-memory-merge-before-overwrite.md](docs/project_experience/2026-05-09-memory-merge-before-overwrite.md) — 自动抽取命中已有 memory 时先合并旧内容，仅在有效变化时写回
- [2026-05-09-rollback-default-worktree-change.md](docs/project_experience/2026-05-09-rollback-default-worktree-change.md) — 回滚误加到 Bobby 项目内的默认 worktree 开发逻辑，改为仅作为开发协作习惯
- [2026-05-09-weixin-hitl-cross-loop-fix.md](docs/project_experience/2026-05-09-weixin-hitl-cross-loop-fix.md) — 微信 HITL 跨事件循环修复：主 loop 发送桥接、线程安全 Future 注入
- [2026-05-09-beta-network-migration.md](docs/project_experience/2026-05-09-beta-network-migration.md) — 多 Agent 专家模式从 group chat/pattern 迁移到 AG2 beta network runtime
- [2026-05-09-deepseek-response-format-fallback.md](docs/project_experience/2026-05-09-deepseek-response-format-fallback.md) — DeepSeek 不支持 `response_format=json_schema` 时，专家模式降级为 prompt JSON contract + runtime 本地解析
- [2026-05-09-session-runtime-layering-refactor.md](docs/project_experience/2026-05-09-session-runtime-layering-refactor.md) — 将原 SwarmSession 拆为 AgentSession 壳层 + orchestration runtimes，清理 single/swarm 双路径混居
- [2026-05-10-reapply-deepseek-response-format-fix.md](docs/project_experience/2026-05-10-reapply-deepseek-response-format-fix.md) — 在 session/runtime 重构后，将被覆盖的 DeepSeek `response_format` 兼容修复重新补回主线
- [2026-05-18-beta-tool-ctx-validation.md](docs/project_experience/2026-05-18-beta-tool-ctx-validation.md) — AG2 beta MCP 工具桥动态签名修复：兼容 `__ctx__` 注入、零参数工具与可选参数省略
- [2026-05-18-beta-network-plaintext-fallback.md](docs/project_experience/2026-05-18-beta-network-plaintext-fallback.md) — AG2 beta network 非 schema 路径下纯文本回复降级：首轮 PM 提问不再因 JSON 校验失败中断 session
- [2026-05-18-beta-stream-ctx-callback.md](docs/project_experience/2026-05-18-beta-stream-ctx-callback.md) — AG2 beta `MemoryStream` / tool-call observer 的 `__ctx__` 兼容封装，修复第二轮工具调用时的 stream 回调校验失败
- [2026-05-18-deepseek-beta-prompted-schema.md](docs/project_experience/2026-05-18-deepseek-beta-prompted-schema.md) — 保留 AG2 前提下，将 DeepSeek beta 路径切回 `PromptedSchema + thinking disabled`，避免 `reasoning_content` 回放阻塞
- [2026-05-18-tool-call-notification-degrade.md](docs/project_experience/2026-05-18-tool-call-notification-degrade.md) — 工具调用前端通知降级为 best-effort，避免微信提示消息失败反向打断 AG2 beta session

## docs/AG2_knowledge/（AG2 框架知识库）

- [Swarm模式.md](docs/AG2_knowledge/Swarm模式.md) — Swarm 编排 API、Handoffs、OnCondition、ContextVariables、register_reply限制
- [Agent与工具注册.md](docs/AG2_knowledge/Agent与工具注册.md) — ConversableAgent 创建、Tool 注册、MCP 桥接
- [MCP集成.md](docs/AG2_knowledge/MCP集成.md) — openharness MCP 服务器列表、启动方式、连接方式、Skill-MCP依赖映射
- [Handoff机制.md](docs/AG2_knowledge/Handoff机制.md) — AG2 handoff tool call 机制、常见错误、MCP Server subprocess stdin 死锁坑
- [HITL.md](docs/AG2_knowledge/HITL.md) — Human-in-the-Loop 模式、多角色邮件代理、SMTP/IMAP 踩坑记录
- [飞书服务化.md](docs/AG2_knowledge/飞书服务化.md) — 飞书机器人常驻服务架构、组件交互、消息拦截、Future回复注入、使用方式
- [Gateway服务化.md](docs/AG2_knowledge/Gateway服务化.md) — Gateway 主 loop 与 AG2 工作线程的异步边界、跨 loop 桥接原则
- [记忆系统.md](docs/AG2_knowledge/记忆系统.md) — cc-haha 记忆系统拆解、AG2 中的 prompt 注入与 Tool 化落地方式
- [Network模式.md](docs/AG2_knowledge/Network模式.md) — beta network 的概念映射、runtime 路由、MemoryStream、beta tool 与 HITL 落地方式
- [Beta工具参数校验.md](docs/AG2_knowledge/Beta工具参数校验.md) — AG2 beta `FunctionTool` 的 `__ctx__` 注入、签名推断与 MCP 动态工具桥落地原则
- [Beta纯文本降级.md](docs/AG2_knowledge/Beta纯文本降级.md) — 非 schema 后端下 beta network 的 prompt JSON contract 与 runtime 纯文本兜底策略
- [Beta事件流上下文兼容.md](docs/AG2_knowledge/Beta事件流上下文兼容.md) — beta stream subscriber / MemoryStream history callback 与 `__ctx__` 注入的兼容处理
- [工具调用通知降级.md](docs/AG2_knowledge/工具调用通知降级.md) — beta `ToolCallEvent` 前端观察者应视为 best-effort，通知失败不应打断工具执行主链路
- [PromptedSchema与DeepSeek.md](docs/AG2_knowledge/PromptedSchema与DeepSeek.md) — 在 AG2 beta 中面向 DeepSeek 这类非原生 schema / thinking 模型的推荐落地方式
- [会话与运行时分层.md](docs/AG2_knowledge/会话与运行时分层.md) — AgentSession 与 runtime 的职责边界、何时该放在 session 层，何时该下沉到 orchestration
