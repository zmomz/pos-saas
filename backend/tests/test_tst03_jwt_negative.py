"""TST-03 (audit F3) — JWT forgery / expiry / algorithm negative tests.

The suite minted tokens only through the live API (server-signed with the real
secret) and never asserted what happens when a *forged* or *expired* token
reaches a protected endpoint. The decode path in ``core.auth.decode_access_token``
pins the signing key and the allowed algorithm and lets ``jose`` enforce ``exp``,
but nothing exercised those guards from the outside — a regression that disabled
signature verification, widened the algorithm allow-list to ``none``, or turned
off expiry checking would have slipped through green.

This module drives forged tokens through ``GET /api/v1/auth/me`` — the canonical
``get_current_user`` guarded route — asserting every one is rejected with 401.
One behavior per test:

  - wrong-secret    -> signature mismatch           -> 401
  - alg:none        -> unsigned, algorithm rejected  -> 401
  - expired         -> real secret, past ``exp``     -> 401
  - default-secret  -> signed with the source-visible default -> 401

Crucially each forged token reuses the claims of a *real, registered* user
(same ``sub``, security stamp ``sv``, ``jti`` …) and changes nothing but the
defect under test. So the rejection can only come from the signature / algorithm
/ expiry guard — not from a missing user or a stale security stamp. That makes
the tests non-vacuous: disable the matching guard (``verify=False``, allow
``none``, or ``verify_exp=False``) and decode would succeed against a genuine
user, flipping the assertion to 200. A positive control proves the real token
itself reaches the route, so the 401s are real rejections of a forgery.
"""
import base64
import json
from datetime import datetime, timezone

import pytest
from jose import jwt

from core.config import DEFAULT_JWT_SECRET, settings

from conftest import auth_headers, register_user

ME = "/api/v1/auth/me"


async def _real_claims(client) -> tuple[str, dict]:
    """Register a user and return (real_token, its decoded claims).

    The claims carry everything ``get_current_user`` requires of a *valid* token
    (real ``sub``, matching security stamp ``sv``, unrevoked ``jti``, future
    ``exp``), so a forgery built from them isolates exactly one broken guard.
    """
    _user, token, _ = await register_user(client)
    return token, jwt.get_unverified_claims(token)


def _alg_none_token(claims: dict) -> str:
    """Hand-build an unsigned ``alg:none`` token (jose refuses to *encode* one)."""

    def _seg(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{_seg({'alg': 'none', 'typ': 'JWT'})}.{_seg(claims)}."  # empty signature


@pytest.mark.asyncio
async def test_valid_token_authorizes(client):
    """Positive control: the real server-minted token reaches the protected route."""
    token, _claims = await _real_claims(client)
    resp = await client.get(ME, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_wrong_secret_token_rejected(client):
    """Real user's claims re-signed with the wrong key -> signature mismatch -> 401."""
    _token, claims = await _real_claims(client)
    forged = jwt.encode(claims, "a-different-secret-not-the-real-one", algorithm=settings.jwt_algorithm)
    resp = await client.get(ME, headers=auth_headers(forged))
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_alg_none_token_rejected(client):
    """Real user's claims as an unsigned ``alg:none`` token -> algorithm rejected -> 401."""
    _token, claims = await _real_claims(client)
    forged = _alg_none_token(claims)
    resp = await client.get(ME, headers=auth_headers(forged))
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_expired_token_rejected(client):
    """Real user's claims, real secret, but ``exp`` set in the past -> 401."""
    _token, claims = await _real_claims(client)
    claims["exp"] = int(datetime.now(timezone.utc).timestamp()) - 3600
    expired = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    resp = await client.get(ME, headers=auth_headers(expired))
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_default_secret_token_rejected(client):
    """Real user's claims re-signed with the source-visible default secret -> 401."""
    _token, claims = await _real_claims(client)
    forged = jwt.encode(claims, DEFAULT_JWT_SECRET, algorithm=settings.jwt_algorithm)
    resp = await client.get(ME, headers=auth_headers(forged))
    assert resp.status_code == 401, resp.text
