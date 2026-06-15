"""HTTP glue for the password-complexity policy (ISSUE-084).

``core.security.validate_password_complexity`` is the framework-agnostic rule;
this wrapper translates a policy violation into a 422 with a clear, client-safe
message so every set-password route enforces it identically.
"""
from fastapi import HTTPException, status

from core.security import PasswordPolicyError, validate_password_complexity


def enforce_password_complexity(password: str) -> None:
    """Validate ``password`` against the configured policy, raising HTTP 422 with
    a clear message when it fails."""
    try:
        validate_password_complexity(password)
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
