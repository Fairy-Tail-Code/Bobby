---
name: runtime-go-toolchain
description: Prepare a Go toolchain for the current repository when runtime inference selects Go.
---

# Go Runtime Provisioner

Prepare a usable Go toolchain for the current repository before language-specific build or test commands run.

Execution rules:
- Read the runtime inference payload from the system prompt first.
- Only act when the inferred language is `go`.
- Before provisioning or running Go commands, call `register_runtime_env` and set:
  - `GO111MODULE=on`
  - `GOPROXY=https://goproxy.cn`
- Use the shell MCP tools first to check whether Go is already available:
  - run `command -v go`
  - if found, run `go version`
- If `go` is not available, you MUST attempt provisioning before any `go build`, `go test`, or `go run` command.
- Prefer the shell MCP tools for provisioning when the runtime is Debian or Ubuntu based and has sufficient privileges:
  - first inspect the environment with commands such as `id`, `uname -a`, `cat /etc/os-release`, and `command -v apt-get`
  - when `apt-get` is available and the session has the needed privileges, run explicit install commands such as `apt-get update` followed by `apt-get install -y golang` or `apt-get install -y golang-go`
  - after installation, run `command -v go` and `go version`
- If shell-based installation is not possible, use the docker MCP tools to provision a minimal Go execution environment and clearly report how later build or test commands should run through that environment.
- After provisioning, if the Go binary path is outside the default PATH, call `register_runtime_env` again and append the resolved Go bin directory to `PATH`.
- Do not stop after reporting `go: not found`. Keep going until one of these is true:
  - Go is ready and verified with `go version`
  - shell-based install is impossible and docker-based provisioning also failed
- Keep provisioning steps explicit and concise. Report the final executable path, version, install method, and any environment variables required for later commands.

Return:
- whether the Go runtime is ready
- what was reused or provisioned
- any required environment variables or remaining limitations
