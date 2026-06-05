"""F-006 — the orphaned Stripe Checkout router (`routers/payment.py`) is removed.

The generic Stripe Checkout endpoints (`POST /api/v1/payments/checkout`,
`GET /api/v1/payments/status/{session_id}`) had **no frontend caller** — the
subscription flow charges through the `tenant.py` Stripe Connect path, and the
Saudi-real payment stack is Moyasar/Geidea (F-001/F-002/F-005), not Stripe
Checkout. The dead surface shared the `/api/v1/payments` prefix with the real
gateway router, so removing it also clears that collision. These tests lock the
removal in: re-mounting the orphan would fail the first two, and accidentally
deleting the live gateway surface alongside it would fail the third.
"""
from conftest import auth_headers, register_user


async def test_orphaned_stripe_checkout_endpoint_is_removed(client):
    _, token, _ = await register_user(client)
    resp = await client.post(
        "/api/v1/payments/checkout",
        json={
            "amount": "10.00",
            "currency": "usd",
            "mode": "payment",
            "ui_mode": "hosted",
            "success_url": "https://x.test/s?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": "https://x.test/c",
        },
        headers=auth_headers(token),
    )
    # The route no longer exists -> 404 (it previously answered 503).
    assert resp.status_code == 404, resp.text


async def test_orphaned_stripe_checkout_status_endpoint_is_removed(client):
    resp = await client.get("/api/v1/payments/status/sess_123")
    # The route no longer exists -> 404 (it previously answered 401).
    assert resp.status_code == 404, resp.text


async def test_real_saudi_gateway_surface_still_mounted(client):
    """Removing the orphan must not disturb the live `/api/v1/payments` gateway."""
    _, token, _ = await register_user(client)
    resp = await client.get(
        "/api/v1/payments/tender-types", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The Saudi tender taxonomy that drives the POS picker is still served.
    assert "mada" in body["tender_types"]
