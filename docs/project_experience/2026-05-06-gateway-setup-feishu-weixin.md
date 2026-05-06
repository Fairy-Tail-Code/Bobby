# 2026-05-06 setup 直出二维码与飞书/微信 Gateway 接入

## 背景

项目原先的 `harness setup` 对飞书保留了手填 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 的分支，二维码路径在缺少 `qrcode` 依赖时只会给出 URL，安装后的首轮 setup 体验和 Hermes 的“终端直接扫码建 bot”模式不一致。

同时 `harness server` 入口写死为飞书服务，无法承载新的微信 gateway 需求。

## 本次决策

### 1. `harness setup` 统一承担 gateway 选择与扫码注册

- `hitl.mode` 选项扩展为 `stdin | email | dingtalk | gateway`
- `harness.hitl.gateways` 作为独立列表字段保存已启用平台，例如：
  - `["feishu"]`
  - `["weixin"]`
  - `["feishu", "weixin"]`
- setup 中 gateway 选择改为终端多选式交互，支持连续勾选多个平台
- 选择 `feishu` 时，setup 直接进入二维码注册流程，自动写回：
  - `FEISHU_APP_ID`
  - `FEISHU_APP_SECRET`
  - `FEISHU_DOMAIN`
- 选择 `weixin` 时，setup 直接进入腾讯 iLink 二维码登录流程，自动写回：
  - `WEIXIN_ACCOUNT_ID`
  - `WEIXIN_TOKEN`
  - `WEIXIN_BASE_URL`
  - `WEIXIN_HOME_CHANNEL`（若扫码返回）
- 删除 setup 中额外的“现在手工配置飞书服务凭据吗”分支，避免重复配置
- gateway 配置在全部扫码成功后再写入 `harness.yaml`，避免半配置状态

### 2. `harness server` 改为通用 gateway 入口

- `server.py` 改为只接受 `hitl.mode = gateway`
- 启动前解析 `harness.hitl.gateways`，按平台逐个创建：
  - `FeishuBotService`
  - `WeixinBotService`
- 未选择任何 gateway 时直接抛出配置错误，提醒重新运行 `harness setup`
- 运行时允许飞书、微信同时在线

### 3. 飞书 runtime 对齐 Hermes 的 domain 处理

- `FeishuConfig` 增加 `domain`
- `FeishuBotService` 创建 REST Client 和 WS Client 时都显式带上 `FEISHU_DOMAIN` / `LARK_DOMAIN`
- setup 扫码返回后把 domain 一起写入 `.env`

### 4. 微信 runtime 采用“最小可维护”实现

- 新增 `gateway/weixin/weixin_onboard.py`
  - 负责二维码登录
  - 暴露最小 iLink API helper（`get_updates` / `send_text_message`）
- 新增 `gateway/weixin/weixin_bot.py`
  - 用长轮询接收消息
  - 只实现当前项目需要的文本收发与 reply injection
- 新增 `gateway/weixin/channel_weixin_service.py`
  - 复用现有 Future 注入式 HITL channel 模式

这个实现没有把 Hermes 的整套 platform framework 完整搬进来，而是只保留 Bobby 现阶段需要的能力，减少本地 CLI 项目的维护负担。

### 5. 多 gateway 共用一个 `SessionManager`

- 引入 `MultiGatewayFrontend` 作为出站消息复用层
- `SessionManager` 仍然只保留一个实例，避免把会话、快照、注入回复、重启逻辑拆散
- 通过 `platform::chat_id` 形式编码 chat_id：
  - 飞书消息进入时写成 `feishu::<chat_id>`
  - 微信消息进入时写成 `weixin::<chat_id>`
- `SessionManager` 内部仍按 chat_id 唯一键管理 session，因此天然支持：
  - 不同平台消息隔离
  - 同一套 resume/list/restart 逻辑
  - 同一套 `ChannelUserProxyAgent` / `SessionSnapshot` 机制
- 出站时再按 chat_id 前缀解码，路由回对应 gateway 的 bot/channel service

## 依赖与模板

- `pyproject.toml` 新增：
  - `aiohttp`
  - `cryptography`
  - `qrcode`
- 更新根目录与安装模板里的 `.env.example`
- README 命令说明改为通用 gateway

## 影响文件

- `cli.py`
- `server.py`
- `config/config.py`
- `main.py`
- `gateway/feishu/feishu_bot.py`
- `gateway/feishu/feishu_onboard.py`
- `gateway/weixin/weixin_onboard.py`
- `gateway/weixin/weixin_bot.py`
- `gateway/weixin/channel_weixin_service.py`
- `install/defaults/harness.yaml`
- `.env.example`
- `install/defaults/.env.example`
- `pyproject.toml`
- `README.md`
- `docs/requirement/4.9需求迭代.md`
- `AGENTS.md`
