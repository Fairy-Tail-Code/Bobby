"""
邮件服务 - 使用 SMTP 发送邮件
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.config import settings


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    发送 HTML 邮件
    返回是否发送成功
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        # 如果没有配置 SMTP，打印日志模拟发送
        print(f"[EMAIL MOCK] To: {to_email}, Subject: {subject}")
        print(f"[EMAIL MOCK] Body length: {len(html_body)} chars")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER
        msg["To"] = to_email

        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        if settings.SMTP_USE_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USER, to_email, msg.as_string())
        server.quit()
        return True

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email to {to_email}: {e}")
        return False


def build_verification_email_html(verification_url: str) -> str:
    """构建邮箱验证邮件的 HTML 内容"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 40px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <h2 style="color: #2563eb; margin-top: 0;">欢迎注册！📧</h2>
            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                感谢您的注册！请点击下方按钮验证您的邮箱地址：
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{verification_url}" style="background-color: #2563eb; color: #ffffff; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-size: 16px; display: inline-block;">
                    验证邮箱
                </a>
            </div>
            <p style="color: #6b7280; font-size: 14px;">
                如果按钮无法点击，请复制以下链接到浏览器打开：
            </p>
            <p style="color: #2563eb; font-size: 14px; word-break: break-all;">
                {verification_url}
            </p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
            <p style="color: #9ca3af; font-size: 12px;">
                此链接 24 小时内有效。如果这不是您的操作，请忽略此邮件。
            </p>
        </div>
    </body>
    </html>
    """


def build_reset_password_email_html(reset_url: str) -> str:
    """构建密码重置邮件的 HTML 内容"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 40px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <h2 style="color: #2563eb; margin-top: 0;">重置密码 🔐</h2>
            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                我们收到了您的密码重置请求。请点击下方按钮设置新密码：
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background-color: #2563eb; color: #ffffff; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-size: 16px; display: inline-block;">
                    重置密码
                </a>
            </div>
            <p style="color: #6b7280; font-size: 14px;">
                如果按钮无法点击，请复制以下链接到浏览器打开：
            </p>
            <p style="color: #2563eb; font-size: 14px; word-break: break-all;">
                {reset_url}
            </p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
            <p style="color: #9ca3af; font-size: 12px;">
                此链接 1 小时内有效。如果这不是您的操作，请忽略此邮件，您的密码不会改变。
            </p>
        </div>
    </body>
    </html>
    """
