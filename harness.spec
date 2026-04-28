# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OpenHarness CLI."""

import sys
from pathlib import Path

block_cipher = None

PROJECT = Path('.')

datas = [
    (str(PROJECT / 'skills' / 'system'), 'skills/system'),
    (str(PROJECT / 'agents' / 'prompts'), 'agents/prompts'),
    (str(PROJECT / 'install' / 'defaults'), 'install/defaults'),
]

a = Analysis(
    ['cli.py'],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'infrastructure.paths',
        'infrastructure.mcp_servers.shell_server',
        'infrastructure.mcp_servers.git_server',
        'infrastructure.mcp_servers.browser_server',
        'infrastructure.mcp_servers.workspace_server',
        'infrastructure.mcp_servers.docker_server',
        'infrastructure.mcp_servers.database_server',
        'infrastructure.mcp_servers.http_api_server',
        'infrastructure.mcp_servers.docs_web_server',
        'infrastructure.mcp_servers.gitee_server',
        'infrastructure.mcp_servers.claude_code_server',
        'infrastructure.mcp.manager',
        'infrastructure.mcp.tool_bridge',
        'infrastructure.skills.registry',
        'infrastructure.skills.tool',
        'infrastructure.skills.skill_inject',
        'infrastructure.session_manager',
        'infrastructure.swarm_session',
        'infrastructure.context.auto_compact',
        'infrastructure.context.snip',
        'infrastructure.feishu_bot',
        'infrastructure.channel.channel_feishu_service',
        'agents.factory',
        'agents.planner',
        'agents.generator',
        'agents.evaluator',
        'agents.PM',
        'agents.single',
        'agents.user',
        'agents.channel_proxy',
        'config.config',
        'orchestration.group',
        'utils.yaml_reader',
        'mcp',
        'mcp.server',
        'mcp.server.fastmcp',
        'mcp.types',
        'autogen',
        'click',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.testing'],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='harness',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
