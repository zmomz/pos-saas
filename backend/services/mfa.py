"""MFA (TOTP) enrollment + verification service (ISSUE-081).

Owns the ``user_mfa`` row lifecycle: begin enrollment (pending secret), confirm
with a TOTP code (enable + mint single-use recovery codes), challenge on login,
and consume a recovery code. Recovery codes are stored only as bcrypt hashes.
"""
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from core.config import settings
from core.security import hash_password, verify_password
from core.totp import generate_secret, provisioning_uri, verify_totp
from models.mfa import UserMfa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10


def _new_recovery_code() -> str:
    """A human-friendly single-use backup code, e.g. ``3f9a-1c2b``."""
    raw = secrets.token_hex(4)
    return f"{raw[:4]}-{raw[4:]}"


class MfaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, user_id: str) -> Optional[UserMfa]:
        result = await self.db.execute(select(UserMfa).where(UserMfa.user_id == str(user_id)))
        return result.scalar_one_or_none()

    async def is_enabled(self, user_id: str) -> bool:
        row = await self.get(user_id)
        return bool(row and row.enabled)

    @staticmethod
    def _remaining_count(row: Optional[UserMfa]) -> int:
        if row is None or not row.recovery_codes:
            return 0
        return sum(1 for c in json.loads(row.recovery_codes) if not c.get("used"))

    async def remaining_recovery_codes(self, user_id: str) -> int:
        return self._remaining_count(await self.get(user_id))

    async def begin_enrollment(self, user_id: str, account_name: str) -> tuple[str, str]:
        """Create/refresh a pending (not-yet-enabled) secret. Returns (secret, uri).

        Re-enrolling before confirmation rotates the pending secret. An already
        enabled account keeps its secret (it must be disabled first).
        """
        issuer = getattr(settings, "app_name", None) or "POS"
        row = await self.get(user_id)
        if row and row.enabled:
            secret = row.secret
        else:
            secret = generate_secret()
            if row is None:
                row = UserMfa(user_id=str(user_id), secret=secret, enabled=False)
                self.db.add(row)
            else:
                row.secret = secret
                row.enabled = False
            await self.db.commit()
        return secret, provisioning_uri(secret, account_name, issuer)

    async def activate(self, user_id: str, code: str) -> Optional[List[str]]:
        """Confirm a pending enrollment with a TOTP ``code``.

        On success: flip ``enabled``, mint a fresh set of single-use recovery
        codes (stored hashed), and return the plaintext codes ONCE for the user
        to save. Returns ``None`` if there is no pending secret or the code is
        wrong.
        """
        row = await self.get(user_id)
        if row is None or not row.secret:
            return None
        if not verify_totp(row.secret, code):
            return None

        plaintext = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        row.recovery_codes = json.dumps(
            [{"hash": hash_password(c), "used": False} for c in plaintext]
        )
        row.enabled = True
        row.confirmed_at = datetime.now(timezone.utc)
        await self.db.commit()
        return plaintext

    async def verify_code(self, user_id: str, code: str) -> bool:
        """Validate a second-factor ``code`` for an MFA-enabled user.

        Accepts either a current TOTP code or one of the single-use recovery
        codes. A matched recovery code is burned (marked used) so it cannot be
        replayed.
        """
        row = await self.get(user_id)
        if row is None or not row.enabled or not row.secret:
            return False
        if verify_totp(row.secret, code):
            return True
        return await self._consume_recovery_code(row, code)

    async def _consume_recovery_code(self, row: UserMfa, code: str) -> bool:
        """Burn a matching unused recovery code; return whether one matched."""
        if not row.recovery_codes:
            return False
        entries = json.loads(row.recovery_codes)
        candidate = (code or "").strip().lower()
        for entry in entries:
            if entry.get("used"):
                continue
            if verify_password(candidate, entry["hash"]):
                entry["used"] = True
                row.recovery_codes = json.dumps(entries)
                await self.db.commit()
                return True
        return False
