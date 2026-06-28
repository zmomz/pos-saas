"""ISSUE-185 — the refresh cookie's SameSite/Secure policy is config-driven.

FE-01 (#146) issues the refresh token as an HttpOnly cookie with ``SameSite=Lax``.
A Lax cookie is *not* sent on cross-site sub-resource XHR, so the moment a
deployment serves the SPA and the API on different sites, the credentialed
``POST /auth/refresh`` stops carrying the cookie and every access-token expiry
bounces the user to ``/login``.

The default stays same-origin (``SameSite=Lax``), but a deployment that splits
the SPA and API across origins can opt in with ``REFRESH_COOKIE_CROSS_SITE=true``,
which switches the cookie to ``SameSite=None; Secure`` (the only combination a
browser honors on cross-site credentialed requests). Because that mode only works
alongside credentialed CORS with explicit origins, ``validate_secrets`` refuses a
prod boot that enables cross-site mode without ``ALLOWED_ORIGINS`` configured.
"""
import pytest
from core.config import settings, validate_secrets
from conftest import auth_headers, register_user, unique_email

COOKIE = "pos_refresh_token"


def _set_cookie_headers(resp):
    return [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]


def _refresh_set_cookie(resp):
    for line in _set_cookie_headers(resp):
        if line.startswith(f"{COOKIE}="):
            return line
    return None


async def _login(client):
    email = unique_email()
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "A"},
    )
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123"}
    )


def _pass_secret_validations(monkeypatch):
    """Satisfy the SEC-01 / SEC-05 startup checks so a prod boot fails (or not)
    solely on the ISSUE-185 cookie-policy invariant."""
    monkeypatch.setattr(settings, "jwt_secret_key", "j" * 64, raising=False)
    monkeypatch.setattr(settings, "secrets_encryption_key", "dedicated-key", raising=False)


def test_cross_site_in_prod_without_origins_refuses_boot(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    _pass_secret_validations(monkeypatch)
    monkeypatch.setattr(settings, "refresh_cookie_cross_site", True, raising=False)
    monkeypatch.setattr(settings, "allowed_origins", "", raising=False)
    with pytest.raises(RuntimeError):
        validate_secrets()


def test_cross_site_in_prod_with_origins_boots(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    _pass_secret_validations(monkeypatch)
    monkeypatch.setattr(settings, "refresh_cookie_cross_site", True, raising=False)
    monkeypatch.setattr(
        settings, "allowed_origins", "https://app.example.com", raising=False
    )
    validate_secrets()  # must not raise


def test_cross_site_in_dev_without_origins_is_allowed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setattr(settings, "refresh_cookie_cross_site", True, raising=False)
    monkeypatch.setattr(settings, "allowed_origins", "", raising=False)
    validate_secrets()  # dev stays frictionless — warn, don't refuse


def test_same_origin_default_in_prod_without_origins_boots(monkeypatch):
    """The default (cross-site off) imposes no new origin requirement."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    _pass_secret_validations(monkeypatch)
    monkeypatch.setattr(settings, "refresh_cookie_cross_site", False, raising=False)
    monkeypatch.setattr(settings, "allowed_origins", "", raising=False)
    validate_secrets()  # must not raise


async def test_default_refresh_cookie_is_samesite_lax(client):
    """Same-origin default is unchanged: SameSite=Lax."""
    resp = await _login(client)
    line = _refresh_set_cookie(resp)
    assert line is not None
    assert "samesite=lax" in line.lower()
    assert "samesite=none" not in line.lower()


async def test_cross_site_mode_sets_samesite_none_secure(client, monkeypatch):
    """Cross-site opt-in: SameSite=None and Secure so the cookie rides
    cross-site credentialed XHR (browsers reject SameSite=None without Secure)."""
    monkeypatch.setattr(settings, "refresh_cookie_cross_site", True, raising=False)
    resp = await _login(client)
    line = _refresh_set_cookie(resp)
    assert line is not None
    low = line.lower()
    assert "samesite=none" in low
    assert "secure" in low


async def test_cross_site_mode_logout_clears_with_matching_attributes(client, monkeypatch):
    """The clearing cookie must mirror the live cookie's SameSite/Secure or the
    browser won't match it on logout."""
    monkeypatch.setattr(settings, "refresh_cookie_cross_site", True, raising=False)
    _, token, _ = await register_user(client)
    resp = await client.post("/api/v1/auth/logout", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    line = _refresh_set_cookie(resp)
    assert line is not None
    low = line.lower()
    assert "max-age=0" in low
    assert "samesite=none" in low
    assert "secure" in low
