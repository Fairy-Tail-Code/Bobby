# Multi-Agent Harness Design

基于 AG2 框架的三智能体全栈应用生成 Harness。

## 核心原则

1. **生成与评估分离**：Generator 和 Evaluator 是独立智能体，避免自我评估偏宽松
2. **轻量编排**：用 AG2 GroupChat auto 模式，提示词引导发言顺序，不硬控流程，允许自由讨论
3. **可插拔**：上下文管理、MCP 服务器、评分标准通过配置切换
4. **三层解耦**：基础设施 → Agent 设计 → 编排，每层只依赖下层接口

## 架构：三层设计

```
┌─────────────────────────────────────┐
│  orchestration/ (Agent 编排)         │  GroupChat auto 模式 + 终止条件
├─────────────────────────────────────┤
│  agents/ (Agent 设计)                │  Planner / Generator / Evaluator
├─────────────────────────────────────┤
│  infrastructure/ (基础设施)           │  MCP / Skills / Context
└─────────────────────────────────────┘
```

## 项目结构

```
AG2_openharness/
├── config/
│   ├── llm.yaml                    # LLM provider（OpenAI 兼容接口）
│   ├── mcp.yaml                    # MCP 服务器连接配置
│   └── harness.yaml                # Harness 行为配置
├── infrastructure/
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── manager.py              # MCP 服务器生命周期管理
│   │   └── clients/
│   │       ├── shell.py
│   │       ├── git.py
│   │       ├── docker.py
│   │       └── browser.py
│   ├── skills/
│   │   ├── __init__.py
│   │   └── loader.py               # 加载 openharness 的 skill 定义
│   └── context/
│       ├── __init__.py
│       ├── base.py                 # 上下文策略接口
│       └── compaction.py           # 自动压缩
├── agents/
│   ├── __init__.py
│   ├── planner.py
│   ├── generator.py
│   ├── evaluator.py
│   ├── prompts/
│   │   ├── planner.md
│   │   ├── generator.md
│   │   └── evaluator.md
│   └── tools/
│       ├── __init__.py
│       ├── planner_tools.py
│       ├── generator_tools.py
│       └── evaluator_tools.py
├── orchestration/
│   ├── __init__.py
│   ├── group.py                    # GroupChat + GroupChatManager
│   ├── termination.py              # 终止条件
│   └── speaker_selection.py        # auto 模式描述优化
├── main.py
└── requirements.txt
```

## 三智能体定义

### Planner

- **输入**：用户 1~4 句 prompt
- **输出**：结构化产品规格（功能列表、技术架构、视觉设计方向、AI 功能建议）
- **原则**：只定义 What，不规定 How
- **工具**：无外部工具，纯 LLM 推理
- **发言引导**：description 强调"收到用户需求后首先发言，将需求扩展为规格"

### Generator

- **输入**：Planner 的产品规格 + Evaluator 的反馈
- **职责**：构建全栈应用（React + Vite + FastAPI + SQLite + Git）
- **工具**：Shell、Git、Docker、Workspace、Browser MCP
- **评估反馈处理**：得分趋势良好→精修；方向不对→重构
- **发言引导**：description 强调"收到规格后构建应用，收到评估反馈后修复问题"

### Evaluator

- **输入**：Generator 构建的应用（通过 Playwright 交互）
- **职责**：按四维标准评分，输出 Bug 报告（文件行号、根因）
- **工具**：Browser/Playwright MCP、Shell MCP
- **评分维度**：

| 维度 | 权重 | 最低阈值 |
|------|------|----------|
| 设计质量 | 高 | 7 |
| 原创性 | 高 | 7 |
| 工艺 | 低 | 5 |
| 功能性 | 低 | 5 |

- **发言引导**：description 强调"应用构建完成后自动评审，给出评分和改进建议"

## 编排方式

- **模式**：AG2 GroupChat `select_speaker_method="auto"`
- **引导策略**：通过精心编写的 Agent description 让 LLM 自然理解发言顺序，不硬控
- **允许自由讨论**：智能体之间可以互相追问、澄清、讨论
- **终止条件**：Evaluator 全维度通过，或达到 max_round（默认 15 轮）
- **用户参与**：仅提供初始 prompt，之后智能体自主运作

## 配置设计

### llm.yaml

三个 Agent 支持不同模型和参数：
- Planner：temperature 0.7（偏创造）
- Generator：temperature 0.4（偏确定性）
- Evaluator：temperature 0.2（偏一致性）

通过 OpenAI 兼容接口配置，支持任意 provider。

### mcp.yaml

复用 openharness 的 MCP 服务器进程（stdio 模式）：
- shell、git、browser、workspace

### harness.yaml

评估轮数、评分阈值、技术栈、上下文策略均可配置。

## 上下文管理

- 当前策略：AG2 SDK 自动 compaction
- 通过 `infrastructure/context/base.py` 接口预留可插拔能力
- 未来可扩展：上下文重置（清空上下文 + 结构化交接文件传递状态）

## 复用策略

- **共享**：openharness 的 Skill 定义（skill.yaml/instruction.md）和 MCP 服务器（stdio 进程）
- **不共享**：openharness 的架构、Agent 编排、工作流引擎

## 首个交付目标

全栈应用生成：用户输入 prompt → Planner 扩展规格 → Generator 构建应用 → Evaluator 评估循环 → 输出可运行的全栈应用。
