# Skill-MCP Alignment & Progressive Disclosure Design

Date: 2026-04-10

## Goal

1. Enable all 9 MCP servers
2. Align skills with their MCP dependencies via declarative frontmatter
3. Implement progressive disclosure: summary in system message, full instructions on demand via `load_skill` tool

## Architecture

### SKILL.md Frontmatter Extension

Add two fields to every SKILL.md frontmatter:

```yaml
---
name: browser-tester
description: Validate running applications with Playwright browser automation...
summary: "Use Playwright to validate running apps end-to-end with inspection, interaction, and screenshots."
mcp_servers:
  - browser
  - shell
---
```

- `summary`: 50-100 char one-liner for the skill catalog in system message. Fallback to `description`.
- `mcp_servers`: list of MCP server names this skill depends on. Validated at startup.

### SkillRegistry (replaces SkillLoader)

```python
@dataclass
class SkillMeta:
    name: str
    description: str
    summary: str
    mcp_servers: list[str]
    instruction_path: Path

@dataclass
class AlignmentIssue:
    skill_name: str
    missing_servers: list[str]
    level: str  # "warning"

class SkillRegistry:
    def __init__(roots, connected_servers): ...
    def list_skills() -> list[SkillMeta]: ...
    def get_summary(skill_name) -> str | None: ...
    def load_instruction(skill_name) -> str | None: ...
    def validate_alignment() -> list[AlignmentIssue]: ...
    def build_summary_block(skill_names) -> str: ...
```

### load_skill Tool

An AG2 Tool registered to each agent. When called with a skill name, returns the full SKILL.md content. This is the on-demand part of progressive disclosure.

### Progressive Disclosure Flow

1. **Startup**: Agent system message gets a "Skill Catalog" section listing name + summary for each assigned skill, plus the instruction: "Call `load_skill(skill_name)` to get full instructions."
2. **On-demand**: When the agent needs a specific skill, it calls `load_skill("browser-tester")` and receives the complete SKILL.md content in the conversation.
3. **Alignment check**: At startup, `SkillRegistry.validate_alignment()` logs warnings for skills whose MCP servers are not connected.

### Skill → MCP Dependency Map

| Skill | MCP Servers |
|-------|------------|
| repo-surveyor | workspace, shell |
| fullstack-analyst | workspace |
| backend-analyst | workspace |
| backend-delivery | workspace, shell |
| frontend-delivery | workspace, shell |
| bug-fixer | workspace, shell |
| git-operator | git |
| docker-operator | docker |
| runtime-python-toolchain | shell |
| runtime-node-toolchain | shell |
| runtime-go-toolchain | shell |
| browser-tester | browser, shell |
| api-tester | http_api |
| verification-gate | (none) |
| test-writer | workspace, shell |
| backend-reviewer | workspace, shell |
| fullstack-reviewer | workspace, shell |

### Files Changed

- `config/mcp.yaml` - uncomment all servers
- `skills/*/SKILL.md` - add summary + mcp_servers to frontmatter (15 files)
- `infrastructure/skills/registry.py` - new SkillRegistry class
- `infrastructure/skills/__init__.py` - re-export
- `agents/factory.py` - use SkillRegistry, inject summaries, register load_skill tool
