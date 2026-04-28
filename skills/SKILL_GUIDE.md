# SKILL Creation Guide

This guide describes how to create a new skill that the system can discover, load, and assign to agents.

## Directory Layout

```
skills/
  system/           # built-in skills shipped with the platform
    my-skill/
      SKILL.md      # required — the skill definition file
  user/             # user-defined skills (same structure)
    my-custom-skill/
      SKILL.md
```

Each skill lives in its own subdirectory. The directory name is the default identifier; the `name` field in frontmatter overrides it.

## SKILL.md Format

A SKILL.md file has two parts: **YAML frontmatter** and **Markdown body**.

### Frontmatter (required)

```yaml
---
name: my-skill
description: One sentence explaining what this skill does.
summary: "Short summary injected into the agent system message."
mcp_servers:
  - workspace
  - shell
---
```

| Field | Required | Description |
|---|---|---|
| `name` | yes | Unique identifier used in `config/skill.yaml` assignments |
| `description` | yes | Full description of the skill's purpose |
| `summary` | yes | One-line version shown in the agent's skill catalog |
| `mcp_servers` | yes | List of MCP server names this skill needs. Use `[]` if none |

### Available MCP Servers

These names must match the keys in `config/mcp.yaml` under `mcp_servers`:

| Name | Purpose |
|---|---|
| `workspace` | Read/write files in the target repository |
| `shell` | Execute shell commands |
| `git` | Git operations (diff, commit, log) |
| `gitee` | Gitee API integration |
| `browser` | Playwright browser automation |
| `docker` | Docker / Docker Compose operations |
| `database` | Database query and migration |
| `http_api` | HTTP request and OpenAPI inspection |
| `docs_web` | Web documentation lookup |
| `claude_code` | Delegate coding tasks to Claude Code subprocess |

### Body (Markdown)

The body is the instruction text loaded into the agent when the skill is activated. Typical sections:

```markdown
# Skill Title

Brief purpose statement.

## Execution rules
- Concrete behavioral constraints
- What to do and what NOT to do
- Preference order when multiple approaches exist

## Return
- Expected output format (JSON schema, text, etc.)
- Required fields the caller expects
```

Keep instructions precise and actionable. The agent reads this verbatim at runtime.

## Assignment to Agents

After creating a skill, register it in `config/skill.yaml`:

```yaml
skills:
  planner:
    - my-skill          # add skill name here
  generator:
    - my-skill

mcp_servers:
  planner:
    - workspace         # must cover all mcp_servers declared in SKILL.md
  generator:
    - workspace
```

**Rule:** The agent's `mcp_servers` list must be a superset of all `mcp_servers` declared in its assigned skills. The system logs a warning on startup if any dependency is missing.

## Discovery

`SkillRegistry` scans all subdirectories under `skills/system/` and `skills/user/` that contain a `SKILL.md` file. No additional registration is needed beyond placing the file.

## Checklist

1. Create directory under `skills/system/` or `skills/user/`
2. Write `SKILL.md` with valid frontmatter (`name`, `description`, `summary`, `mcp_servers`)
3. Write actionable body instructions
4. Add the skill name to the target agent role(s) in `config/skill.yaml`
5. Ensure the agent's `mcp_servers` in `config/skill.yaml` covers the skill's dependencies
6. Restart the service — check logs for alignment warnings
