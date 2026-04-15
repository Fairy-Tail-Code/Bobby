from __future__ import annotations

from autogen import ConversableAgent, UserProxyAgent

from agents.email_proxy import create_email_proxies
from infrastructure.config import LlmConfig, SmtpConfig, ImapConfig, HitlConfig


def create_user(llm_config: LlmConfig) -> ConversableAgent:
    """Create a stdin-based UserProxyAgent (legacy / fallback mode)."""
    return UserProxyAgent(
        name="user",
        code_execution_config={
            "work_dir": r"C:\Users\WUJIEAI\PycharmProjects\OpenHarness\ag2_coding",
            "use_docker": False,
        },
    )


def create_email_user_proxies(
    smtp_config: SmtpConfig,
    imap_config: ImapConfig,
    hitl_config: HitlConfig,
    role_emails: dict[str, str],
) -> dict[str, ConversableAgent]:
    """Create 3 email-based user proxies for multi-role HITL.

    Returns a dict of {role_key: EmailUserProxyAgent}.
    """
    return create_email_proxies(smtp_config, imap_config, hitl_config, role_emails)
