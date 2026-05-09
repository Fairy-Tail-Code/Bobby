# 2026-05-09 回滚默认 worktree 开发改动

## 背景

本次开发中一度把“开发时优先使用 `git worktree`”误实现成了 `Bobby` 项目自身的默认行为，包括 prompt、Git MCP 能力和测试。

用户随后明确：

- 这不是 `Bobby` 的产品需求
- 只要求作为开发协作习惯执行
- 需要把已经落到项目代码里的相关改动全部回滚

## 本次处理

- 删除 `Git MCP` 中新增的 worktree 管理能力
- 回滚 `single / planner / generator` prompt 中的默认 worktree 开发约束
- 删除误加的 worktree 测试与知识文档
- 保留本次真正目标功能：`cc-haha` 风格记忆系统接入

## 结论

后续如果需要使用 `git worktree`，仅作为开发过程中的执行习惯，不再作为 `Bobby` 的默认产品能力或内建流程要求。
