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
    mcp_manager = McpManager()
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
    finally:
        # 无论是否异常，最终都断开 MCP 服务，释放资源
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
