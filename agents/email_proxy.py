"""Email-based Human-in-the-Loop UserProxyAgent.

Replaces stdin with SMTP (send) + IMAP (receive) so that each role's human
operator can interact with agents via ordinary email replies.
"""
from __future__ import annotations

import asyncio
import email
import logging
import smtplib
import time
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re

from autogen import UserProxyAgent

from config.config import SmtpConfig, ImapConfig, HitlConfig

from autogen.io.base import AsyncInputStream

logger = logging.getLogger(__name__)


class EmailUserProxyAgent(UserProxyAgent):
    """A UserProxyAgent that sends questions via SMTP and polls IMAP for replies.

    Email threading relies on standard Message-ID / In-Reply-To headers.
    The human operator simply clicks "Reply" in their email client.
    """

    def __init__(
        self,
        name: str,
        smtp_config: SmtpConfig,
        imap_config: ImapConfig,
        recipient_email: str,
        role_description: str,
        hitl_config: HitlConfig | None = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            human_input_mode="ALWAYS",
            system_message=role_description,
            code_execution_config=False,
            llm_config=False,
            description=f"Human operator ({name}) reachable via {recipient_email}",
            **kwargs,
        )
        self._smtp = smtp_config
        self._imap = imap_config
        self._recipient = recipient_email
        hitl_config = hitl_config or HitlConfig()
        self._polling_interval = hitl_config.polling_interval
        self._timeout = hitl_config.timeout
        self._subject_prefix = hitl_config.subject_prefix
        self._seen_uids: set[str] = set()  # 已处理过的 IMAP UID，防止重复匹配


    # ------------------------------------------------------------------
    # AG2 hook — this is what the framework calls when it needs human input
    # ------------------------------------------------------------------


    # AG2 Group Chat 轮到 UserProxyAgent 发言时：
    #
    # 1. AG2 把上一位 agent 的消息作为 prompt 传入 a_get_human_input(prompt)
    #    ↓  这就是 "out" —— agent 要对人说的话
    #    ↓  我在方法里把它格式化成邮件，通过 SMTP 发给负责人
    #
    # 2. 然后轮询 IMAP 等负责人回复
    #    ↓  这就是 "in" —— 人的回复
    #
    # 3. return reply → AG2 把这个返回值作为 UserProxyAgent 的发言，继续群聊
    async def a_get_human_input(self, prompt: str, *, iostream: AsyncInputStream | None = None) -> str:
        """Send the prompt to the human via email, then poll for a reply."""
        # prompt 是 AG2 自动生成的 stdin 提示词（如 "Replying as planner_owner..."）
        # 真正的对话内容需要从 agent 消息历史中提取
        context = self._get_last_agent_message()

        # 生成唯一请求 ID，放入邮件主题用于匹配回复
        request_id = f"harness_{uuid.uuid4().hex[:8]}"

        subject = f"{self._subject_prefix} [{request_id}] {self.name} needs your input"
        body = self._format_email_body(context)

        self._send_email(subject, body)
        logger.info("Email sent to %s (%s), request_id=%s, waiting for reply...", self._recipient, self.name, request_id)

        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            reply = self._check_for_reply(request_id)
            if reply is not None:
                logger.info("Reply received from %s (%s)", self._recipient, self.name)
                logger.info(f"Get Reply ：{reply}")
                return reply
            await asyncio.sleep(self._polling_interval)

        logger.warning("Timeout waiting for reply from %s (%s)", self._recipient, self.name)
        return "[TIMEOUT] 未在规定时间内收到回复，请agent自行判断继续执行。"

    def _get_last_agent_message(self) -> str | None:
        """从GroupChat历史里找最后一条真正有意义的agent消息"""

        # 需要过滤掉的模式
        SKIP_PATTERNS = [
            r"^Transfer to \w+",
            r"^TERMINATE",
            r"^APPROVED",
            r"^REJECTED",
            r"^\s*$",  # 空消息
        ]

        if hasattr(self, "_groupchat") and self._groupchat:
            messages = self._groupchat.messages
        else:
            messages = []
            for msgs in self.chat_messages.values():
                messages.extend(msgs)

        for msg in reversed(messages):
            # 跳过自己发的
            if msg.get("name") == self.name:
                continue

            content = msg.get("content") or ""

            # 跳过None或空
            if not content.strip():
                continue

            # 跳过控制消息
            if any(re.search(p, content.strip(), re.IGNORECASE) for p in SKIP_PATTERNS):
                continue

            # 跳过纯工具调用结果（AG2里tool message）
            if msg.get("role") == "tool":
                continue

            sender = msg.get("name", "agent")
            return f"[{sender}]:\n{content}"

        return None
    # ------------------------------------------------------------------
    # Email formatting
    # ------------------------------------------------------------------

    def _format_email_body(self, prompt: str) -> str:
        return (
            f"A request from the {self.name} requires your input.\n\n"
            f"--- Request Details ---\n"
            f"{prompt}\n\n"
            f"--- Instructions ---\n"
            f"Please reply to this email directly. "
            f"Your reply body (plain text) will be forwarded to the agent as-is.\n"
        )

    # ------------------------------------------------------------------
    # SMTP send
    # ------------------------------------------------------------------

    def _send_email(self, subject: str, body: str) -> None:
        msg = MIMEMultipart()
        msg["From"] = self._smtp.user
        msg["To"] = self._recipient
        msg["Subject"] = subject
        msg["X-Harness-Role"] = self.name
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if self._smtp.use_tls:
            with smtplib.SMTP(self._smtp.host, self._smtp.port, timeout=30) as server:
                server.starttls()
                server.login(self._smtp.user, self._smtp.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self._smtp.host, self._smtp.port, timeout=30) as server:
                server.login(self._smtp.user, self._smtp.password)
                server.send_message(msg)

        logger.debug("Email sent: subject=%r", subject)

    # ------------------------------------------------------------------
    # IMAP poll
    # ------------------------------------------------------------------

    def _check_for_reply(self, request_id: str) -> str | None:
        """Check IMAP for an UNSEEN reply whose subject contains our request_id.

        不依赖 In-Reply-To（QQ 等邮箱 SMTP 会替换 Message-ID 导致失配），
        而是通过邮件主题中的唯一 request_id 来匹配。
        """
        import imaplib
        import email as email_lib

        try:
            if self._imap.use_ssl:
                imap_conn = imaplib.IMAP4_SSL(self._imap.host, self._imap.port)
            else:
                imap_conn = imaplib.IMAP4(self._imap.host, self._imap.port)

            with imap_conn:
                imap_conn.login(self._imap.user, self._imap.password)
                imap_conn.select("INBOX")

                # 只搜未读邮件
                _, raw_uids = imap_conn.uid("search", None, "UNSEEN")
                if not raw_uids[0]:
                    return None

                # 从最新开始遍历
                for uid in reversed(raw_uids[0].split()):
                    uid_str = uid.decode()

                    if uid_str in self._seen_uids:
                        continue

                    # 先取 Subject 头做轻量匹配
                    _, header_data = imap_conn.uid(
                        "fetch", uid, "(BODY[HEADER.FIELDS (SUBJECT)])"
                    )
                    if not header_data or not header_data[0]:
                        continue

                    # header_data[0] 可能是 tuple 或 bytes
                    raw = header_data[0]
                    header_bytes = raw[1] if isinstance(raw, tuple) else raw
                    if isinstance(header_bytes, bytes):
                        subject_text = email_lib.header.decode_header(
                            header_bytes.decode("utf-8", errors="replace")
                        )
                        subject = ""
                        for part, enc in subject_text:
                            if isinstance(part, bytes):
                                subject += part.decode(enc or "utf-8", errors="replace")
                            else:
                                subject += part
                    else:
                        subject = str(header_bytes)

                    logger.debug("UNSEEN UID=%s subject=%r", uid_str, subject)

                    # 检查主题是否包含我们的 request_id
                    if request_id not in subject:
                        continue

                    # 匹配成功，取完整邮件正文
                    _, msg_data = imap_conn.uid("fetch", uid, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue

                    reply_msg = email_lib.message_from_bytes(msg_data[0][1])
                    text = self._extract_text(reply_msg)

                    if text:
                        self._seen_uids.add(uid_str)
                        logger.info(
                            "Reply received (UID=%s) from %s (%s), request_id=%s",
                            uid_str, self._recipient, self.name, request_id,
                        )
                        return text

        except Exception:
            logger.exception("IMAP check failed for %s", self.name)

        return None

    @staticmethod
    def _extract_text(msg: email.message.Message) -> str | None:
        """Extract plain text content from an email message."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return None


# ------------------------------------------------------------------
# Factory helpers
# ------------------------------------------------------------------

_ROLE_DESCRIPTIONS = {
    "pm_owner": (
        "你是 PM 负责人，也就是用户本人。PM agent 会向你提问以补充和澄清需求细节，"
        "也会将 PRD 草稿发给你确认。请根据你的实际需求进行补充、修改或确认。"
    ),
    "planner_owner": (
        "你是 Planner 负责人。当 Planner agent 遇到需求不明确、信息不足时，"
        "会向你提问。请补充需求细节或澄清模糊之处。"
    ),
    "generator_owner": (
        "你是 Generator 负责人。当 Generator agent 准备执行风险操作"
        "（如删除数据库、强制推送、修改生产配置等）时，需要你的审批。"
        "回复 'approve' 表示批准，回复其他内容表示拒绝或提出修改意见。"
    ),
    "evaluator_owner": (
        "你是 Evaluator 负责人。当 Evaluator agent 在审核过程中需要确认"
        "某些决策或标准时，会向你咨询。请提供你的判断和意见。"
    ),
}


def create_email_proxies(
    smtp_config: SmtpConfig,
    imap_config: ImapConfig,
    hitl_config: HitlConfig,
    role_emails: dict[str, str],
) -> dict[str, EmailUserProxyAgent]:
    """Create email-based user proxies, one per role.

    Returns dict keyed by "pm_owner", "planner_owner", "generator_owner", "evaluator_owner".
    """
    proxies: dict[str, EmailUserProxyAgent] = {}
    for role_key, description in _ROLE_DESCRIPTIONS.items():
        short_role = role_key.replace("_owner", "")  # "planner", "generator", "evaluator"
        recipient = role_emails.get(short_role, "")
        if not recipient:
            logger.warning("No email configured for %s, skipping", role_key)
            continue
        proxies[role_key] = EmailUserProxyAgent(
            name=role_key,
            smtp_config=smtp_config,
            imap_config=imap_config,
            recipient_email=recipient,
            role_description=description,
            hitl_config=hitl_config,
        )
        logger.info("Created email proxy %s -> %s", role_key, recipient)
    return proxies
