"""
Pydantic Schemas - 请求和响应模型
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ============ 请求模型 ============

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


# ============ 响应模型 ============

class UserResponse(BaseModel):
    id: str
    email: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # PENDING, STARTED, SUCCESS, FAILURE
    result: Optional[str] = None
    date_done: Optional[str] = None
