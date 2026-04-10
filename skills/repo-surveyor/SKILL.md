---
name: repo-surveyor
description: Inspect a repository and produce an implementation-oriented delivery survey.
summary: "Inspect repo structure, code patterns, and dependencies to produce a delivery-ready survey."
mcp_servers:
  - workspace
  - shell
---

# Repo Surveyor

Inspect the target repository before planning or coding.

Execution rules:
- Use `mcp__workspace__list_files` to discover top-level structure FIRST, then drill into specific subdirectories progressively. NEVER use recursive listing commands like `dir /s` or `find . -type`.
- Use `mcp__workspace__read_file` to read individual files, not shell commands that cat entire directories.
- Use `mcp__shell__run_command` only for lightweight, single-target inspection such as `python --version`, `npm list --depth=0`, or `cat package.json`. Never for recursive traversal.
- Do not modify files and do not run destructive shell commands.
- If you need to understand a directory, list it first, then read specific files of interest. Do not dump everything at once.

Return an implementation-oriented survey that covers:
- language, framework, package manager, and test stack
- source roots, entrypoints, config, migrations, UI surface, and API surface
- existing frontend, backend, and shared architecture conventions worth preserving
- local run, build, and test commands
- important constraints and unclear areas that downstream agents should respect

If the repository is empty or does not yet contain a usable application skeleton, say so explicitly.
When that happens, infer the minimal backend project skeleton that downstream agents should create from:
- the PRD language and framework constraints when they are already available in context
- otherwise the most conservative, conventional starter structure for the detected stack and requested topology

For an empty or skeletal repository, include:
- what is missing
- the minimal project scaffold that should be created first for each required subsystem
- the run and test commands that scaffold should support
