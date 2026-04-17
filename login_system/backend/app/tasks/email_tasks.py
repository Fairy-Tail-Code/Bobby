"""
Celery 异步任务定义
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app
from app.config import settings
from app.services.email_service import (
    send_email,
    build_verification_email_html,
    build_reset_password_email_html,
)


@celery_app.task(bind=True, name="send_verification_email")
def send_verification_email(self, to_email: str, token: str):
    """
    异步发送邮箱验证邮件
    Celery task：不阻塞 HTTP 响应，由 Worker 异步执行
    """
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"

    self.update_state(
        state="PROGRESS",
        meta={"email": to_email, "step": "building_email"},
    )

    html_body = build_verification_email_html(verification_url)
    subject = "验证您的邮箱 - Celery Login System"

    self.update_state(
        state="PROGRESS",
        meta={"email": to_email, "step": "sending"},
    )

    success = send_email(to_email, subject, html_body)

    if success:
        return {"email": to_email, "status": "sent", "task_id": self.request.id}
    else:
        raise Exception(f"Failed to send verification email to {to_email}")


@celery_app.task(bind=True, name="send_reset_password_email")
def send_reset_password_email(self, to_email: str, token: str):
    """
    异步发送密码重置邮件
    Celery task：不阻塞 HTTP 响应，由 Worker 异步执行
    """
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    self.update_state(
        state="PROGRESS",
        meta={"email": to_email, "step": "building_email"},
    )

    html_body = build_reset_password_email_html(reset_url)
    subject = "重置您的密码 - Celery Login System"

    self.update_state(
        state="PROGRESS",
        meta={"email": to_email, "step": "sending"},
    )

    success = send_email(to_email, subject, html_body)

    if success:
        return {"email": to_email, "status": "sent", "task_id": self.request.id}
    else:
        raise Exception(f"Failed to send reset password email to {to_email}")
