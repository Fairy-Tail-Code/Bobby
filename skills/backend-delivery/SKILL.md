---
name: backend-delivery
description: Implement backend code changes in the target repository using workspace and shell MCP tools.
---

# Backend Delivery

Implement backend code changes directly in the workspace.

Execution rules:
- Preserve the repository's existing architecture, naming, and testing patterns.
- Use `mcp__workspace__apply_patch` for focused edits when practical. Use the other workspace file tools when creating or moving files is simpler.
- Use shell tools for targeted validation and inspection, not for broad or destructive system changes.
- Reconcile upstream plan, review findings, and repository constraints before editing.
- Do not add UI code.
- If the repository is empty or lacks a usable backend skeleton, create the minimal conventional project scaffold required by the PRD before implementing feature logic.
- When scaffolding is needed, infer it from the requested language, framework, and runtime constraints instead of requiring a separate bootstrap instruction.
- Keep the scaffold minimal: only the files, directories, dependencies, and configuration needed to build, run, test, and extend the requested backend.

Before finishing:
- ensure the changed files are internally consistent
- note any assumptions or unimplemented follow-up items
- summarize the concrete code changes and validation performed
