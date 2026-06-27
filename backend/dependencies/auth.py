import hashlib
import logging
from datetime import datetime
from typing import Optional

from core.auth import AccessTokenError, decode_access_token
from core.database import get_db
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models.auth import User
from schemas.auth import UserResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

# SEC-07: a user with a pending forced password change may still reach the change
# endpoint itself, plus the whole auth surface (logout, /me, sessions, mfa) so they
# can rotate the credential and read their own state. Everything else is gated.
_PASSWORD_CHANGE_EXEMPT_PATHS = frozenset({"/api/v1/users/change-password"})
_PASSWORD_CHANGE_EXEMPT_PREFIXES = ("/api/v1/auth/",)


def _is_password_change_exempt(path: str) -> bool:
    """Whether ``path`` stays reachable for a user who must change their password."""
    if path in _PASSWORD_CHANGE_EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PASSWORD_CHANGE_EXEMPT_PREFIXES)


async def _assert_password_changed(db: AsyncSession, user_id: str, path: str) -> None:
    """Block a force-flagged user from every non-exempt endpoint (SEC-07).

    Called only when the presented token *claims* ``must_change_password``. The
    live DB flag is re-read so a user who has just rotated their credential — which
    clears the flag (``UserService.change_password``) without bumping the security
    stamp — is unblocked immediately on their existing token, satisfying the
    "flag cleared after change -> 200" guarantee.
    """
    if _is_password_change_exempt(path):
        return
    result = await db.execute(select(User.must_change_password).where(User.id == str(user_id)))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must change your password before continuing.",
        )


async def get_bearer_token(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> str:
    """Extract bearer token from Authorization header."""
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials

    logger.debug("Authentication required for request %s %s", request.method, request.url.path)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication credentials were not provided")


async def _assert_account_active(db: AsyncSession, user_id: str) -> None:
    """Block suspended tenants from authenticating.

    Tenancy-suspended clients (``clients.is_active = False``) must not be able to
    use any authenticated endpoint. The suspension flag lives on the *owning*
    merchant's ``Clients`` row, so we resolve the caller to their tenancy owner
    first (exactly as ``resolve_tenant_scope`` does): a **staff** member has no
    client row of their own, yet must inherit the owning merchant's suspension
    (SEC-06). Master/agent accounts have no owner to suspend and stay unaffected.
    Imported lazily to avoid a circular import at module load.
    """
    from dependencies.tenancy import resolve_owner_user_id
    from models.clients import Clients

    # ``None`` => platform master (unrestricted, no client row). For everyone else
    # this is the owning merchant's id — the caller's own id for a client/agent,
    # the owning merchant's for a staff member.
    owner_user_id = await resolve_owner_user_id(db, str(user_id))
    if owner_user_id is None:
        return

    result = await db.execute(
        select(Clients.is_active).where(Clients.user_id == str(owner_user_id))
    )
    is_active = result.scalar_one_or_none()
    # ``None`` => no client row (agent/master) => allowed. A row with is_active
    # explicitly False => suspended.
    if is_active is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended. Contact your provider.",
        )


async def get_current_user(
    request: Request,
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Dependency to get current authenticated user via JWT token."""
    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        # Log error type only, not the full exception which may contain sensitive token data
        logger.warning("Token validation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)

    # Reject refresh tokens being used as access tokens.
    if payload.get("type") == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh tokens cannot be used to access resources",
        )

    # Reject any other non-access ticket (e.g. the short-lived MFA second-factor
    # ticket, ISSUE-081) — only a real access token reaches protected resources.
    token_type = payload.get("type")
    if token_type is not None and token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This token cannot be used to access resources",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")

    # Server-side revocation (Phase 3): a logged-out / forcibly-revoked token is
    # rejected even though its signature and ``exp`` are still valid.
    from services.token_revocation import is_token_revoked

    if await is_token_revoked(db, payload.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This session has been logged out. Please sign in again.",
        )

    # Security stamp (ISSUE-082): a password reset bumps the user's token_version,
    # so a token minted before the reset no longer matches and is rejected.
    from services.auth import get_security_stamp

    current_stamp = await get_security_stamp(db, user_id)
    if current_stamp is None or int(payload.get("sv", 0) or 0) != current_stamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This session is no longer valid. Please sign in again.",
        )

    await _assert_account_active(db, user_id)

    # SEC-07: enforce the forced-password-change gate. Only flagged tokens pay the
    # extra DB read; unflagged users (the common case) are untouched.
    if bool(payload.get("must_change_password", False)):
        await _assert_password_changed(db, user_id, request.url.path)

    last_login_raw = payload.get("last_login")
    last_login = None
    if isinstance(last_login_raw, str):
        try:
            last_login = datetime.fromisoformat(last_login_raw)
        except ValueError:
            # Log user hash instead of actual user ID to avoid exposing sensitive information
            user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()[:8] if user_id else "unknown"
            logger.debug("Failed to parse last_login for user hash: %s", user_hash)

    return UserResponse(
        id=user_id,
        email=payload.get("email", ""),
        name=payload.get("name"),
        role=payload.get("role", "user"),
        must_change_password=bool(payload.get("must_change_password", False)),
        last_login=last_login,
    )


async def get_admin_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Dependency to ensure current user has admin role."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
