"""AG2 OpenHarness - Multi-agent full-stack application generation harness."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from infrastructure.config import load_llm_config, load_mcp_config, load_harness_config, load_smtp_config, load_imap_config, load_role_emails
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry
from agents.factory import create_all_agents, SKILLS_DIR
from orchestration.group import arun_swarm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent
CONFIG_DIR = PROJECT_DIR / "config"


async def run(prompt: str) -> None:
    """Run the harness with the given user prompt."""
    # Load configuration
    logger.info("Loading LLM config from .env")
    llm_config = load_llm_config(PROJECT_DIR)
    logger.info("Loading MCP and harness config from %s", CONFIG_DIR)
    mcp_config = load_mcp_config(CONFIG_DIR)
    harness_config = load_harness_config(CONFIG_DIR)

    # Initialize skill registry
    skill_registry = SkillRegistry(roots=[SKILLS_DIR])
    available_skills = skill_registry.list_skills()
    logger.info("Available skills: %s", [s.name for s in available_skills])

    # Connect to MCP servers
    logger.info("Connecting to MCP servers...")
    mcp_manager = McpManager()
    connected_servers: list[str] = []
    for server_cfg in mcp_config.servers:
        try:
            await mcp_manager.connect(server_cfg)
            connected_servers.append(server_cfg.name)
        except Exception as e:
            logger.error("Failed to connect to MCP server '%s': %s", server_cfg.name, e)

    # Validate skill-MCP alignment
    skill_registry.connected_servers = connected_servers
    alignment_issues = skill_registry.validate_alignment()
    if alignment_issues:
        for issue in alignment_issues:
            logger.warning(
                "Skill '%s' needs MCP servers %s but %s not connected",
                issue.skill_name, issue.missing_servers, issue.missing_servers,
            )

    try:
        # Load HITL email config (if email mode)
        smtp_config = None
        imap_config = None
        role_emails = None
        if harness_config.hitl.mode == "email":
            smtp_config = load_smtp_config(PROJECT_DIR)
            imap_config = load_imap_config(PROJECT_DIR)
            role_emails = load_role_emails(PROJECT_DIR)
            logger.info("HITL mode: email (SMTP=%s)", smtp_config.host)

        # Create agents with skills and handoffs
        logger.info("Creating agents with skills and swarm handoffs...")
        agents_dict = create_all_agents(
            llm_config, mcp_manager, skill_registry, harness_config,
            smtp_config=smtp_config,
            imap_config=imap_config,
            role_emails=role_emails,
        )

        # Build agent list: AI agents + whichever human proxies exist
        agents_list = [
            agents_dict["planner"],
            agents_dict["generator"],
            agents_dict["evaluator"],
        ]
        for key in ("user", "planner_owner", "generator_owner", "evaluator_owner"):
            if key in agents_dict:
                agents_list.append(agents_dict[key])

        # Run swarm chat
        logger.info(
            "Starting swarm chat (max %d rounds) with prompt: %s",
            harness_config.max_rounds,
            prompt[:100],
        )
        chat_result, context, last_speaker = await arun_swarm(
            initial_agent=agents_dict["planner"],
            agents=agents_list,
            prompt=prompt,
            harness_config=harness_config,
        )
        logger.info("Swarm completed. Last speaker: %s", last_speaker.name)
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
