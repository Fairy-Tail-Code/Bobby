"""AG2 OpenHarness Feishu Service — FastAPI entry point.

Usage:
    python server.py
"""
from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

import yaml

from config.config import (
    load_llm_config, load_mcp_config, load_harness_config,
    load_feishu_config,
)
from infrastructure.feishu_bot import FeishuBotService
from infrastructure.mcp.manager import McpManager
from infrastructure.session_manager import SessionManager
from infrastructure.skills.registry import SkillRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent
CONFIG_DIR = PROJECT_DIR / "config"


async def main() -> None:
    """Initialize all services and run forever. Supports in-process restart via restart_event."""
    restart_event = asyncio.Event()

    while True:
        restart_event.clear()

        # 1. Load configs
        logger.info("Loading configs...")
        llm_config = load_llm_config(PROJECT_DIR)
        mcp_config = load_mcp_config(CONFIG_DIR)
        harness_config = load_harness_config(CONFIG_DIR)
        feishu_config = load_feishu_config(PROJECT_DIR)

        # 2. Initialize skill registry
        system_skills_dir = PROJECT_DIR / "skills" / "system"
        user_skills_dir = PROJECT_DIR / "skills" / "user"
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

        skill_registry.connected_servers = connected_servers
        for issue in skill_registry.validate_alignment():
            logger.warning(
                "Skill '%s' needs MCP servers %s but %s not connected",
                issue.skill_name, issue.missing_servers, issue.missing_servers,
            )

        # 4. Get session dir from config
        config_path = CONFIG_DIR / "harness.yaml"
        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        session_dir = config_data.get("harness", {}).get("session", {}).get("session_dir", "session")

        # 5. Create SessionManager (bot set later)
        session_manager = SessionManager(
            bot=None,
            mcp_manager=mcp_manager,
            llm_config=llm_config,
            harness_config=harness_config,
            skill_registry=skill_registry,
            session_dir=session_dir,
            restart_event=restart_event,
        )

        # 6. Create and start FeishuBotService
        bot = FeishuBotService(
            app_id=feishu_config.app_id,
            app_secret=feishu_config.app_secret,
            on_message=session_manager.handle_message,
        )
        session_manager._bot = bot
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
