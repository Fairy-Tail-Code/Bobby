● 现在全面了解了。以下是对比：

  ---
  Skill 读取机制对比：AG2_openharness vs cc-haha

  核心一致点

  ┌──────────────┬─────────────────────────────────────────────────────┬─────────────────────────────────┬──────────┐
  │     维度     │                       cc-haha                       │         AG2_openharness         │  一致？  │
  ├──────────────┼─────────────────────────────────────────────────────┼─────────────────────────────────┼──────────┤
  │ 文件格式     │ skill-name/SKILL.md + YAML frontmatter              │ skill-name/SKILL.md + YAML      │ 完全一致 │
  │              │                                                     │ frontmatter                     │          │
  ├──────────────┼─────────────────────────────────────────────────────┼─────────────────────────────────┼──────────┤
  │ Frontmatter  │ name, description, when_to_use, allowed-tools,      │ name, description, summary,     │ 部分一致 │
  │ 字段         │ arguments…                                          │ mcp_servers                     │          │
  ├──────────────┼─────────────────────────────────────────────────────┼─────────────────────────────────┼──────────┤
  │              │ 先注入 name+description+whenToUse（frontmatter      │ 先注入 summary                  │          │
  │ 渐进式披露   │ token 估算），调用时才加载完整内容                  │ 列表，load_skill() 时才返回完整 │ 思路一致 │
  │              │                                                     │  SKILL.md                       │          │
  ├──────────────┼─────────────────────────────────────────────────────┼─────────────────────────────────┼──────────┤
  │ 按需加载     │ SkillTool 调用时 getPrompt() 返回完整 markdown      │ load_skill(skill_name) 返回完整 │ 一致     │
  │              │                                                     │  SKILL.md                       │          │
  └──────────────┴─────────────────────────────────────────────────────┴─────────────────────────────────┴──────────┘

  关键差异

  1. 发现范围 — cc-haha 是多源的，AG2_openharness 是单源的

  cc-haha 从 5 个位置并行加载 skill：
  managed (组织策略) → user (~/.claude/skills/) → project (.claude/skills/) → additional (--add-dir) → legacy commands
  然后用 realpath 去重（处理 symlink 场景）。

  AG2_openharness 只从一个 skills/ 目录扫描。

  影响：当前可接受，但如果未来需要组织级 skill 或用户自定义 skill，需要扩展 SkillRegistry.roots。

  2. when_to_use vs summary — cc-haha 更智能

  cc-haha 有独立的 when_to_use 字段，用于告诉模型"什么时候该用这个 skill"，这个字段会被估算 token
  后注入到上下文中，帮助模型做主动决策。

  AG2_openharness 用 summary 替代，但 summary 是被动描述，缺少"触发条件"语义。

  例如，cc-haha 的做法是：
  name: backend-delivery
  description: Implement backend code changes...
  when_to_use: Use this skill when you need to write or modify backend Python/FastAPI code.
  而 AG2_openharness 只有：
  name: backend-delivery
  summary: "Implement backend code changes using workspace file tools and shell commands."

  3. 条件性 Skill（Conditional Skills）— cc-haha 有路径激活

  cc-haha 支持 paths frontmatter：
  paths:
    - "src/backend/**"
  只有当 agent 操作匹配路径的文件时，这个 skill 才被激活。这是"按文件上下文自动发现能力"。

  AG2_openharness 没有，skill 是静态分配给 agent 的（PLANNER_SKILLS = [...]）。

  4. Skill 热更新 — cc-haha 有文件监听

  cc-haha 有 skillChangeDetector.ts（311行），监听 skill 文件变化后自动重载。

  AG2_openharness 的 _cache 是首次扫描后永久缓存的。

  5. Skill 执行模型 — cc-haha 可以 fork 子 Agent

  cc-haha 的 frontmatter 有 context: fork 字段，skill 可以在一个独立的子 Agent 中运行，有自己的 token 预算和上下文。还有
   model 字段可以指定 skill 使用的模型。

  AG2_openharness 的 skill 只是注入 instruction 文本，没有独立的执行环境。

  ---
  结论

  底层机制一致（SKILL.md + frontmatter + 渐进式披露 + 按需加载），但 cc-haha 在上层有更多工程能力。对 AG2_openharness
  当前阶段来说，最值得补充的是 when_to_use 字段——改动极小（frontmatter 解析 + summary_block
  注入），但能让模型更准确地知道何时该调用哪个 skill。其他能力（多源发现、条件激活、热更新、fork
  执行）属于进阶需求，可以后续迭代。