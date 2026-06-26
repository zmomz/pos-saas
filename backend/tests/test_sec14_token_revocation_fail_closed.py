"""SEC-14 — token-revocation must fail closed on tokens lacking a ``jti``.

``is_token_revoked`` is the server-side blocklist check consulted on every
authenticated request. Its docstring promises a *fail-closed* policy, but it
early-returned ``False`` (allowed) whenever the token carried no ``jti`` claim.
Every token the app mints now carries a ``jti`` (``core.auth._create_token``),
so a missing ``jti`` signals a forged or tampered token — it must be rejected,
not waved through.
"""
import uuid

from core.database import db_manager
from services.token_revocation import is_token_revoked, revoke_token


async def test_missing_jti_is_treated_as_revoked():
    """A token with no ``jti`` claim is treated as revoked (fail closed)."""
    async with db_manager.async_session_maker() as db:
        assert await is_token_revoked(db, None) is True
        assert await is_token_revoked(db, "") is True


async def test_jti_bearing_tokens_unaffected():
    """A real ``jti`` is allowed until it is explicitly revoked."""
    jti = uuid.uuid4().hex
    async with db_manager.async_session_maker() as db:
        # Not on the blocklist -> allowed.
        assert await is_token_revoked(db, jti) is False
        # After revocation -> blocked.
        await revoke_token(db, jti, token_type="access")
        assert await is_token_revoked(db, jti) is True
