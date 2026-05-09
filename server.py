"""AG2 OpenHarness gateway service entry point.

Usage:
    python server.py
"""
from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable

from config.config import (
    load_llm_config, load_mcp_config, load_harness_config,
    load_feishu_config,
    load_weixin_config,
    ConfigError,
)
from config.cron_config import load_cron_config
from gateway.feishu.feishu_bot import FeishuBotService
from gateway.feishu.channel_feishu_service import ChannelFeishuService
from gateway.weixin.weixin_bot import WeixinBotService
from gateway.weixin.channel_weixin_service import ChannelWeixinService
from infrastructure.mcp.manager import create_mcp_manager
from infrastructure.agent_pool import AgentPool
from infrastructure.cron import TaskScheduler
from infrastructure.mcp_servers.agent_cron_server import set_task_scheduler
from utils.paths import (
    get_session_dir, get_system_skills_dir, get_user_skills_dir,
)
from infrastructure.session.session_manager import SessionManager
from infrastructure.skills.registry import SkillRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_GATEWAY_CHAT_ID_SEPARATOR = "::"


def _encode_gateway_chat_id(platform: str, chat_id: str) -> str:
    return f"{platform}{_GATEWAY_CHAT_ID_SEPARATOR}{chat_id}"


def _decode_gateway_chat_id(chat_id: str) -> tuple[str, str]:
    if _GATEWAY_CHAT_ID_SEPARATOR not in chat_id:
        raise ConfigError(f"Invalid gateway chat_id: {chat_id!r}")
    platform, raw_chat_id = chat_id.split(_GATEWAY_CHAT_ID_SEPARATOR, 1)
    return platform, raw_chat_id


class MultiGatewayFrontend:
    """Frontend multiplexer that routes outbound messages by chat_id prefix."""

    def __init__(self, frontends: dict[str, object]) -> None:
        self._frontends = frontends

    def _resolve(self, chat_id: str) -> tuple[object, str]:
        platform, raw_chat_id = _decode_gateway_chat_id(chat_id)
        frontend = self._frontends.get(platform)
        if frontend is None:
            raise ConfigError(f"Unsupported gateway platform: {platform!r}")
        return frontend, raw_chat_id

    async def send_text(self, chat_id: str, text: str) -> None:
        frontend, raw_chat_id = self._resolve(chat_id)
        await frontend.send_text(raw_chat_id, text)

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        frontend, raw_chat_id = self._resolve(chat_id)
        await frontend.stream_token(raw_chat_id, agent_name, token)

    async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
        frontend, raw_chat_id = self._resolve(chat_id)
        await frontend.on_tool_call(raw_chat_id, agent_name, tool_name)


def _resolve_gateway_platforms(mode: str, gateways: list[str]) -> list[str]:
    if mode == "gateway":
        return [platform for platform in gateways if platform in {"feishu", "weixin"}]
    if mode in {"feishu", "weixin"}:
        return [mode]
    return []


def _build_gateway(
    *,
    platform: str,
    session_manager: SessionManager,
) -> tuple[str, object, Callable[[str], object]]:
    async def _dispatch(chat_id: str, open_id: str, chat_type: str, text: str) -> None:
        await session_manager.handle_message(
            _encode_gateway_chat_id(platform, chat_id),
            open_id,
            chat_type,
            text,
        )

    if platform == "feishu":
        feishu_config = load_feishu_config()
        if not feishu_config.app_id or not feishu_config.app_secret:
            raise ConfigError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET，请重新运行 'harness setup' 完成飞书扫码配置。")
        bot = FeishuBotService(
            app_id=feishu_config.app_id,
            app_secret=feishu_config.app_secret,
            domain=feishu_config.domain,
            on_message=_dispatch,
        )
        channel_factory = lambda chat_id: ChannelFeishuService(bot, chat_id)
        return "Feishu", bot, channel_factory

    if platform == "weixin":
        weixin_config = load_weixin_config()
        if not weixin_config.account_id or not weixin_config.token:
            raise ConfigError("缺少 WEIXIN_ACCOUNT_ID / WEIXIN_TOKEN，请重新运行 'harness setup' 完成微信扫码配置。")
        bot = WeixinBotService(
            account_id=weixin_config.account_id,
            token=weixin_config.token,
            base_url=weixin_config.base_url,
            on_message=_dispatch,
        )
        channel_factory = lambda chat_id: ChannelWeixinService(bot, chat_id)
        return "Weixin", bot, channel_factory

    raise ConfigError(
        f"Unsupported gateway platform: {platform!r}."
    )


