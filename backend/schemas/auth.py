from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: str  # UUID
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None  # self-editable contact phone (#203)
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


class PinLoginRequest(BaseModel):
    """Request body for on-terminal staff PIN login (#216).

    ``merchant_email`` scopes the PIN to a single merchant's staff (PINs are only
    unique within a merchant); ``pin`` is the staff member's numeric PIN.
    """

    merchant_email: EmailStr
    pin: str


class LoginResponse(BaseModel):
    """Response body for a successful login/registration."""

    token: str
    token_type: str = "Bearer"
    expires_at: int  # unix timestamp (seconds)
    refresh_token: Optional[str] = None
    user: UserResponse


class RefreshRequest(BaseModel):
    """Request body for exchanging a refresh token for a new access token.

    ``refresh_token`` is optional (FE-01): the SPA sends it via the HttpOnly
    refresh cookie instead of the body, so an empty body falls back to the
    cookie. The body path is kept for backward compatibility.
    """

    refresh_token: Optional[str] = None


class RefreshResponse(BaseModel):
    """Response body for a successful token refresh."""

    token: str
    token_type: str = "Bearer"
    expires_at: int


class ChangePasswordRequest(BaseModel):
    """Request body for changing the current user's password."""

    current_password: str
    new_password: str = Field(min_length=8)


class PasswordResetRequest(BaseModel):
    """Request body for ``/auth/password/forgot`` — the account email."""

    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    """Response for a reset request. Always 200 (anti-enumeration).

    ``reset_token`` is populated only in dev / no-SMTP mode so the flow is usable
    and testable without a real mailbox; it is ``None`` in production.
    """

    success: bool = True
    message: str = "If the account exists, a reset link has been sent."
    reset_token: Optional[str] = None


class PasswordResetConfirm(BaseModel):
    """Request body for ``/auth/password/reset`` — the token + the new password."""

    token: str
    new_password: str = Field(min_length=8)


class SessionInfo(BaseModel):
    """One active session (an issued refresh token) for the management UI (#83)."""

    id: str  # the session identifier (refresh-token jti) — pass to DELETE to revoke
    current: bool = False  # True for the session the calling access token belongs to
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class SessionListResponse(BaseModel):
    """The caller's active sessions."""

    sessions: list[SessionInfo]


class RevokeSessionsResponse(BaseModel):
    """Result of revoking sessions (single or all-but-current)."""

    success: bool = True
    revoked: int = 1


class NotificationPrefs(BaseModel):
    """Per-user notification toggles. Defaults mirror the prior frontend defaults.

    ``email_alerts`` / ``whatsapp_alerts`` / ``push_alerts`` are the per-channel
    master switches (M10 / parity #8); the others are per-category switches. New
    channels default off so an upgrade never starts messaging a user over a
    channel they never opted into.
    """

    email_alerts: bool = True
    whatsapp_alerts: bool = False
    push_alerts: bool = False
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


# ---- MFA (TOTP) — ISSUE-081 ----


class MfaEnrollResponse(BaseModel):
    """Enrollment secret to load into an authenticator app (not yet active)."""

    secret: str  # base32 shared secret
    otpauth_uri: str  # otpauth://totp/... for QR provisioning
    enabled: bool = False


class MfaCodeRequest(BaseModel):
    """A submitted TOTP (or recovery) code."""

    code: str


class MfaActivateResponse(BaseModel):
    """Returned once on activation — the user must save these backup codes."""

    enabled: bool = True
    recovery_codes: list[str]


class MfaStatusResponse(BaseModel):
    """Whether MFA is active for the caller, with remaining recovery-code count."""

    enabled: bool
    recovery_codes_remaining: int = 0


class MfaChallengeResponse(BaseModel):
    """Returned by /auth/login when the account requires a second factor."""

    mfa_required: bool = True
    mfa_token: str  # short-lived ticket; exchange at /auth/login/mfa


class MfaLoginRequest(BaseModel):
    """Second-factor exchange: the login challenge ticket + a TOTP/recovery code."""

    mfa_token: str
    code: str
