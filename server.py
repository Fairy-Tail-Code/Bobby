"""AG2 OpenHarness Feishu Service — FastAPI entry point.

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
)
from infrastructure.feishu_bot import FeishuBotService
from infrastructure.channel.channel_feishu_service import ChannelFeishuService
from infrastructure.mcp.manager import McpManager
from infrastructure.agent_pool import AgentPool
from infrastructure.paths import (
    get_session_dir, get_system_skills_dir, get_user_skills_dir,
)
from infrastructure.session_manager import SessionManager
from infrastructure.skills.registry import SkillRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
        feishu_config = load_feishu_config()

        # 2. Initialize skill registry
        system_skills_dir = get_system_skills_dir()
        user_skills_dir = get_user_skills_dir()
        skill_registry = SkillRegistry(roots=[system_skills_dir,user_skills_dir])
        logger.info("Available skills: %s", [s.name for s in skill_registry.list_skills()])

        # 3. Connect MCP servers
        logger.info("Connecting to MCP servers...")
        mcp_manager = McpManager(mcp_config)
        connected_servers: list[str] = []
        for server_cfg in mcp_config.servers:
            try:
                await mcp_manager.connect(server_cfg)
                connected_servers.append(server_cfg.name)
            except Exception as e:
                logger.error("Failed to connect MCP server '%s': %s", server_cfg.name, e)

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

        # 6. Create and start FeishuBotService
        bot = FeishuBotService(
            app_id=feishu_config.app_id,
            app_secret=feishu_config.app_secret,
            on_message=session_manager.handle_message,
        )
        session_manager._frontend = bot
        session_manager._channel_factory = lambda chat_id: ChannelFeishuService(bot, chat_id)
        session_manager._hitl_mode = "feishu"
        bot.set_main_loop(asyncio.get_running_loop())
        bot.start()

        logger.info(
            "AG2 OpenHarness Feishu Service started. "
            "Active MCP servers: %s",
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

            done, pending = await asyncio.wait( # 等待事件被set()
                [
                    asyncio.create_task(stop_event.wait()), # stop_event绑定了kill、ctrl+c等操作
                    asyncio.create_task(restart_event.wait()),# restart_event绑定了飞书的消息，当飞书发送harness restart时触发restart_event.set()
                ],
                return_when=asyncio.FIRST_COMPLETED,  # 只需要完成一个任务就返回，确保只能选择重启或者关闭
            )
            for t in pending:  # 清理另一个未完成的任务
                t.cancel()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
            session_manager.terminate_all()
            bot.stop()
            await mcp_manager.disconnect_all()
            logger.info("Shutdown complete.")
            break

        # Shutdown phase
        session_manager.terminate_all() # 确保所有资源被关闭
        bot.stop() # 确保所有资源被关闭
        await mcp_manager.disconnect_all()

        if restart_event.is_set(): #
            logger.info("Restarting service...")
            continue  # 如果该事件触发重新触发while True循环完成重启

        else:
            logger.info("Shutdown complete.")
            break


if __name__ == "__main__":
    asyncio.run(main())
