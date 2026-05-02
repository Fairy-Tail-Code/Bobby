node.exe : Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin 
explicitly: < /dev/null to skip, or wait longer.
所在位置 C:\Users\WUJIEAI\AppData\Roaming\npm\claude.ps1:24 字符: 5
+     & "node$exe"  "$basedir/node_modules/@anthropic-ai/claude-code/cl ...
+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (Warning: no std...or wait longer.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
所有 4 个修复已应用到 3 个文件中 (49 次插入，7 次删除):

| 优先级 | 修复项 | 文件 |
|----------|-----|---------|
| P0-1 | `async dispose()` + `_cleanup_session` fire-and-forget | `swarm_session.py`, `session_manager.py` |
| P0-2 | `max_messages` 60→40, `max_tokens` 80k→60k | `config.py` |
| P1 | `_on_complete` try/except + `inject_reply` wait_for(10s) | `swarm_session.py`, `session_manager.py` |
| P2 | 动态休眠：2s 活动 / 5s 空闲 | `swarm_session.py` |

未更改 TerminateTarget handoff 或 termination 逻辑。
