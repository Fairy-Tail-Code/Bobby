"""Email channel adapter — wraps SMTP send + IMAP poll into ChannelAdapter."""
from __future__ import annotations

import email as email_lib
import imaplib
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from infrastructure.channel.channel import ChannelAdapter
from config.config import SmtpConfig, ImapConfig

logger = logging.getLogger(__name__)


class EmailChannel(ChannelAdapter):
    """Send via SMTP, poll for replies via IMAP.

    Reply matching relies on the *request_id* embedded in the email subject
    (the same approach used by the original ``EmailUserProxyAgent``).
    """

    def __init__(self, smtp: SmtpConfig, imap: ImapConfig) -> None:
        self._smtp = smtp
        self._imap = imap
        self._seen_uids: set[str] = set()

    # ------------------------------------------------------------------ send
    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        full_subject = f"[OpenHarness] [{request_id}] {subject}"
        msg = MIMEMultipart()
        msg["From"] = self._smtp.user
        msg["To"] = recipient
        msg["Subject"] = full_subject
        msg["X-Harness-RequestId"] = request_id
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

        logger.debug("Email sent to %s, subject=%r", recipient, full_subject)

    # --------------------------------------------------------------- poll
    async def poll_reply(self, request_id: str) -> str | None:
        try:
            if self._imap.use_ssl:
                conn = imaplib.IMAP4_SSL(self._imap.host, self._imap.port)
            else:
                conn = imaplib.IMAP4(self._imap.host, self._imap.port)

            with conn:
                conn.login(self._imap.user, self._imap.password)
                conn.select("INBOX")

                _, raw_uids = conn.uid("search", None, "UNSEEN")
                if not raw_uids[0]:
                    return None

                for uid in reversed(raw_uids[0].split()):
                    uid_str = uid.decode()
                    if uid_str in self._seen_uids:
                        continue

                    # lightweight: fetch Subject header only
                    _, header_data = conn.uid("fetch", uid, "(BODY[HEADER.FIELDS (SUBJECT)])")
                    if not header_data or not header_data[0]:
                        continue

                    raw = header_data[0]
                    header_bytes = raw[1] if isinstance(raw, tuple) else raw
                    if isinstance(header_bytes, bytes):
                        decoded = email_lib.header.decode_header(
                            header_bytes.decode("utf-8", errors="replace")
                        )
                        subject = ""
                        for part, enc in decoded:
                            if isinstance(part, bytes):
                                subject += part.decode(enc or "utf-8", errors="replace")
                            else:
                                subject += part
                    else:
                        subject = str(header_bytes)

                    if request_id not in subject:
                        continue

                    # match found — fetch full body
                    _, msg_data = conn.uid("fetch", uid, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue

                    reply_msg = email_lib.message_from_bytes(msg_data[0][1])
                    text = self._extract_text(reply_msg)
                    if text:
                        self._seen_uids.add(uid_str)
                        return text

        except Exception:
            logger.exception("IMAP poll failed")

        return None

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _extract_text(msg: email_lib.message.Message) -> str | None:
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
