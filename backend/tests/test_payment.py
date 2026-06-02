"""Payment router is wired and fails gracefully when Stripe isn't configured."""
from conftest import auth_headers, register_user


async def test_checkout_requires_stripe_configuration(client):
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
    # No STRIPE_SECRET_KEY in the test env -> 503, not a 500.
    assert resp.status_code == 503, resp.text


async def test_payment_endpoint_requires_auth(client):
    resp = await client.get("/api/v1/payments/status/sess_123")
    assert resp.status_code == 401
