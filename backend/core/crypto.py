"""Application secrets at rest — AES-256-GCM.

A single small helper for encrypting secrets we must store and later read back
(payment-gateway keys, saved card tokens, ZATCA CSIDs/keys). The PAN itself never
reaches us — only reusable gateway tokens do (PAY-09) — but those tokens, the
agents' own Moyasar API/webhook keys, and ZATCA credentials are all sensitive and
are kept encrypted in the database.

The key is derived (SHA-256) from, in order of preference:
  * ``SECRETS_ENCRYPTION_KEY`` — the dedicated app-wide secret;
  * ``ZATCA_ENCRYPTION_KEY``   — kept for backward compatibility with already
    encrypted ZATCA material;
  * ``JWT_SECRET_KEY``         — a dev/out-of-the-box fallback.

Production deployments MUST set a dedicated key — losing it makes every stored
secret unrecoverable.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.config import settings


def _aes_key() -> bytes:
    """Derive a 32-byte AES-256 key from the configured secret material."""
    raw = (
        getattr(settings, "secrets_encryption_key", None)
        or getattr(settings, "zatca_encryption_key", None)
        or settings.jwt_secret_key
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(plaintext: str) -> str:
    """AES-256-GCM encrypt and base64-encode ``nonce || ciphertext||tag``."""
    nonce = os.urandom(12)
    ct = AESGCM(_aes_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Inverse of :func:`encrypt_secret`. Raises on tamper/wrong key."""
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(_aes_key()).decrypt(nonce, ct, None).decode("utf-8")
