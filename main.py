"""AG2 OpenHarness - Multi-agent full-stack application generation harness."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from infrastructure.config import (
    load_llm_config, load_mcp_config, load_harness_config,
    load_smtp_config, load_imap_config, load_role_emails,
    load_dingtalk_config, load_role_dingtalk_ids,
    load_feishu_config, load_role_feishu_open_ids,
    load_knowledge_config,
)
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry
from agents.factory import create_all_agents, SKILLS_DIR
from orchestration.group import arun_swarm
from utils.yaml_reader import read_yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent
CONFIG_DIR = PROJECT_DIR / "config"

# 获取session_file
config = read_yaml("config/harness.yaml")
session_dir = config.get("harness", {}).get("session", {}).get("session_dir", "session")
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
session_file = os.path.join(session_dir, f"chat_history_{timestamp}.json")


async def run(prompt: str) -> None:
    """运行测试工具，传入用户提示词启动完整流程"""
    # 加载配置：从环境变量加载大模型配置
    logger.info("Loading LLM config from .env")
    llm_config = load_llm_config(PROJECT_DIR)

    # 加载 MCP 服务配置和测试工具配置
    logger.info("Loading MCP and harness config from %s", CONFIG_DIR)
    mcp_config = load_mcp_config(CONFIG_DIR)
    harness_config = load_harness_config(CONFIG_DIR)

    # 初始化技能注册器，扫描技能目录
    skill_registry = SkillRegistry(roots=[SKILLS_DIR])
    available_skills = skill_registry.list_skills()
    logger.info("Available skills: %s", [s.name for s in available_skills])

    # 连接所有配置的 MCP 服务器（用于工具调用/外部服务）
    logger.info("Connecting to MCP servers...")
    mcp_manager = McpManager(mcp_config)
    connected_servers: list[str] = []
    for server_cfg in mcp_config.servers:
        try:
            await mcp_manager.connect(server_cfg)
            connected_servers.append(server_cfg.name)
        except Exception as e:
            logger.error("Failed to connect to MCP server '%s': %s", server_cfg.name, e)

    # 校验技能与 MCP 服务的匹配性：技能需要的服务是否已连接
    skill_registry.connected_servers = connected_servers
    alignment_issues = skill_registry.validate_alignment()
    if alignment_issues:
        for issue in alignment_issues:
            logger.warning(
                "Skill '%s' needs MCP servers %s but %s not connected",
                issue.skill_name, issue.missing_servers, issue.missing_servers,
            )

    try:
        # 根据HITL模式加载对应通道配置
        smtp_config = None
        imap_config = None
        role_emails = None
        dingtalk_config = None
        role_dingtalk_ids = None
        feishu_config = None
        role_feishu_open_ids = None

        if harness_config.hitl.mode == "email":
            smtp_config = load_smtp_config(PROJECT_DIR)
            imap_config = load_imap_config(PROJECT_DIR)
            role_emails = load_role_emails(PROJECT_DIR)
            logger.info("HITL mode: email (SMTP=%s)", smtp_config.host)
        elif harness_config.hitl.mode == "dingtalk":
            dingtalk_config = load_dingtalk_config(PROJECT_DIR)
            role_dingtalk_ids = load_role_dingtalk_ids(PROJECT_DIR)
            logger.info("HITL mode: dingtalk (client_id=%s)", dingtalk_config.client_id[:6] + "..." if dingtalk_config.client_id else "N/A")
        elif harness_config.hitl.mode == "feishu":
            feishu_config = load_feishu_config(PROJECT_DIR)
            role_feishu_open_ids = load_role_feishu_open_ids(PROJECT_DIR)
            logger.info("HITL mode: feishu (app_id=%s)", feishu_config.app_id[:6] + "..." if feishu_config.app_id else "N/A")

        # 创建所有智能体：包含技能、转接逻辑、人工代理（如需）
        logger.info("Creating agents (mode=%s)...", harness_config.mode)

        agents_dict = create_all_agents(
            llm_config, mcp_manager, skill_registry, harness_config,
            smtp_config=smtp_config,
            imap_config=imap_config,
            role_emails=role_emails,
            dingtalk_config=dingtalk_config,
            role_dingtalk_ids=role_dingtalk_ids,
            feishu_config=feishu_config,
            role_feishu_open_ids=role_feishu_open_ids,
        )

        # 构建智能体列表
        if harness_config.mode == "single":
            agents_list = [agents_dict["assistant"]]
            for key in ("user", "assistant_owner"):
                if key in agents_dict:
                    agents_list.append(agents_dict[key])
        else:
            agents_list = [
                agents_dict["planner"],
                agents_dict["generator"],
                agents_dict["evaluator"],
                agents_dict["pm"],
            ]
            for key in ("user", "pm_owner", "planner_owner", "generator_owner", "evaluator_owner"):
                if key in agents_dict:
                    agents_list.append(agents_dict[key])

        # 启动多智能体群聊（Swarm），设置初始发言智能体、最大轮数等
        logger.info(
            "Starting swarm chat (max %d rounds) with prompt: %s",
            harness_config.max_rounds,
            prompt[:100],  # 只打印前100字符避免日志过长
        )
        # arun_swarm开始循环
        initial_agent = agents_dict.get("assistant") or agents_dict["pm"]
        chat_result, context, last_speaker,manager = await arun_swarm(
            initial_agent=initial_agent,
            agents=agents_list,  # 参与群聊的所有智能体
            prompt=prompt,  # 用户输入提示词
            harness_config=harness_config,  # 配置

        )

        # 保存session
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(chat_result.chat_history, f, ensure_ascii=False, indent=2)

        logger.info("Session saved.")

        # 群聊执行完成，输出最后发言智能体

        # todo 加入session resume功能
        logger.info("Swarm completed. Last speaker: %s", last_speaker.name)

        # === 知识收集与同步 ===
        knowledge_config = harness_config.knowledge
        if knowledge_config and knowledge_config.enabled:
            try:
                from infrastructure.knowledge.collector import ExperienceCollector
                from infrastructure.knowledge.local_store import LocalKnowledgeStore
                from infrastructure.knowledge.sync_client import KnowledgeSyncClient
                from infrastructure.knowledge.formatter import write_pulled_experiences

                collector = ExperienceCollector(llm_config.generator, knowledge_config)
                experiences = await collector.collect_from_session(
                    chat_history=chat_result.chat_history,
                    session_metadata={
                        "prompt": prompt,
                        "mode": harness_config.mode,
                        "session_id": timestamp,
                        "project_type": "+".join(harness_config.tech_stack.values()) if harness_config.tech_stack else None,
                    },
                )

                if experiences:
                    local_store = LocalKnowledgeStore(knowledge_config.local_store_path)
                    await local_store.connect()
                    try:
                        enqueued = await local_store.enqueue(experiences)
                        logger.info("Enqueued %d experiences for sync", enqueued)

                        # Try immediate sync
                        sync_client = KnowledgeSyncClient(knowledge_config)
                        if await sync_client.health_check():
                            result = await sync_client.sync_with_server(local_store)
                            logger.info("Sync result: pushed=%d, pulled=%d, errors=%d",
                                        result["pushed"], result["pulled"], result["errors"])

                            # Integrate pulled experiences
                            if knowledge_config.pull_enabled and result["pulled"] > 0:
                                pull_resp = await sync_client.pull()
                                if pull_resp and pull_resp.get("experiences"):
                                    written = write_pulled_experiences(
                                        pull_resp["experiences"],
                                        knowledge_config.collected_dir + "/shared",
                                    )
                                    logger.info("Wrote %d shared experiences to local memory", written)
                        else:
                            logger.info("Knowledge server unreachable; %d experiences queued locally", enqueued)
                    finally:
                        await local_store.close()
            except Exception:
                logger.exception("Knowledge collection/sync failed, continuing...")
    finally:
        # 无论是否异常，最终都断开 MCP 服务，释放资源
        logger.info("Disconnecting MCP servers...")
        await mcp_manager.disconnect_all()


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
    knowledge_config = load_knowledge_config(PROJECT_DIR)
    if not knowledge_config.enabled:
        print("Knowledge sharing is not enabled. Set knowledge.enabled=true in config/harness.yaml")
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
