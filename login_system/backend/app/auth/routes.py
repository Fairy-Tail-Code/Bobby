"""
认证 API 路由
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt_utils import create_access_token, get_current_user
from app.auth.password import hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.models import User, VerificationToken
from app.schemas import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ResendVerificationRequest,
    TokenResponse,
    UserResponse,
    MessageResponse,
)
from app.tasks.email_tasks import send_verification_email, send_reset_password_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    # 验证密码一致
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )

    # 检查邮箱是否已注册
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # 创建用户
    user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 创建验证 Token
    token = str(uuid.uuid4())
    verification_token = VerificationToken(
        user_id=user.id,
        token=token,
        token_type="email_verification",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS),
    )
    db.add(verification_token)
    db.commit()

    # 🎯 核心：通过 Celery 异步发送验证邮件（不阻塞响应）
    send_verification_email.delay(user.email, token)

    return MessageResponse(
        message="Registration successful! Please check your email to verify your account.",
        success=True,
    )


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    # 签发 JWT
    access_token = create_access_token(data={"sub": user.id, "email": user.email})

    return TokenResponse(
        access_token=access_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            is_verified=user.is_verified,
            created_at=user.created_at,
        ),
    )


@router.get("/verify-email", response_model=MessageResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    """邮箱验证"""
    verification_token = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.token == token,
            VerificationToken.token_type == "email_verification",
            VerificationToken.is_used == False,
        )
        .first()
    )

    if not verification_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    # 检查是否过期
    if verification_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired. Please request a new one.",
        )

    # 标记 Token 已使用
    verification_token.is_used = True

    # 标记用户已验证
    user = db.query(User).filter(User.id == verification_token.user_id).first()
    if user:
        user.is_verified = True
        user.updated_at = datetime.now(timezone.utc)

    db.commit()

    return MessageResponse(
        message="Email verified successfully! You can now log in.",
        success=True,
    )


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """请求密码重置"""
    user = db.query(User).filter(User.email == request.email).first()

    # 即使邮箱不存在也返回成功，防止用户枚举攻击
    if not user:
        return MessageResponse(
            message="If your email is registered, you will receive a password reset email.",
            success=True,
        )

    # 使之前的重置 Token 失效
    existing_tokens = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.user_id == user.id,
            VerificationToken.token_type == "password_reset",
            VerificationToken.is_used == False,
        )
        .all()
    )
    for t in existing_tokens:
        t.is_used = True

    # 创建新的重置 Token
    token = str(uuid.uuid4())
    reset_token = VerificationToken(
        user_id=user.id,
        token=token,
        token_type="password_reset",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.RESET_TOKEN_EXPIRE_HOURS),
    )
    db.add(reset_token)
    db.commit()

    # 🎯 核心：通过 Celery 异步发送密码重置邮件
    send_reset_password_email.delay(user.email, token)

    return MessageResponse(
        message="If your email is registered, you will receive a password reset email.",
        success=True,
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """执行密码重置"""
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )

    reset_token = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.token == request.token,
            VerificationToken.token_type == "password_reset",
            VerificationToken.is_used == False,
        )
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    if reset_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one.",
        )

    # 更新密码
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if user:
        user.hashed_password = hash_password(request.new_password)
        user.updated_at = datetime.now(timezone.utc)

    reset_token.is_used = True
    db.commit()

    return MessageResponse(
        message="Password reset successfully! You can now log in with your new password.",
        success=True,
    )


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(request: ResendVerificationRequest, db: Session = Depends(get_db)):
    """重新发送验证邮件"""
    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        return MessageResponse(
            message="If your email is registered and not verified, a new verification email will be sent.",
            success=True,
        )

    if user.is_verified:
        return MessageResponse(
            message="Your email is already verified. You can log in.",
            success=True,
        )

    # 检查冷却时间
    latest_token = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.user_id == user.id,
            VerificationToken.token_type == "email_verification",
        )
        .order_by(VerificationToken.created_at.desc())
        .first()
    )

    if latest_token:
        elapsed = (datetime.now(timezone.utc) - latest_token.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < settings.RESEND_COOLDOWN_SECONDS:
            remaining = int(settings.RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting another verification email.",
            )

    # 创建新的验证 Token
    token = str(uuid.uuid4())
    verification_token = VerificationToken(
        user_id=user.id,
        token=token,
        token_type="email_verification",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS),
    )
    db.add(verification_token)
    db.commit()

    # 🎯 Celery 异步发送
    send_verification_email.delay(user.email, token)

    return MessageResponse(
        message="A new verification email has been sent. Please check your inbox.",
        success=True,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户信息"""
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse(
        id=user.id,
        email=user.email,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )
