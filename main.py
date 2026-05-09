"""AG2 OpenHarness - Multi-agent full-stack application generation harness."""
from __future__ import annotations

import asyncio
import logging
import sys

from config.config import (
    load_llm_config,
    load_mcp_config,
    load_harness_config,
    load_knowledge_config,
)
from infrastructure.mcp.manager import create_mcp_manager
from utils.paths import (
    get_config_dir, get_session_dir, get_system_skills_dir, get_user_skills_dir,
)
from fronted.frontend_cli import CLIFrontend, print_info
from infrastructure.agent_pool import AgentPool
from infrastructure.channel.channel_cli import CLIChannel
from infrastructure.session.session_manager import SessionManager
from infrastructure.skills.registry import SkillRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run(prompt: str) -> None:
    """Run one CLI session using the current session manager/runtime stack."""
    llm_config = load_llm_config()
    mcp_config = load_mcp_config()
    harness_config = load_harness_config()

    skill_registry = SkillRegistry(roots=[get_system_skills_dir(), get_user_skills_dir()])
    available_skills = skill_registry.list_skills()
    logger.info("Available skills: %s", [s.name for s in available_skills])

    logger.info("Connecting to MCP servers...")
    async with create_mcp_manager(mcp_config) as mcp_manager:
        connected_servers = mcp_manager.list_servers()
        skill_registry.connected_servers = connected_servers
        alignment_issues = skill_registry.validate_alignment()
        if alignment_issues:
            for issue in alignment_issues:
                logger.warning(
                    "Skill '%s' needs MCP servers %s but %s not connected",
                    issue.skill_name, issue.missing_servers, issue.missing_servers,
                )

        agent_pool = AgentPool(
            llm_config=llm_config,
            mcp_manager=mcp_manager,
            skill_registry=skill_registry,
            harness_config=harness_config,
        )
        agent_pool.initialize()

        frontend = CLIFrontend()
        session_manager = SessionManager(
            frontend=frontend,
            mcp_manager=mcp_manager,
            llm_config=llm_config,
            harness_config=harness_config,
            skill_registry=skill_registry,
            session_dir=str(get_session_dir()),
            agent_pool=agent_pool,
            channel_factory=lambda chat_id: CLIChannel(),
        )

        chat_id = "cli"
        open_id = "user"
        chat_type = "p2p"

        print_info(f"OpenHarness run ready (mode={harness_config.mode}, MCP servers={connected_servers})")
        await session_manager.handle_message(chat_id, open_id, chat_type, prompt)

        session = session_manager._sessions.get(chat_id)
        if session and session.is_running:
            try:
                while session.is_running:
                    channel = getattr(session, "channel", None)
                    if channel is not None:
                        pending_id = channel.get_any_pending_request_id()
                        if pending_id is not None:
                            reply = input()
                            channel.inject_reply(pending_id, reply)
                            continue
                    await asyncio.sleep(0.3)
            except KeyboardInterrupt:
                session_manager.terminate_all()
                raise


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py \"Your application description\"")
        print("       python main.py knowledge sync")
        print("       python main.py knowledge search <query>")
        print("       python main.py knowledge status")
        print("Example: python main.py \"Build a task management app with dark theme\"")
        sys.exit(1)

    if sys.argv[1] == "knowledge":
        asyncio.run(_handle_knowledge_command(sys.argv[2:]))
        return

    prompt = " ".join(sys.argv[1:])
    asyncio.run(run(prompt))


async def _handle_knowledge_command(args: list[str]) -> None:
    """Handle knowledge subcommands: sync, search, status."""
    knowledge_config = load_knowledge_config()
    if not knowledge_config.enabled:
        print(
            "Knowledge sharing is not enabled. "
            f"Set knowledge.enabled=true in {get_config_dir() / 'harness.yaml'}"
        )
        sys.exit(1)

    if not args or args[0] == "status":
        await _knowledge_status(knowledge_config)
    elif args[0] == "sync":
        await _knowledge_sync(knowledge_config)
    elif args[0] == "search" and len(args) > 1:
        await _knowledge_search(knowledge_config, " ".join(args[1:]))
    else:
        print(f"Unknown knowledge command: {args[0] if args else 'none'}")
        print("Available: sync, search <query>, status")
        sys.exit(1)


async def _knowledge_status(config) -> None:
    from infrastructure.knowledge.local_store import LocalKnowledgeStore
    from infrastructure.knowledge.sync_client import KnowledgeSyncClient

    sync_client = KnowledgeSyncClient(config)
    server_ok = await sync_client.health_check()

    store = LocalKnowledgeStore(config.local_store_path)
    await store.connect()
    try:
        status = await store.get_status()
    finally:
        await store.close()

    print(f"Server: {'online' if server_ok else 'offline'} ({config.server_url})")
    print(f"Client ID: {config.client_id or 'not set'}")
    print(f"Queue status: {status or 'empty'}")


async def _knowledge_sync(config) -> None:
    from infrastructure.knowledge.local_store import LocalKnowledgeStore
    from infrastructure.knowledge.sync_client import KnowledgeSyncClient

    sync_client = KnowledgeSyncClient(config)
    if not await sync_client.health_check():
        print(f"Server unreachable at {config.server_url}")
        sys.exit(1)

    store = LocalKnowledgeStore(config.local_store_path)
    await store.connect()
    try:
        result = await sync_client.sync_with_server(store)
        print(f"Sync complete: pushed={result['pushed']}, pulled={result['pulled']}, errors={result['errors']}")
    finally:
        await store.close()


async def _knowledge_search(config, query: str) -> None:
    from infrastructure.knowledge.sync_client import KnowledgeSyncClient

    sync_client = KnowledgeSyncClient(config)
    result = await sync_client.search(query)
    if not result:
        print("No results or server unreachable")
        return

    experiences = result.get("results", [])
    total = result.get("total", 0)
    print(f"Found {total} results for '{query}':\n")
    for i, exp in enumerate(experiences, 1):
        print(f"  {i}. [{exp.get('category')}] {exp.get('title')}")
        tags = ", ".join(exp.get("tags", []))
        if tags:
            print(f"     Tags: {tags}")
        print()


if __name__ == "__main__":
    main()
