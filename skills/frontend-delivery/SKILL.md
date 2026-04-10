---
name: frontend-delivery
description: Implement frontend code changes in the target repository using workspace and shell MCP tools.
summary: "Implement frontend code changes using workspace file tools and shell commands."
mcp_servers:
  - workspace
  - shell
---

# Frontend Delivery

Implement frontend code changes directly in the workspace.

Execution rules:
- Preserve the repository's existing architecture, naming, and testing patterns.
- Use `mcp__workspace__apply_patch` for focused edits when practical. Use the other workspace file tools when creating or moving files is simpler.
- Use shell tools for targeted validation and inspection, not for broad or destructive system changes.
- Reconcile upstream plan, review findings, and repository constraints before editing.
- Focus on browser-facing UI, client-side routing, state management, accessibility, and integration with backend contracts.
- If the repository is empty or lacks a usable frontend skeleton, create the minimal conventional Node-based frontend scaffold required by the PRD before implementing feature behavior.
- Keep the scaffold minimal: only the files, directories, dependencies, and configuration needed to build, run, test, and extend the requested frontend.

Before finishing:
- ensure the changed files are internally consistent
- note any assumptions or unimplemented follow-up items
- summarize the concrete code changes and validation performed
