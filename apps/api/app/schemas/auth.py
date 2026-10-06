import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..models.user import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)


class LoginResponse(BaseModel):
    user: UserOut
    csrf_token: str


class CsrfResponse(BaseModel):
    token: str


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None