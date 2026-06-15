"""Password hashing helpers (local email/password authentication).

Uses bcrypt directly to avoid passlib/bcrypt version-compatibility issues.
"""
import logging
import re

import bcrypt

logger = logging.getLogger(__name__)


class PasswordPolicyError(ValueError):
    """Raised when a password fails the configured complexity policy.

    Subclasses ``ValueError`` so existing callers that already expect bad input
    as a ``ValueError`` keep working; the message is human-facing and safe to
    relay to the client (it names what the password is missing, never the value).
    """


def validate_password_complexity(password: str) -> None:
    """Enforce the configurable password-complexity policy (ISSUE-084).

    Reads the policy from :data:`core.config.settings` so a deployment can tune
    length and required character classes without code changes. Raises
    :class:`PasswordPolicyError` with a clear message when ``password`` is too
    weak; returns ``None`` when it complies.
    """
    from core.config import settings

    password = password or ""
    min_length = int(getattr(settings, "password_min_length", 8) or 8)
    require_upper = bool(getattr(settings, "password_require_uppercase", True))
    require_lower = bool(getattr(settings, "password_require_lowercase", True))
    require_digit = bool(getattr(settings, "password_require_digit", True))
    require_symbol = bool(getattr(settings, "password_require_symbol", False))

    failures = []
    if len(password) < min_length:
        failures.append(f"at least {min_length} characters")
    if require_upper and not re.search(r"[A-Z]", password):
        failures.append("an uppercase letter")
    if require_lower and not re.search(r"[a-z]", password):
        failures.append("a lowercase letter")
    if require_digit and not re.search(r"\d", password):
        failures.append("a digit")
    if require_symbol and not re.search(r"[^A-Za-z0-9]", password):
        failures.append("a symbol")

    if failures:
        raise PasswordPolicyError("Password must contain " + ", ".join(failures) + ".")


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
