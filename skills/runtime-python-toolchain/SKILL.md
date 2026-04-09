---
name: runtime-python-toolchain
description: Prepare a Python runtime for the current repository when runtime inference selects Python.
---

# Python Runtime Provisioner

Prepare a usable Python runtime for the current repository before Python-specific build or test commands run.

Execution rules:
- Read the runtime inference payload from the system prompt first.
- Only act when the inferred language is `python`.
- Before provisioning or running Python commands, call `register_runtime_env` and set:
  - `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`
  - `PIP_TRUSTED_HOST=mirrors.aliyun.com`
- Use the shell MCP tools first to check whether Python is already available:
  - run `command -v python3`
  - if not found, run `command -v python`
  - if found, run `python3 --version` or `python --version`
- If neither `python3` nor `python` is available, you MUST attempt provisioning before any `pytest`, `python`, `python3`, or other Python-specific command.
- Prefer the shell MCP tools for provisioning when the runtime is Debian or Ubuntu based and has sufficient privileges:
  - first inspect the environment with commands such as `id`, `uname -a`, `cat /etc/os-release`, and `command -v apt-get`
  - when `apt-get` is available and the session has the needed privileges, run explicit install commands such as `apt-get update` followed by `apt-get install -y python3 python3-pip`
  - after installation, run `command -v python3`, `python3 --version`, and if needed `python3 -m pip --version`
- If shell-based installation is not possible, use the docker MCP tools to provision a minimal Python execution environment and clearly report how later build or test commands should run through that environment.
- After provisioning, if the Python binary path is outside the default PATH, call `register_runtime_env` again and append the resolved bin directory to `PATH`.
- Do not stop after reporting `python: not found` or `python3: not found`. Keep going until one of these is true:
  - Python is ready and verified with `python3 --version` or `python --version`
  - shell-based install is impossible and docker-based provisioning also failed
- Report the executable path, version, install method, and any environment variables needed for later commands.

Return:
- whether the Python runtime is ready
- what was reused or provisioned
- any required environment variables or remaining limitations
