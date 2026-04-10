---
name: runtime-node-toolchain
description: Prepare a Node.js runtime for the current repository when runtime inference selects Node.js.
summary: "Prepare Node.js runtime environment and validate toolchain availability."
mcp_servers:
  - shell
---

# Node Runtime Provisioner

Prepare a usable Node.js runtime for the current repository before Node-specific build or test commands run.

Execution rules:
- Read the runtime inference payload from the system prompt first.
- Only act when the inferred language is `node`.
- Before provisioning or running Node.js commands, call `register_runtime_env` and set:
  - `NPM_CONFIG_REGISTRY=https://registry.npm.aliyun.com/`
- Use the shell MCP tools first to check whether Node.js is already available:
  - run `command -v node`
  - if found, run `node --version`
- If `node` is not available, you MUST attempt provisioning before any `npm test`, `pnpm test`, `yarn test`, `node`, or other Node.js-specific command.
- Prefer the shell MCP tools for provisioning when the runtime is Debian or Ubuntu based and has sufficient privileges:
  - first inspect the environment with commands such as `id`, `uname -a`, `cat /etc/os-release`, and `command -v apt-get`
  - when `apt-get` is available and the session has the needed privileges, run explicit install commands such as `apt-get update` followed by `apt-get install -y nodejs npm`
  - after installation, run `command -v node`, `node --version`, and if needed `npm --version`
- If shell-based installation is not possible, use the docker MCP tools to provision a minimal Node.js execution environment and clearly report how later build or test commands should run through that environment.
- After provisioning, if the Node.js binary path is outside the default PATH, call `register_runtime_env` again and append the resolved bin directory to `PATH`.
- Do not stop after reporting `node: not found`. Keep going until one of these is true:
  - Node.js is ready and verified with `node --version`
  - shell-based install is impossible and docker-based provisioning also failed
- Report the executable path, version, install method, and any environment variables needed for later commands.

Return:
- whether the Node.js runtime is ready
- what was reused or provisioned
- any required environment variables or remaining limitations
