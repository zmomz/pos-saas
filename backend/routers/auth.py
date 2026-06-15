import logging
import os
import uuid
from typing import Optional

from core.auth import AccessTokenError, create_mfa_token, decode_access_token
from core.config import settings
from core.database import get_db
from dependencies.auth import get_bearer_token, get_current_user
from services.mfa import MfaService
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel
from schemas.auth import (
    LoginRequest,
    LoginResponse,
    MfaActivateResponse,
    MfaChallengeResponse,
    MfaCodeRequest,
    MfaEnrollResponse,
    MfaLoginRequest,
    MfaStatusResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RevokeSessionsResponse,
    SessionInfo,
    SessionListResponse,
    UserResponse,
)
from services.auth import AuthService
from utils.password_policy import enforce_password_complexity
from services.password_reset import PasswordResetService
from services.login_throttle import (
    LoginLockedOut,
    assert_login_allowed,
    clear_login_attempts,
    register_failed_login,
)
from services.sessions import (
    list_active_sessions,
    record_session,
    revoke_other_sessions,
    revoke_session,
    touch_session,
)
from services.token_revocation import is_token_revoked, revoke_token
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


async def _issue_login_response(
    service: "AuthService", user, request: Optional[Request] = None
) -> LoginResponse:
    """Mint an access + refresh token pair and shape the standard login payload.

    Each pair is bound to a session (ISSUE-083): the refresh token's ``jti`` is
    recorded as a :class:`UserSession` so the user can list/revoke it, and the
    access token carries the same value as its ``sid`` claim so the session it
    belongs to can be flagged "current".
    """
    sid = uuid.uuid4().hex
    token, expires_at, _ = await service.issue_app_token(user, sid=sid)
    refresh_token = service.issue_refresh_token(user, jti=sid)

    refresh_exp = _refresh_token_exp(refresh_token)
    user_agent = request.headers.get("user-agent") if request else None
    ip_address = (request.client.host if request and request.client else None)
    await record_session(
        service.db,
        user_id=user.id,
        jti=sid,
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=refresh_exp,
    )

    return LoginResponse(
        token=token,
        expires_at=int(expires_at.timestamp()),
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


def _refresh_token_exp(refresh_token: str) -> Optional[int]:
    """Best-effort read of a refresh token's ``exp`` (seconds) for session metadata."""
    try:
        return decode_access_token(refresh_token).get("exp")
    except AccessTokenError:
        return None


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new local user and return an access token.

    Note: in this multi-tenant POS, self-registered users default to the
    "master" tenancy role. For provisioning agents/clients, use the tenant
    endpoints which create scoped accounts.
    """
    if not getattr(settings, "allow_registration", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled. Contact your administrator.",
        )

    enforce_password_complexity(payload.password)

    service = AuthService(db)
    try:
        user = await service.create_user(
            email=payload.email,
            password=payload.password,
            name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return await _issue_login_response(service, user, request)


@router.post("/login")
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password and return an access token.

    Repeated failed logins for the same (identifier, IP) are throttled to blunt
    credential-stuffing — see ``services.login_throttle`` for the policy.

    If the account has MFA enabled (ISSUE-081), a correct password yields a
    short-lived ``MfaChallengeResponse`` instead of tokens; the caller must
    exchange the ticket + a second-factor code at ``/auth/login/mfa``.
    """
    client_ip = request.client.host if request.client else "unknown"

    try:
        await assert_login_allowed(db, payload.email, client_ip)
    except LoginLockedOut as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    service = AuthService(db)
    user = await service.authenticate(payload.email, payload.password)
    if not user:
        await register_failed_login(db, payload.email, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    await clear_login_attempts(db, payload.email, client_ip)

    # Second-factor gate: an MFA-enabled account gets a challenge, not tokens.
    if await MfaService(db).is_enabled(user.id):
        ticket = create_mfa_token({"sub": user.id})
        return MfaChallengeResponse(mfa_required=True, mfa_token=ticket)

    return await _issue_login_response(service, user, request)


@router.post("/login/mfa", response_model=LoginResponse)
async def login_mfa(payload: MfaLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Complete an MFA login: exchange the challenge ticket + a code for tokens (#81).

    ``code`` may be a current TOTP code or a single-use recovery code.
    """
    try:
        claims = decode_access_token(payload.mfa_token)
    except AccessTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)

    if claims.get("type") != "mfa":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a valid second-factor ticket. Start at /auth/login.",
        )

    user_id = claims.get("sub")
    service = AuthService(db)
    user = await service.get_user_by_id(user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid second-factor ticket")

    if not await MfaService(db).verify_code(user.id, payload.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code",
        )

    return await _issue_login_response(service, user, request)


def _is_dev() -> bool:
    """Whether we're in a dev/CI environment (mirrors core/cors.py)."""
    return os.getenv("ENVIRONMENT", "prod").lower() == "dev"


@router.post("/password/forgot", response_model=PasswordResetRequestResponse)
async def forgot_password(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Request a password reset (ISSUE-082).

    Always responds 200 — whether or not the email matches an account — so the
    endpoint cannot be used to enumerate registered addresses. A matching
    account is emailed a single-use, time-limited reset token. In dev/no-SMTP
    mode the token is also returned in the response so the flow is testable.
    """
    token = await PasswordResetService(db).request_reset(payload.email)
    return PasswordResetRequestResponse(reset_token=token if _is_dev() else None)


@router.post("/password/reset")
async def reset_password(payload: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    """Complete a password reset with a token from ``/password/forgot`` (ISSUE-082).

    The token is single-use and time-limited; a used, expired, or unknown token
    is rejected with 400. On success the new password takes effect and the
    account's previously issued sessions are dropped (security-stamp bump).
    """
    # Enforce complexity before consuming the single-use token so a weak attempt
    # doesn't burn the reset grant.
    enforce_password_complexity(payload.new_password)

    ok = await PasswordResetService(db).reset(payload.token, payload.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Request a new one.",
        )
    return {"success": True, "message": "Password has been reset. Please sign in."}


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access token."""
    try:
        claims = decode_access_token(payload.refresh_token)
    except AccessTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)

    if claims.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provided token is not a refresh token",
        )

    if await is_token_revoked(db, claims.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This session has been logged out. Please sign in again.",
        )

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    service = AuthService(db)
    user = await service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    # Security stamp (ISSUE-082): a refresh token issued before a password reset
    # can no longer mint access tokens.
    if int(claims.get("sv", 0) or 0) != int(getattr(user, "token_version", 0) or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This session is no longer valid. Please sign in again.",
        )

    # Keep the new access token bound to the same session (#83) and record use.
    sid = claims.get("jti")
    await touch_session(db, sid)
    token, expires_at, _ = await service.issue_app_token(user, sid=sid)
    return RefreshResponse(token=token, expires_at=int(expires_at.timestamp()))


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    current_user: UserResponse = Depends(get_current_user),
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's active sessions (#83).

    Each session is an issued refresh token; the one the calling access token was
    minted from is flagged ``current`` (via its ``sid`` claim).
    """
    current_sid = None
    try:
        current_sid = decode_access_token(token).get("sid")
    except AccessTokenError:
        pass

    sessions = await list_active_sessions(db, current_user.id)
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=s.jti,
                current=(s.jti == current_sid),
                user_agent=s.user_agent,
                ip_address=s.ip_address,
                created_at=s.created_at,
                last_used_at=s.last_used_at,
            )
            for s in sessions
        ]
    )


@router.delete("/sessions/others", response_model=RevokeSessionsResponse)
async def revoke_other_sessions_endpoint(
    current_user: UserResponse = Depends(get_current_user),
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    """Revoke every session except the caller's current one (#83)."""
    current_sid = None
    try:
        current_sid = decode_access_token(token).get("sid")
    except AccessTokenError:
        pass

    revoked = await revoke_other_sessions(db, current_user.id, current_sid)
    return RevokeSessionsResponse(success=True, revoked=revoked)


@router.delete("/sessions/{session_id}", response_model=RevokeSessionsResponse)
async def revoke_session_endpoint(
    session_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke one of the caller's sessions by id (#83).

    Revoking blocklists the session's refresh token, so a subsequent
    ``/auth/refresh`` with it fails. Unknown / already-revoked / not-owned
    session ids return 404.
    """
    ok = await revoke_session(db, current_user.id, session_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No such active session.",
        )
    return RevokeSessionsResponse(success=True, revoked=1)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: UserResponse = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return current_user


@router.get("/me/permissions")
async def get_my_permissions(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the caller's effective permission grants/denies (Phase 3).

    Lets the frontend hide/disable actions the staff member lacks. The master
    (admin) is flagged ``is_master`` and gates nothing.
    """
    from dependencies.permissions import get_effective_permissions

    return await get_effective_permissions(db, current_user)


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Begin TOTP enrollment: mint a pending secret + provisioning URI (#81).

    Enrollment is not active until a generated code is verified at
    ``/auth/mfa/activate``.
    """
    service = MfaService(db)
    secret, uri = await service.begin_enrollment(current_user.id, current_user.email)
    return MfaEnrollResponse(secret=secret, otpauth_uri=uri, enabled=False)


@router.post("/mfa/activate", response_model=MfaActivateResponse)
async def mfa_activate(
    payload: MfaCodeRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm enrollment with a TOTP code; enable MFA + return recovery codes (#81)."""
    service = MfaService(db)
    codes = await service.activate(current_user.id, payload.code)
    if codes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code. Enroll first, then enter the current code.",
        )
    return MfaActivateResponse(enabled=True, recovery_codes=codes)


@router.get("/mfa/status", response_model=MfaStatusResponse)
async def mfa_status(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Whether MFA is active for the caller (+ remaining recovery codes) (#81)."""
    service = MfaService(db)
    row = await service.get(current_user.id)
    enabled = bool(row and row.enabled)
    return MfaStatusResponse(
        enabled=enabled,
        recovery_codes_remaining=service._remaining_count(row) if enabled else 0,
    )


class LogoutRequest(BaseModel):
    """Optional body for logout — pass the refresh token to revoke it too."""

    refresh_token: Optional[str] = None


@router.post("/logout")
async def logout(
    body: LogoutRequest = Body(default=LogoutRequest()),
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current session server-side (Phase 3).

    Adds the access token's ``jti`` to the blocklist so the bearer token can no
    longer be used even before it expires. If a ``refresh_token`` is supplied it
    is revoked as well, so the session cannot be silently resurrected via
    ``/auth/refresh``.
    """
    try:
        claims = decode_access_token(token)
    except AccessTokenError as exc:
        # An already-invalid token needs no revocation; treat logout as success.
        logger.debug("Logout with invalid token: %s", exc.message)
        return {"success": True}

    await revoke_token(
        db,
        claims.get("jti"),
        user_id=claims.get("sub"),
        token_type="access",
        expires_at=claims.get("exp"),
        reason="logout",
    )

    # Drop the session this access token belongs to (#83) so it no longer shows
    # as active and its refresh token is blocklisted in one shot.
    if claims.get("sid") and claims.get("sub"):
        await revoke_session(db, claims["sub"], claims["sid"])

    if body and body.refresh_token:
        try:
            refresh_claims = decode_access_token(body.refresh_token)
            await revoke_token(
                db,
                refresh_claims.get("jti"),
                user_id=refresh_claims.get("sub"),
                token_type="refresh",
                expires_at=refresh_claims.get("exp"),
                reason="logout",
            )
        except AccessTokenError:
            pass

    return {"success": True}
