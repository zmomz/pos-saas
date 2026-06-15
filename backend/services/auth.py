import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from core.auth import create_access_token, create_refresh_token
from core.config import settings
from core.database import db_manager
from core.security import hash_password, verify_password
from models.auth import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        password: str,
        name: Optional[str] = None,
        role: str = "user",
        user_id: Optional[str] = None,
    ) -> User:
        """Create a local user with a hashed password."""
        existing = await self.get_user_by_email(email)
        if existing:
            raise ValueError("A user with this email already exists")

        user = User(
            id=user_id or str(uuid.uuid4()),
            email=email.strip().lower(),
            name=name,
            hashed_password=hash_password(password),
            role=role,
            last_login=datetime.now(timezone.utc),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        logger.info("Created local user %s (role=%s)", user.id, role)
        return user

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Return the user if the email/password are valid, else None."""
        user = await self.get_user_by_email(email)
        if not user or not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def issue_app_token(
        self, user: User, sid: Optional[str] = None
    ) -> Tuple[str, datetime, Dict[str, Any]]:
        """Generate application JWT token for the authenticated user.

        ``sid`` ties the access token to the session (refresh-token ``jti``) it
        was minted from, so active-session management (ISSUE-083) can flag the
        caller's *current* session and exclude it from "revoke all others".
        """
        try:
            expires_minutes = int(getattr(settings, "jwt_expire_minutes", 1440))
        except (TypeError, ValueError):
            logger.warning("Invalid JWT_EXPIRE_MINUTES value; fallback to 1440 minutes")
            expires_minutes = 1440
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

        claims: Dict[str, Any] = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "must_change_password": bool(getattr(user, "must_change_password", False)),
            # Security stamp (ISSUE-082): rejected once the user resets and the
            # stored token_version moves past this value.
            "sv": int(getattr(user, "token_version", 0) or 0),
        }
        if user.name:
            claims["name"] = user.name
        if user.last_login:
            claims["last_login"] = user.last_login.isoformat()
        if sid:
            claims["sid"] = sid

        token = create_access_token(claims, expires_minutes=expires_minutes)
        return token, expires_at, claims

    def issue_refresh_token(self, user: User, jti: Optional[str] = None) -> str:
        """Generate a long-lived refresh token for the user.

        When ``jti`` is supplied it becomes the token's id, so the caller can
        register a matching :class:`UserSession` and later revoke it (#83).
        """
        claims: Dict[str, Any] = {
            "sub": user.id,
            "email": user.email,
            "sv": int(getattr(user, "token_version", 0) or 0),
        }
        if jti:
            claims["jti"] = jti
        return create_refresh_token(claims)

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == str(user_id)))
        return result.scalar_one_or_none()


async def get_security_stamp(db: AsyncSession, user_id: str) -> Optional[int]:
    """Return a user's current ``token_version`` (security stamp), or ``None``.

    Used to validate a presented token's ``sv`` claim — see ISSUE-082. ``None``
    means the user no longer exists (caller should reject).
    """
    result = await db.execute(select(User.token_version).where(User.id == str(user_id)))
    row = result.scalar_one_or_none()
    return None if row is None else int(row or 0)


async def initialize_admin_user():
    """Seed the master/admin account from ADMIN_EMAIL / ADMIN_PASSWORD env vars."""
    if "SKIP_INIT_ADMIN" in os.environ:
        logger.info("SKIP_INIT_ADMIN set; skipping admin initialization")
        return

    from services.database import initialize_database

    # Ensure database is initialized first
    await initialize_database()

    admin_email = (getattr(settings, "admin_email", "") or "").strip().lower()
    admin_password = getattr(settings, "admin_password", "") or ""
    admin_name = getattr(settings, "admin_name", "Administrator") or "Administrator"

    if not admin_email or not admin_password:
        logger.warning(
            "ADMIN_EMAIL/ADMIN_PASSWORD not configured; skipping admin seed. "
            "Set them in the environment to create the initial master account."
        )
        return

    async with db_manager.async_session_maker() as db:
        service = AuthService(db)
        existing = await service.get_user_by_email(admin_email)
        if existing:
            # Make sure the seeded account stays an admin (master).
            if existing.role != "admin":
                existing.role = "admin"
                await db.commit()
                logger.info("Promoted existing user %s to admin", admin_email)
            else:
                logger.debug("Admin user %s already exists", admin_email)
            return

        await service.create_user(
            email=admin_email,
            password=admin_password,
            name=admin_name,
            role="admin",
        )
        logger.info("Seeded master/admin account: %s", admin_email)
