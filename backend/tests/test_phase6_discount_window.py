"""Phase 6 — PRC-02 scheduled validity window on discount/promo codes (F-041, first slice).

A coupon/promo code can now carry a validity window (``starts_at`` / ``ends_at``).
The server-side validator — the single source of truth wired into both the
``/validate`` preview and the atomic sale path — honours the window: a code whose
window has not started is "not active yet", one past its window has "expired", and
only a code whose window straddles "now" applies. Either bound NULL ⇒ open-ended on
that side (a plain always-on code keeps working unchanged).

Catches forever (per COMPLETENESS_REVIEW F-041 / PRC-02):
* a sale with an expired code is rejected (400) and no use is consumed;
* a sale with a not-yet-active code is rejected (400);
* a sale with an in-window code applies the discount and prices it server-side;
* the window bounds round-trip through the discount CRUD;
* boundary semantics on the validator itself (inclusive start, inclusive end).
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.discounts import Discounts
from services.discounts import DiscountsService, DiscountValidationError


# Fixed far-apart bounds make the window unambiguous regardless of the wall clock.
FAR_PAST = "2000-01-01T00:00:00"
FAR_FUTURE = "2999-01-01T00:00:00"


async def _create_discount(client, headers, **fields):
    payload = {"code": fields.pop("code"), "type": "percentage", "value": 10.0, "is_active": True}
    payload.update(fields)
    resp = await client.post("/api/v1/entities/discounts", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _usage_count(discount_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Discounts.usage_count).where(Discounts.id == discount_id))
        ).scalar_one() or 0


# ---------------------------------------------------------------------------
# The window bounds round-trip through the CRUD triad.
# ---------------------------------------------------------------------------
async def test_discount_window_round_trips(client):
    _, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    created = await _create_discount(
        client, headers, code="SUMMER", starts_at=FAR_PAST, ends_at=FAR_FUTURE
    )
    assert created["starts_at"] is not None
    assert created["ends_at"] is not None


# ---------------------------------------------------------------------------
# A sale with an expired code is rejected and consumes no use.
# ---------------------------------------------------------------------------
async def test_expired_code_blocks_sale_and_consumes_no_use(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)
    disc = await _create_discount(
        client, headers, code="EXPIRED", starts_at=FAR_PAST, ends_at=FAR_PAST
    )

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "discount_code": "EXPIRED",
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "expired" in resp.json()["detail"].lower()
    # The rejected sale spent no use.
    assert await _usage_count(disc["id"]) == 0


# ---------------------------------------------------------------------------
# A sale with a not-yet-active code is rejected.
# ---------------------------------------------------------------------------
async def test_not_yet_active_code_blocks_sale(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)
    await _create_discount(
        client, headers, code="SOON", starts_at=FAR_FUTURE, ends_at=FAR_FUTURE
    )

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "discount_code": "SOON",
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "not active yet" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# A sale with an in-window code applies the discount, priced server-side.
# ---------------------------------------------------------------------------
async def test_in_window_code_applies_discount(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)
    disc = await _create_discount(
        client, headers, code="NOW10", starts_at=FAR_PAST, ends_at=FAR_FUTURE
    )

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "discount_code": "NOW10",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 10% of the 100 subtotal, priced from the rule (never client-trusted).
    assert abs(body["discount_amount"] - 10.0) < 0.01
    # VAT is on the post-discount taxable base (90 * 15%).
    assert abs(body["vat_amount"] - 13.5) < 0.01
    # The in-window sale consumed exactly one use.
    assert await _usage_count(disc["id"]) == 1


# ---------------------------------------------------------------------------
# Boundary semantics on the validator itself (deterministic injected ``now``).
# ---------------------------------------------------------------------------
async def test_validator_window_boundaries_are_inclusive(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _create_discount(
        client,
        headers,
        code="WINDOW",
        starts_at="2026-06-01T00:00:00",
        ends_at="2026-06-30T23:59:59",
    )

    async with db_manager.async_session_maker() as db:
        service = DiscountsService(db)

        # Inside the window → valid.
        ok = await service.validate(
            "WINDOW", 100.0, user_id=str(user["id"]), now=datetime(2026, 6, 15, 12, 0, 0)
        )
        assert ok.code == "WINDOW"

        # Exactly at the start bound is inclusive.
        ok_start = await service.validate(
            "WINDOW", 100.0, user_id=str(user["id"]), now=datetime(2026, 6, 1, 0, 0, 0)
        )
        assert ok_start.code == "WINDOW"

        # Before the window → not active yet.
        with pytest.raises(DiscountValidationError):
            await service.validate(
                "WINDOW", 100.0, user_id=str(user["id"]), now=datetime(2026, 5, 31, 23, 59, 59)
            )

        # After the window → expired.
        with pytest.raises(DiscountValidationError):
            await service.validate(
                "WINDOW", 100.0, user_id=str(user["id"]), now=datetime(2026, 7, 1, 0, 0, 1)
            )
