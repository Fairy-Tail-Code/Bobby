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

from infrastructure.config import (
    load_llm_config, load_mcp_config, load_harness_config,
    load_feishu_config,
)
from infrastructure.feishu_bot import FeishuBotService, set_main_loop
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
    """Initialize all services and run forever."""
    # 1. Load configs
    logger.info("Loading configs...")
    llm_config = load_llm_config(PROJECT_DIR)
    mcp_config = load_mcp_config(CONFIG_DIR)
    harness_config = load_harness_config(CONFIG_DIR)
    feishu_config = load_feishu_config(PROJECT_DIR)

    # 2. Set main event loop reference for WS thread → main loop bridge
    set_main_loop(asyncio.get_running_loop())

    # 3. Initialize skill registry
    skills_dir = PROJECT_DIR / "skills"
    skill_registry = SkillRegistry(roots=[skills_dir])
    logger.info("Available skills: %s", [s.name for s in skill_registry.list_skills()])

    # 4. Connect MCP servers
    logger.info("Connecting to MCP servers...")
    mcp_manager = McpManager()
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

    # 5. Get session dir from config
    config_path = CONFIG_DIR / "harness.yaml"
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    session_dir = config_data.get("harness", {}).get("session", {}).get("session_dir", "session")

    # 6. Create SessionManager (bot set later)
    session_manager = SessionManager(
        bot=None,
        mcp_manager=mcp_manager,
        llm_config=llm_config,
        harness_config=harness_config,
        skill_registry=skill_registry,
        session_dir=session_dir,
    )

    # 7. Create and start FeishuBotService
    bot = FeishuBotService(
        app_id=feishu_config.app_id,
        app_secret=feishu_config.app_secret,
        on_message=session_manager.handle_message,
    )
    session_manager._bot = bot
    bot.start()

    logger.info(
        "AG2 OpenHarness Feishu Service started. "
        "Active MCP servers: %s",
        connected_servers,
    )

    # 8. Run forever until interrupted
    try:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _signal_handler():
            logger.info("Shutdown signal received")
            stop_event.set()

        # On Windows, add_signal_handler is not supported, so we fall back
        # to simply waiting on the stop event (Ctrl+C will raise KeyboardInterrupt).
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, AttributeError, OSError):
            # Windows or platform without add_signal_handler support
            pass

        await stop_event.wait()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
    finally:
        logger.info("Shutting down...")
        session_manager.terminate_all()
        await mcp_manager.disconnect_all()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