async def main() -> None:
    """Initialize all services and run forever. Supports in-process restart via restart_event."""
    restart_event = asyncio.Event()

    while True:
        restart_event.clear()

        # 1. Load configs
        logger.info("Loading configs...")
        llm_config = load_llm_config()
        mcp_config = load_mcp_config()
        harness_config = load_harness_config()
        cron_config = load_cron_config()
        # 2. Initialize skill registry
        system_skills_dir = get_system_skills_dir()
        user_skills_dir = get_user_skills_dir()
        skill_registry = SkillRegistry(roots=[system_skills_dir,user_skills_dir])
        logger.info("Available skills: %s", [s.name for s in skill_registry.list_skills()])

        # 3. Connect MCP servers
        logger.info("Connecting to MCP servers...")
        async with create_mcp_manager(mcp_config) as mcp_manager:
            connected_servers = mcp_manager.list_servers()

            # 检查是否有 skill缺少必要的 MCP 工具。
            skill_registry.connected_servers = connected_servers
            for issue in skill_registry.validate_alignment():
                logger.warning(
                    "Skill '%s' needs MCP servers %s but %s not connected",
                    issue.skill_name, issue.missing_servers, issue.missing_servers,
                )

            # 3.5. Initialize agent pool (pre-create agent templates with tools/skills)
            logger.info("Initializing agent pool...")
            agent_pool = AgentPool(
                llm_config=llm_config,
                mcp_manager=mcp_manager,
                skill_registry=skill_registry,
                harness_config=harness_config,
            )
            agent_pool.initialize()
            logger.info("Agent pool ready — agents will be cloned from templates on demand")

            # 4. Get session dir from paths
            session_dir = str(get_session_dir())

            # 5. Create SessionManager (bot set later)
            session_manager = SessionManager(
                frontend=None,
                mcp_manager=mcp_manager,
                llm_config=llm_config,
                harness_config=harness_config,
                skill_registry=skill_registry,
                session_dir=session_dir,
                restart_event=restart_event,
                agent_pool=agent_pool,
            )

            gateway_platforms = _resolve_gateway_platforms(
                harness_config.hitl.mode,
                harness_config.hitl.gateways,
            )
            if not gateway_platforms:
                raise ConfigError(
                    "harness server 仅支持已启用的 feishu / weixin gateway。"
                    " 请运行 'harness setup' 选择 messaging gateway 并勾选至少一个平台。"
                )

            gateway_labels: list[str] = []
            bots: dict[str, object] = {}
            channel_factories: dict[str, Callable[[str], object]] = {}
            for platform in gateway_platforms:
                gateway_label, bot, channel_factory = _build_gateway(
                    platform=platform,
                    session_manager=session_manager,
                )
                gateway_labels.append(gateway_label)
                bots[platform] = bot
                channel_factories[platform] = channel_factory

            def _channel_factory(chat_id: str) -> object:
                platform, raw_chat_id = _decode_gateway_chat_id(chat_id)
                factory = channel_factories.get(platform)
                if factory is None:
                    raise ConfigError(f"Unsupported gateway platform: {platform!r}")
                return factory(raw_chat_id)

            session_manager._frontend = MultiGatewayFrontend(bots)
            session_manager._channel_factory = _channel_factory
            session_manager._hitl_mode = "gateway"

            # 6.5. Initialize task scheduler if enabled
            if cron_config.enabled:
                logger.info("Initializing task scheduler...")
                task_scheduler = TaskScheduler(
                    session_manager=session_manager,
                    storage_path=cron_config.storage_path,
                )
                await task_scheduler.initialize()
                # Set global scheduler for agent_cron MCP server
                set_task_scheduler(task_scheduler)
                logger.info("Task scheduler initialized")
            else:
                task_scheduler = None
                logger.info("Task scheduler disabled")

            main_loop = asyncio.get_running_loop()
            for bot in bots.values():
                bot.set_main_loop(main_loop)
                bot.start()

            logger.info(
                "AG2 OpenHarness Gateways started: %s. "
                "Active MCP servers: %s",
                ", ".join(gateway_labels),
                connected_servers,
            )

            # 7. Run until stop or restart requested
            try:
                stop_event = asyncio.Event()
                loop = asyncio.get_running_loop()

                def _signal_handler() -> None:
                    logger.info("Shutdown signal received")
                    stop_event.set()

                try:
                    for sig in (signal.SIGINT, signal.SIGTERM):
                        loop.add_signal_handler(sig, _signal_handler)
                except (NotImplementedError, AttributeError, OSError):
                    pass

                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(stop_event.wait()),
                        asyncio.create_task(restart_event.wait()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt received")

            # Shutdown phase
            session_manager.terminate_all()
            for bot in bots.values():
                bot.stop()

            # Shutdown task scheduler if enabled
            if task_scheduler:
                await task_scheduler.shutdown()

        # After async with exits, MCP is automatically disconnected

        if restart_event.is_set():
            logger.info("Restarting service...")
            continue
        else:
            logger.info("Shutdown complete.")
            break


if __name__ == "__main__":
    asyncio.run(main())
