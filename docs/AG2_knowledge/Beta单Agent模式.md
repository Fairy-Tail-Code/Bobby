# Beta单Agent模式

## 结论

- 单 Agent 也可以走 `autogen.beta.Agent`，不需要为了普通模式单独保留 `ConversableAgent + UserProxy + group chat`。
- 对当前项目，更稳妥的做法是让 `single` 和 `swarm` 共享：
  - beta tool bridge
  - beta provider config
  - beta stream observers
  - beta context middleware

## 推荐编排方式

- 不再依赖 legacy handoff 关键词路由。
- 给单 Agent 一个显式结构化 contract，例如：
  - `message`
  - `next_step`
- `next_step` 只保留单 Agent 需要的值：
  - `ask_user`
  - `complete`
  - `terminate`

## 好处

1. Provider 兼容问题只修一套。
2. MCP / memory / skill 工具桥只维护一套 beta 版本。
3. 前端流式观察、tool-call 提示、context 裁剪只维护一套。
4. session shell / gateway / channel 层无需感知 single 与 swarm 的底层差异。

## 注意点

- beta single runtime 不能直接照搬 multi-agent network 的角色路由，但可以复用同样的事件桥与结构化输出模式。
- 对 DeepSeek 这类非原生 schema provider，仍应沿用 `PromptedSchema + 本地去围栏解析`。
