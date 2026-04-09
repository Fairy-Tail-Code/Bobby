"""AG2 OpenHarness - Multi-agent full-stack application generation harness."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from infrastructure.config import load_llm_config, load_mcp_config, load_harness_config
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.loader import SkillLoader
from agents.factory import create_all_agents, SKILLS_DIR
from orchestration.group import create_group_chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / "config"


async def run(prompt: str) -> None:
    """Run the harness with the given user prompt."""
    # Load configuration
    logger.info("Loading configuration from %s", CONFIG_DIR)
    llm_config = load_llm_config(CONFIG_DIR)
    mcp_config = load_mcp_config(CONFIG_DIR)
    harness_config = load_harness_config(CONFIG_DIR)

    # Initialize skill loader
    skill_loader = SkillLoader(roots=[SKILLS_DIR])
    available_skills = skill_loader.list_skills()
    logger.info("Available skills: %s", available_skills)

    # Connect to MCP servers
    logger.info("Connecting to MCP servers...")
    mcp_manager = McpManager()
    for server_cfg in mcp_config.servers:
        try:
            await mcp_manager.connect(server_cfg)
        except Exception as e:
            logger.error("Failed to connect to MCP server '%s': %s", server_cfg.name, e)

    try:
        # Create agents with skills
        logger.info("Creating agents with skills...")
        agents_dict = create_all_agents(llm_config, mcp_manager, skill_loader)
        agents_list = [
            agents_dict["planner"],
            agents_dict["generator"],
            agents_dict["evaluator"],
        ]

        # Create group chat
        logger.info("Setting up group chat (max %d rounds)...", harness_config.max_rounds)
        manager = create_group_chat(agents_list, llm_config, harness_config)

        # Start the conversation
        logger.info("Starting conversation with prompt: %s", prompt[:100])
        agents_list[0].initiate_chat(
            manager,
            message=prompt,
        )
    finally:
        # Cleanup
        logger.info("Disconnecting MCP servers...")
        await mcp_manager.disconnect_all()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py \"Your application description\"")
        print("Example: python main.py \"Build a task management app with dark theme\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    asyncio.run(run(prompt))


if __name__ == "__main__":
    main()