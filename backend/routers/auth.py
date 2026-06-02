import logging

from core.auth import AccessTokenError, decode_access_token
from core.config import settings
from core.database import get_db
from dependencies.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    UserResponse,
)
from services.auth import AuthService
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


@router.post("/logout")
async def logout():
    """Logout is stateless for JWT auth — the client simply discards the token."""
    return {"success": True}
