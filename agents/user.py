"""Factory helpers for creating HITL user proxy agents."""
from __future__ import annotations

import logging

from autogen import ConversableAgent

from agents.channel_proxy import create_channel_proxies
from config.config import (
    DingTalkConfig,
    FeishuConfig,
    HitlConfig,
    ImapConfig,
    SmtpConfig,
)
from gateway.dingtalk.channel_dingtalk import DingTalkChannel
from gateway.email.channel_email import EmailChannel
from gateway.feishu.channel_feishu import FeishuChannel

logger = logging.getLogger(__name__)


def create_user() -> ConversableAgent:
    """Create a stdin-based UserProxyAgent (legacy / fallback mode)."""
    return ConversableAgent(
        name="user",
        human_input_mode="ALWAYS",
    )


def create_email_channel_proxies(
    smtp_config: SmtpConfig,
    imap_config: ImapConfig,
    hitl_config: HitlConfig,
    role_emails: dict[str, str],
) -> dict[str, ConversableAgent]:
    """Create email-based user proxies via the channel abstraction."""
    channel = EmailChannel(smtp_config, imap_config)
    return create_channel_proxies(
        channel,
        role_emails,
        timeout=hitl_config.timeout,
        polling_interval=hitl_config.polling_interval,
    )


def create_dingtalk_channel_proxies(
    dingtalk_config: DingTalkConfig,
    hitl_config: HitlConfig,
    role_user_ids: dict[str, str],
) -> dict[str, ConversableAgent]:
    """Create DingTalk-based user proxies."""
    channel = DingTalkChannel(
        client_id=dingtalk_config.client_id,
        client_secret=dingtalk_config.client_secret,
        robot_code=dingtalk_config.robot_code,
    )
    return create_channel_proxies(
        channel,
        role_user_ids,
        timeout=hitl_config.timeout,
        polling_interval=hitl_config.polling_interval,
    )


def create_feishu_channel_proxies(
    feishu_config: FeishuConfig,
    hitl_config: HitlConfig,
    role_open_ids: dict[str, str],
) -> dict[str, ConversableAgent]:
    """Create Feishu-based user proxies."""
    channel = FeishuChannel(
        app_id=feishu_config.app_id,
        app_secret=feishu_config.app_secret,
    )
    return create_channel_proxies(
        channel,
        role_open_ids,
        timeout=hitl_config.timeout,
        polling_interval=hitl_config.polling_interval,
    )
