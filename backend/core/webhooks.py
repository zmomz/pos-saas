"""Shared webhook signature verification (SEC-02).

Moyasar signs each webhook by HMAC-SHA256'ing the *raw* request body with a shared
secret and sending the hex digest in a request header. We recompute the digest
over the raw bytes — never the re-serialized JSON, whose key order/spacing would
differ — and compare in constant time.

Fail-closed contract: a missing/empty secret, a missing header, or a mismatching
signature all return ``False``; the caller MUST reject with no state change. This
is the SEC-02 fix — the platform quota webhook previously trusted the body
whenever no secret was configured, letting anyone reach the URL and mass-suspend
agents (a DoS on every white-label tenant).
"""
import hashlib
import hmac
from typing import Optional

# The header Moyasar carries the body HMAC in.
MOYASAR_SIGNATURE_HEADER = "X-Moyasar-Signature"


def compute_moyasar_signature(raw_body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest of ``raw_body`` under ``secret``."""
    return hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()


def verify_moyasar_signature(
    raw_body: bytes, header_sig: Optional[str], secret: Optional[str]
) -> bool:
    """Return ``True`` only when ``header_sig`` is the valid HMAC of ``raw_body``.

    Fail-closed: an unset/empty ``secret`` or a missing ``header_sig`` returns
    ``False`` so an unconfigured deployment rejects rather than trusting the body.
    """
    if not secret or not header_sig:
        return False
    expected = compute_moyasar_signature(raw_body, secret)
    return hmac.compare_digest(expected, header_sig)
