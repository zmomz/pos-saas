import logging
import time
from typing import Optional

from core.security import hash_password, verify_password
from models.auth import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PasswordError(Exception):
    """Raised when a password change fails validation (wrong current password)."""


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
    async def update_user_profile(db: AsyncSession, user_id: str, name: Optional[str] = None) -> Optional[User]:
        """Update user profile."""
        start_time = time.time()
        logger.debug(f"[DB_OP] Starting update_user_profile - user_id: {user_id}")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        logger.debug(f"[DB_OP] User lookup completed in {time.time() - start_time:.4f}s - found: {user is not None}")

        if user and name is not None:
            start_time_update = time.time()
            logger.debug("[DB_OP] Starting user profile update")
            user.name = name
            await db.commit()
            await db.refresh(user)
            logger.debug(f"[DB_OP] User profile update completed in {time.time() - start_time_update:.4f}s")

        return user

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
