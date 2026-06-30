from typing import Optional

from core.database import get_db
from dependencies.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from models.auth import User
from pydantic import BaseModel
from schemas.auth import (
    ChangePasswordRequest,
    NotificationPrefs,
    UpdateUserPreferencesRequest,
    UserPreferencesResponse,
    UserResponse,
)
from services.user import EmailConflictError, PasswordError, UserService
from sqlalchemy.ext.asyncio import AsyncSession
from utils.password_policy import enforce_password_complexity

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UpdateProfileRequest(BaseModel):
    # All optional + PATCH-like: only the fields actually present in the body are
    # applied (see ``model_fields_set`` below), so a name-only edit never wipes
    # the phone and vice versa (#203, parity #4).
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


@router.get("/profile", response_model=UserResponse)
async def get_profile(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    profile = await UserService.get_user_profile(db, current_user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    return profile


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update current user profile (name/email/phone — only fields sent are applied)."""
    supplied = profile_data.model_fields_set
    kwargs = {f: getattr(profile_data, f) for f in ("name", "email", "phone") if f in supplied}
    try:
        profile = await UserService.update_user_profile(db, current_user.id, **kwargs)
    except EmailConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    return profile


def _to_preferences_response(profile) -> UserPreferencesResponse:
    if profile is None:
        return UserPreferencesResponse()
    return UserPreferencesResponse(
        display_name=profile.display_name,
        notification_prefs=NotificationPrefs(
            email_alerts=profile.email_alerts,
            whatsapp_alerts=profile.whatsapp_alerts,
            push_alerts=profile.push_alerts,
            low_stock_alerts=profile.low_stock_alerts,
            daily_summary=profile.daily_summary,
            transaction_alerts=profile.transaction_alerts,
        ),
    )


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the authenticated user's persisted profile + notification prefs.

    Falls back to server-side defaults when the user has never saved a profile.
    """
    profile = await UserService.get_preferences(db, current_user.id)
    return _to_preferences_response(profile)


@router.put("/preferences", response_model=UserPreferencesResponse)
async def update_preferences(
    payload: UpdateUserPreferencesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist the authenticated user's profile + notification prefs (server-side)."""
    profile = await UserService.update_preferences(
        db,
        current_user.id,
        display_name=payload.display_name,
        notification_prefs=(
            payload.notification_prefs.model_dump() if payload.notification_prefs is not None else None
        ),
    )
    return _to_preferences_response(profile)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the authenticated user's password.

    Requires the correct current password. Returns 400 on mismatch.
    """
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )
    enforce_password_complexity(payload.new_password)
    try:
        await UserService.change_password(
            db, current_user.id, payload.current_password, payload.new_password
        )
    except PasswordError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"success": True, "message": "Password changed successfully"}
