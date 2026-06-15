"""RFC 6238 TOTP + RFC 4226 HOTP, implemented on the standard library.

We avoid a third-party dependency (``pyotp``) — TOTP is a thin wrapper over an
HMAC, and keeping it in-tree means tests and the server share one generator with
no extra install. The same code an authenticator app runs is exercised by the
test suite to mint the codes it submits.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

# 30-second steps, 6 digits, SHA-1 — the de-facto authenticator-app defaults.
DEFAULT_PERIOD = 30
DEFAULT_DIGITS = 6


def generate_secret(length: int = 20) -> str:
    """Return a fresh base32 TOTP secret (no padding) of ``length`` random bytes."""
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _hotp(secret: str, counter: int, digits: int = DEFAULT_DIGITS) -> str:
    """RFC 4226 HOTP for a base32 ``secret`` and integer ``counter``."""
    # Re-pad to a multiple of 8 for base32 decode; secrets are stored unpadded.
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def totp_now(secret: str, for_time: float | None = None, period: int = DEFAULT_PERIOD) -> str:
    """The current TOTP code for ``secret`` (the value an app would display now)."""
    now = time.time() if for_time is None else for_time
    return _hotp(secret, int(now // period))


def verify_totp(
    secret: str,
    code: str,
    for_time: float | None = None,
    period: int = DEFAULT_PERIOD,
    valid_window: int = 1,
) -> bool:
    """Validate ``code`` against ``secret``, tolerating ``±valid_window`` steps.

    The window absorbs clock skew between the authenticator and the server.
    Comparison is constant-time to avoid leaking via timing.
    """
    if not secret or not code:
        return False
    code = code.strip()
    if not code.isdigit():
        return False
    now = time.time() if for_time is None else for_time
    counter = int(now // period)
    for drift in range(-valid_window, valid_window + 1):
        if hmac.compare_digest(_hotp(secret, counter + drift), code):
            return True
    return False


def provisioning_uri(secret: str, account_name: str, issuer: str) -> str:
    """Build an ``otpauth://`` URI for QR provisioning into an authenticator app."""
    label = quote(f"{issuer}:{account_name}")
    params = f"secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={DEFAULT_DIGITS}&period={DEFAULT_PERIOD}"
    return f"otpauth://totp/{label}?{params}"
