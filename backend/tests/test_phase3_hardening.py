"""Phase 3 — production hardening (security & ops).

Covers the testable security backbone wired in Phase 3:

* session revocation — logout blocklists the token (subsequent call 401) and a
  revoked refresh token can no longer mint access tokens;
* granular permissions — ``require_permission`` gates the refund route
  (403 without ``pos.refund``, 200 once granted);
* rate limiting — 429 after the bucket drains (when enabled);
* request validation — oversized body rejected with 413;
* webhooks — real signed dispatch with HMAC + retry on 5xx, fired on a sale;
* email — ``EmailService`` delegates to the real transport (dev fallback).
"""
import hashlib
import hmac

import httpx
from sqlalchemy import select

from conftest import (
    add_product,
    auth_headers,
    make_client_account,
    make_master_account,
    register_user,
)
from core.database import db_manager
from models.permissions import Permissions
from models.webhooks import Webhooks
from services.production import WebhookDispatcher, fire_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _set_vat(client_id: int, vat: str = "300000000000003"):
    from models.clients import Clients

    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _sale(client, headers, pid, *, qty=2):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": qty}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _set_permission(user_id: str, key: str, granted: bool):
    async with db_manager.async_session_maker() as db:
        existing = (
            await db.execute(
                select(Permissions).where(
                    Permissions.user_id == str(user_id),
                    Permissions.permission_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.is_granted = granted
        else:
            db.add(
                Permissions(user_id=str(user_id), permission_key=key, is_granted=granted)
            )
        await db.commit()


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeHttpClient:
    """Stand-in for ``httpx.AsyncClient`` capturing the single POST it receives."""

    captured: dict = {}
    status_sequence = [200]
    _call_index = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, content=None, headers=None):
        type(self).captured = {"url": url, "content": content, "headers": headers}
        idx = type(self)._call_index
        type(self)._call_index += 1
        seq = type(self).status_sequence
        return _FakeResponse(seq[min(idx, len(seq) - 1)])


# ---------------------------------------------------------------------------
# Session revocation (forced logout)
# ---------------------------------------------------------------------------
async def test_logout_revokes_token(client):
    _, token, _ = await register_user(client)
    headers = auth_headers(token)

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    out = await client.post("/api/v1/auth/logout", headers=headers, json={})
    assert out.status_code == 200

    # Same (still-unexpired) token must now be rejected.
    after = await client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401


async def test_refresh_after_logout_fails(client):
    _, token, refresh = await register_user(client)
    headers = auth_headers(token)

    # Refresh works before logout.
    pre = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert pre.status_code == 200, pre.text

    # Logout revokes both the access token and the supplied refresh token.
    out = await client.post(
        "/api/v1/auth/logout", headers=headers, json={"refresh_token": refresh}
    )
    assert out.status_code == 200

    post = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert post.status_code == 401


# ---------------------------------------------------------------------------
# Granular permissions
# ---------------------------------------------------------------------------
async def test_refund_denied_without_permission_then_granted(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    sale = await _sale(client, headers, pid, qty=1)

    # Explicit deny → 403.
    await _set_permission(user["id"], "pos.refund", granted=False)
    denied = await client.post(f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers)
    assert denied.status_code == 403
    assert "pos.refund" in denied.json()["detail"]

    # Grant → 200 (same sale was untouched by the rejected attempt).
    await _set_permission(user["id"], "pos.refund", granted=True)
    ok = await client.post(f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers)
    assert ok.status_code == 200, ok.text


async def test_me_permissions_endpoint(client):
    # Master bypasses everything. Re-login so the token carries the promoted
    # admin role (make_master_account issues the token before promoting).
    muser, _ = await make_master_account(client)
    login = await client.post(
        "/api/v1/auth/login", json={"email": muser["email"], "password": "Password123"}
    )
    mtoken = login.json()["token"]
    mresp = await client.get("/api/v1/auth/me/permissions", headers=auth_headers(mtoken))
    assert mresp.status_code == 200
    assert mresp.json()["is_master"] is True

    # A client with an explicit deny surfaces it so the UI can hide the action.
    user, token, _ = await make_client_account(client)
    await _set_permission(user["id"], "pos.refund", granted=False)
    cresp = await client.get("/api/v1/auth/me/permissions", headers=auth_headers(token))
    body = cresp.json()
    assert body["is_master"] is False
    assert "pos.refund" in body["denied"]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
async def test_rate_limit_returns_429(client, monkeypatch):
    from services.production import rate_limiter

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    # Drain-fast bucket: 2 tokens, no refill.
    monkeypatch.setattr(rate_limiter, "max_tokens", 2)
    monkeypatch.setattr(rate_limiter, "refill_rate", 0.0)
    monkeypatch.setattr(rate_limiter, "_buckets", {})

    r1 = await client.get("/health")
    r2 = await client.get("/health")
    r3 = await client.get("/health")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers


# ---------------------------------------------------------------------------
# Request validation (body-size cap)
# ---------------------------------------------------------------------------
async def test_oversized_body_rejected(client, monkeypatch):
    monkeypatch.setenv("MAX_BODY_SIZE_MB", "1")
    big = "x" * (1_500_000)  # ~1.5MB > 1MB cap
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "a@b.com", "password": big}
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------
def test_webhook_dispatch_signs_and_delivers(monkeypatch):
    _FakeHttpClient.captured = {}
    _FakeHttpClient.status_sequence = [200]
    _FakeHttpClient._call_index = 0
    monkeypatch.setattr(httpx, "AsyncClient", _FakeHttpClient)

    import asyncio

    secret = "topsecret"
    result = asyncio.run(
        WebhookDispatcher.dispatch(
            "https://example.test/hook", "sale.completed", {"a": 1}, secret
        )
    )
    assert result["status"] == "delivered"
    assert result["status_code"] == 200

    # The signature header is a valid HMAC-SHA256 of the exact posted body.
    body = _FakeHttpClient.captured["content"]
    sig_header = _FakeHttpClient.captured["headers"]["X-Webhook-Signature"]
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert sig_header == expected


def test_webhook_dispatch_retries_on_5xx(monkeypatch):
    _FakeHttpClient.captured = {}
    _FakeHttpClient.status_sequence = [500, 500, 200]  # two transient failures, then ok
    _FakeHttpClient._call_index = 0
    monkeypatch.setattr(httpx, "AsyncClient", _FakeHttpClient)

    import asyncio

    result = asyncio.run(
        WebhookDispatcher.dispatch("https://example.test/hook", "evt", {"x": 1}, "s")
    )
    assert result["status"] == "delivered"
    assert result["attempts"] == 3


async def test_webhook_fires_on_sale(client, monkeypatch):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)

    # Register a webhook subscribed to sale.completed for this user.
    async with db_manager.async_session_maker() as db:
        db.add(
            Webhooks(
                user_id=user["id"],
                client_id=client_id,
                name="hook",
                url="https://example.test/sale",
                events="sale.completed,sale.refunded",
                secret_key="sek",
                is_active=True,
            )
        )
        await db.commit()

    # Capture dispatches without hitting the network.
    fired = []

    async def _record(url, event, payload, secret):
        fired.append({"url": url, "event": event, "payload": payload})
        return {"status": "delivered"}

    monkeypatch.setattr(WebhookDispatcher, "dispatch", staticmethod(_record))

    await _sale(client, headers, pid)

    sale_events = [f for f in fired if f["event"] == "sale.completed"]
    assert len(sale_events) == 1
    assert sale_events[0]["url"] == "https://example.test/sale"
    assert sale_events[0]["payload"]["data"]["client_id"] == client_id


async def test_fire_event_skips_unsubscribed_and_inactive(client):
    user, token, client_id = await make_client_account(client)
    async with db_manager.async_session_maker() as db:
        db.add(Webhooks(user_id=user["id"], name="a", url="u1", events="other.event", is_active=True))
        db.add(Webhooks(user_id=user["id"], name="b", url="u2", events="sale.completed", is_active=False))
        await db.commit()

    sent = []

    async def _record(url, event, payload, secret):
        sent.append(url)

    import services.production as prod

    orig = prod.WebhookDispatcher.dispatch
    prod.WebhookDispatcher.dispatch = staticmethod(_record)
    try:
        async with db_manager.async_session_maker() as db:
            attempted = await fire_event(db, user["id"], "sale.completed", {"x": 1})
    finally:
        prod.WebhookDispatcher.dispatch = staticmethod(orig)

    # One row is for a different event, the other is inactive → nothing attempted.
    assert attempted == 0
    assert sent == []


# ---------------------------------------------------------------------------
# Email transport wiring
# ---------------------------------------------------------------------------
async def test_email_service_delegates_to_core_email(monkeypatch):
    import core.email as core_email
    from services.production import EmailService

    sent = {}

    async def _fake_send(to_email, subject, body):
        sent.update({"to": to_email, "subject": subject})
        return True  # simulate real SMTP delivery

    monkeypatch.setattr(core_email, "send_email", _fake_send)
    result = await EmailService.send_email("a@b.com", "Subject", "Body")
    assert result["status"] == "sent"
    assert result["delivered"] is True
    assert sent["to"] == "a@b.com"


async def test_email_service_dev_fallback_when_not_delivered(monkeypatch):
    import core.email as core_email
    from services.production import EmailService

    async def _fake_send(to_email, subject, body):
        return False  # dev fallback (no SMTP)

    monkeypatch.setattr(core_email, "send_email", _fake_send)
    result = await EmailService.send_email("a@b.com", "S", "B")
    assert result["status"] == "logged"
    assert result["delivered"] is False
