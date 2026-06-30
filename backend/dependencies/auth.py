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

    The authoritative live DB flag is always re-read — the token's own
    ``must_change_password`` claim is never trusted to decide whether to check
    (#183). This covers two directions:

    - **Admin-forced rotation** sets the flag on a user who already holds a live
      access token whose claim is ``False``; that stale-claim token must still be
      gated until the password is rotated.
    - A user who has just rotated their credential — which clears the flag
      (``UserService.change_password``) without bumping the security stamp — is
      unblocked immediately on their existing (still ``True``-claiming) token,
      satisfying the "flag cleared after change -> 200" guarantee.
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

    Two independent suspension flags gate every authenticated endpoint, both
    resolved through the caller's :class:`TenantScope` so the staff→merchant and
    merchant→agent mappings are computed in exactly one place:

    - **SEC-06 — tenancy-suspended merchant** (``Clients.is_active = False``):
      the merchant and any **staff** member operating under it (who has no client
      row of their own) are blocked.
    - **SEC-02 — quota-suspended agent** (``Agents.is_active = False``, set by the
      quota dunning sweep when an agent fails to pay for his slot quota): the agent
      himself AND every merchant provisioned under him go dark together (cascade,
      #184). ``scope.agent_id`` is the caller's *owning* agent — his own id for an
      agent self-login, the merchant's ``agent_id`` for a client/staff caller.

    Master accounts have no owning merchant or agent (``owner_user_id`` /
    ``agent_id`` are ``None``) and stay unaffected. Imported lazily to avoid a
    circular import at module load.
    """
    from dependencies.tenancy import resolve_tenant_scope
    from models.agents import Agents
    from models.clients import Clients
    from models.staff_members import Staff_members

    scope = await resolve_tenant_scope(
        db, UserResponse(id=str(user_id), email="", role="user")
    )

    # Issue #216 — staff lifecycle: a suspended or terminated staff member is
    # blocked on their *own* login regardless of the owning merchant's state.
    # Keyed on the immutable login FK (SEC-11), never the mutable email. Bumping
    # the login's security stamp already kills live tokens on suspend/terminate;
    # this is the durable, replay-proof backstop checked on every request.
    staff_status = (
        await db.execute(
            select(Staff_members.status).where(Staff_members.login_user_id == str(user_id))
        )
    ).scalars().first()
    if staff_status in ("suspended", "terminated"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your staff access has been revoked. Contact your manager.",
        )

    # SEC-06: the owning merchant's row (``None`` for an agent/master => no merchant
    # to suspend). An is_active that is explicitly False => suspended; NULL/True pass.
    # M8 (issue-215): an archived merchant (``archived_at`` set) is likewise blocked —
    # a distinct lifecycle state from the non-payment suspension above.
    if scope.owner_user_id is not None:
        row = (
            await db.execute(
                select(Clients.is_active, Clients.archived_at).where(
                    Clients.user_id == str(scope.owner_user_id)
                )
            )
        ).one_or_none()
        if row is not None:
            client_active, client_archived_at = row
            if client_active is False:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This account has been suspended. Contact your provider.",
                )
            if client_archived_at:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This account has been archived. Contact your provider.",
                )

    # SEC-02: the owning agent (``None`` for master => no agent to suspend). A
    # suspended agent blocks himself and cascades to all his merchants.
    if scope.agent_id is not None:
        agent_active = (
            await db.execute(
                select(Agents.is_active).where(Agents.id == scope.agent_id)
            )
        ).scalar_one_or_none()
        if agent_active is False:
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

    # SEC-07: enforce the forced-password-change gate. The cheap indexed DB read
    # runs on every protected request so admin-forced rotation revokes a live
    # token whose own claim is still ``False`` (#183); the stale token claim is
    # never trusted to decide whether to check.
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
