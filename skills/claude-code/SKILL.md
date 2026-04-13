---
name: claude-code
description: Claude Code integration skill — provides AI-assisted coding best practices, documentation queries, workflow guidance, and subagent coordination for high-quality code delivery.
summary: "Apply Claude Code best practices, documentation patterns, and workflow guidance during code implementation."
mcp_servers:
  - workspace
  - shell
---

# Claude Code Integration

Provides Claude Code documentation, best practices, and workflow guidance to improve code delivery quality.

## Documentation Topics

The following knowledge areas are available for consultation during implementation:

### Quickstart
- Claude Code CLI installation and basic usage
- Project setup and configuration patterns
- Environment and IDE integration

### Best Practices
- **Be Specific**: Clear, detailed prompts get better results
- **Iterate**: AI assistance is a dialogue, not a magic button
- **Review Always**: Always review AI-generated code
- **Test Thoroughly**: AI can make logical errors
- **Understand First**: Don't apply code you don't understand

### Common Workflows
1. **Bug Fixing**: Reproduce → Understand → Diagnose → Fix → Verify → Document
2. **Feature Development**: Plan → Design → Prototype → Iterate → Test → Review → Merge
3. **Code Review**: Scan → Analyze → Test → Discuss → Approve
4. **Refactoring**: Catalog → Understand → Plan → Execute → Verify → Document

### Settings & Configuration
- CLI settings and environment variables (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_DIR`)
- Configuration files (`~/.claude/settings.json`, `CLAUDE.md`)
- MCP server configuration (`~/.claude/mcp.json`)
- Model selection and context length tuning

### Troubleshooting
- Connection issues: check API key, network, Anthropic status
- Performance: reduce context size, use faster models for simple tasks
- Code quality: specify language, provide style guide, verify dependencies

### Subagents & Agent Teams
- Subagent creation for parallel execution of specialized tasks
- Agent team coordination for large-scale refactoring and multi-component features
- Resource constraints and concurrent subagent limits

### MCP (Model Context Protocol)
- Standardized connection to external tools and data sources
- Common servers: filesystem, database, git
- Configuration and security best practices

### Plugins & Extensions
- MCP servers for enhanced capabilities
- IDE integrations (VS Code, JetBrains, Neovim)
- Custom plugin creation

## Execution Rules

When applying Claude Code guidance during code generation:
- Follow the best practices for prompt clarity and specificity
- Use the recommended workflow patterns (bug fix, feature dev, refactoring)
- Apply security best practices: never hardcode secrets, use environment variables
- Break complex tasks into smaller, well-defined steps
- Always write tests for generated code and verify edge cases
- Maintain consistent coding standards and document AI-assisted decisions
- When scaffolding, keep it minimal — only what is needed to build, run, test, and extend

## Return

- Code changes following Claude Code best practices
- Documented assumptions and follow-up items
- Summary of patterns applied and validation performed
