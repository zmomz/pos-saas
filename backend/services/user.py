import logging
import time
from typing import Optional

from core.security import hash_password, verify_password
from models.auth import User
from models.user_profile import UserProfile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Notification-preference fields that live on UserProfile.
_PREF_FIELDS = ("email_alerts", "low_stock_alerts", "daily_summary", "transaction_alerts")

logger = logging.getLogger(__name__)


class PasswordError(Exception):
    """Raised when a password change fails validation (wrong current password)."""


class EmailInUseError(Exception):
    """Raised when a profile update would collide with another account's email."""


class UserService:
    @staticmethod
    async def get_user_profile(db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user profile by user ID."""
        start_time = time.time()
        logger.debug(f"[DB_OP] Starting get_user_profile - user_id: {user_id}")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        logger.debug(
            f"[DB_OP] Get user profile completed in {time.time() - start_time:.4f}s - found: {user is not None}"
        )
        return user

    @staticmethod
    async def update_user_profile(
        db: AsyncSession,
        user_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Optional[User]:
        """Update the account identity fields (name / email / phone).

        Only the provided fields are touched; passing ``None`` leaves a field
        unchanged. An empty string clears ``name``/``phone``. ``email`` is
        normalised (trim + lowercase, mirroring registration) and checked for
        uniqueness against other accounts — a collision raises
        :class:`EmailInUseError`.
        """
        start_time = time.time()
        logger.debug(f"[DB_OP] Starting update_user_profile - user_id: {user_id}")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        logger.debug(f"[DB_OP] User lookup completed in {time.time() - start_time:.4f}s - found: {user is not None}")
        if not user:
            return None

        changed = False
        if name is not None:
            user.name = name.strip() or None
            changed = True
        if phone is not None:
            user.phone = phone.strip() or None
            changed = True
        if email is not None:
            normalized = email.strip().lower()
            if normalized and normalized != (user.email or "").lower():
                clash = await db.execute(
                    select(User.id).where(func.lower(User.email) == normalized, User.id != user_id)
                )
                if clash.scalar_one_or_none() is not None:
                    raise EmailInUseError("That email is already in use")
                user.email = normalized
                changed = True

        if changed:
            start_time_update = time.time()
            logger.debug("[DB_OP] Starting user profile update")
            await db.commit()
            await db.refresh(user)
            logger.debug(f"[DB_OP] User profile update completed in {time.time() - start_time_update:.4f}s")

        return user

    @staticmethod
    async def get_preferences(db: AsyncSession, user_id: str) -> Optional[UserProfile]:
        """Return the user's persisted profile preferences, or None if never saved."""
        result = await db.execute(select(UserProfile).where(UserProfile.user_id == str(user_id)))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_preferences(
        db: AsyncSession,
        user_id: str,
        display_name=None,
        notification_prefs: Optional[dict] = None,
    ) -> UserProfile:
        """Persist (creating on first save) the user's profile + notification prefs.

        Only the provided fields are touched; omitting ``display_name`` or
        ``notification_prefs`` leaves the stored value unchanged.
        """
        result = await db.execute(select(UserProfile).where(UserProfile.user_id == str(user_id)))
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = UserProfile(user_id=str(user_id))
            db.add(profile)

        if display_name is not None:
            profile.display_name = display_name
        if notification_prefs is not None:
            for field in _PREF_FIELDS:
                if field in notification_prefs and notification_prefs[field] is not None:
                    setattr(profile, field, bool(notification_prefs[field]))

        await db.commit()
        await db.refresh(profile)
        return profile

    @staticmethod
    async def change_password(
        db: AsyncSession, user_id: str, current_password: str, new_password: str
    ) -> User:
        """Change a user's password after verifying their current one.

        Raises:
            PasswordError: if the user is missing or the current password is wrong.
        """
        result = await db.execute(select(User).where(User.id == str(user_id)))
        user = result.scalar_one_or_none()
        if not user or not user.hashed_password:
            raise PasswordError("User not found or password not set")

        if not verify_password(current_password, user.hashed_password):
            raise PasswordError("Current password is incorrect")

        user.hashed_password = hash_password(new_password)
        # First password change clears the force-reset flag (first-login flow).
        if getattr(user, "must_change_password", False):
            user.must_change_password = False
        await db.commit()
        await db.refresh(user)
        logger.info("Password changed for user %s", user_id)
        return user
