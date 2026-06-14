from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: str  # UUID
    email: str
    name: Optional[str] = None
    role: str = "user"  # user/admin
    # True for freshly-provisioned accounts that must reset their temp password
    # before doing anything else (consumed by the first-login reset screen).
    must_change_password: bool = False
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    """Request body for local user registration."""

    email: EmailStr
    password: str = Field(min_length=8)
    name: Optional[str] = None


class LoginRequest(BaseModel):
    """Request body for local email/password login."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Response body for a successful login/registration."""

    token: str
    token_type: str = "Bearer"
    expires_at: int  # unix timestamp (seconds)
    refresh_token: Optional[str] = None
    user: UserResponse


class RefreshRequest(BaseModel):
    """Request body for exchanging a refresh token for a new access token."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Response body for a successful token refresh."""

    token: str
    token_type: str = "Bearer"
    expires_at: int


class ChangePasswordRequest(BaseModel):
    """Request body for changing the current user's password."""

    current_password: str
    new_password: str = Field(min_length=8)


class NotificationPrefs(BaseModel):
    """Per-user notification toggles. Defaults mirror the prior frontend defaults."""

    email_alerts: bool = True
    low_stock_alerts: bool = True
    daily_summary: bool = False
    transaction_alerts: bool = True


class UserPreferencesResponse(BaseModel):
    """Server-side per-user profile + notification preferences."""

    display_name: Optional[str] = None
    notification_prefs: NotificationPrefs = Field(default_factory=NotificationPrefs)


class UpdateUserPreferencesRequest(BaseModel):
    """Request body for persisting profile + notification preferences."""

    display_name: Optional[str] = None
    notification_prefs: Optional[NotificationPrefs] = None
