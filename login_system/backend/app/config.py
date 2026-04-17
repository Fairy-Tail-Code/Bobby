"""
Celery + Redis 学习型登录系统 - 后端配置
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "sqlite:///./login_system.db"

    # JWT
    JWT_SECRET_KEY: str = "celery-login-system-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # 邮箱验证 Token
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    RESET_TOKEN_EXPIRE_HOURS: int = 1

    # Celery / Redis
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # SMTP 邮件
    SMTP_HOST: str = "smtp.qq.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    # 前端地址（用于邮件中的链接）
    FRONTEND_URL: str = "http://localhost:5173"

    # 重新发送验证邮件冷却时间（秒）
    RESEND_COOLDOWN_SECONDS: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
