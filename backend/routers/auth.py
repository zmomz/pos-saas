import logging
from typing import Optional

from core.auth import AccessTokenError, decode_access_token
from core.config import settings
from core.database import get_db
from dependencies.auth import get_bearer_token, get_current_user
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    UserResponse,
)
from services.auth import AuthService
from services.token_revocation import is_token_revoked, revoke_token
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
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

    service = AuthService(db)
    try:
        user = await service.create_user(
            email=payload.email,
            password=payload.password,
            name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    token, expires_at, _ = await service.issue_app_token(user)
    refresh_token = service.issue_refresh_token(user)
    return LoginResponse(
        token=token,
        expires_at=int(expires_at.timestamp()),
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password and return an access token."""
    service = AuthService(db)
    user = await service.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token, expires_at, _ = await service.issue_app_token(user)
    refresh_token = service.issue_refresh_token(user)
    return LoginResponse(
        token=token,
        expires_at=int(expires_at.timestamp()),
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


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

    token, expires_at, _ = await service.issue_app_token(user)
    return RefreshResponse(token=token, expires_at=int(expires_at.timestamp()))


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
