"""AG2 OpenHarness gateway service entry point.

Usage:
    python server.py
"""
from __future__ import annotations

import asyncio
import logging
import signal

from config.config import (
    load_llm_config, load_mcp_config, load_harness_config,
    load_feishu_config,
    load_weixin_config,
    ConfigError,
)
from gateway.feishu.feishu_bot import FeishuBotService
from gateway.feishu.channel_feishu_service import ChannelFeishuService
from gateway.weixin.weixin_bot import WeixinBotService
from gateway.weixin.channel_weixin_service import ChannelWeixinService
from infrastructure.mcp.manager import create_mcp_manager
from infrastructure.agent_pool import AgentPool
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


def _build_gateway(
    *,
    mode: str,
    session_manager: SessionManager,
) -> tuple[str, object, object]:
    if mode == "feishu":
        feishu_config = load_feishu_config()
        if not feishu_config.app_id or not feishu_config.app_secret:
            raise ConfigError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET，请重新运行 'harness setup' 完成飞书扫码配置。")
        bot = FeishuBotService(
            app_id=feishu_config.app_id,
            app_secret=feishu_config.app_secret,
            domain=feishu_config.domain,
            on_message=session_manager.handle_message,
        )
        channel_factory = lambda chat_id: ChannelFeishuService(bot, chat_id)
        return "Feishu", bot, channel_factory

    if mode == "weixin":
        weixin_config = load_weixin_config()
        if not weixin_config.account_id or not weixin_config.token:
            raise ConfigError("缺少 WEIXIN_ACCOUNT_ID / WEIXIN_TOKEN，请重新运行 'harness setup' 完成微信扫码配置。")
        bot = WeixinBotService(
            account_id=weixin_config.account_id,
            token=weixin_config.token,
            base_url=weixin_config.base_url,
            on_message=session_manager.handle_message,
        )
        channel_factory = lambda chat_id: ChannelWeixinService(bot, chat_id)
        return "Weixin", bot, channel_factory

    raise ConfigError(
        "harness server 仅支持 feishu 或 weixin 网关。"
        f" 当前 harness.hitl.mode={mode!r}，请先运行 'harness setup' 重新选择。"
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

            gateway_label, bot, channel_factory = _build_gateway(
                mode=harness_config.hitl.mode,
                session_manager=session_manager,
            )
            session_manager._frontend = bot
            session_manager._channel_factory = channel_factory
            session_manager._hitl_mode = harness_config.hitl.mode
            bot.set_main_loop(asyncio.get_running_loop())
            bot.start()

            logger.info(
                "AG2 OpenHarness %s Gateway started. "
                "Active MCP servers: %s",
                gateway_label,
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
            bot.stop()

        # After async with exits, MCP is automatically disconnected

        if restart_event.is_set():
            logger.info("Restarting service...")
            continue
        else:
            logger.info("Shutdown complete.")
            break


if __name__ == "__main__":
    asyncio.run(main())
