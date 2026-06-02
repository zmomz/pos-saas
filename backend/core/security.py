"""Password hashing helpers (local email/password authentication).

Uses bcrypt directly to avoid passlib/bcrypt version-compatibility issues.
"""
import logging

import bcrypt

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt and return a UTF-8 string."""
    if not password:
        raise ValueError("Password must not be empty")
    salt = bcrypt.gensalt()
    digest = bcrypt.hashpw(password.encode("utf-8"), salt)
    return digest.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        logger.warning("Password verification error: %s", type(exc).__name__)
        return False
