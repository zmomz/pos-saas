"""Phase 4 — Pricing & discounts server-side enforcement (PRC-01, F-040).

Before F-040 the POS trusted a client-computed ``discount_amount`` and never
validated a discount code, never enforced ``max_uses``, and never incremented
``usage_count`` — so caps were unenforceable and the amount was forgeable.

These tests prove the closed gaps:

* ``POST /entities/discounts/validate`` is the server-authoritative price for a
  code (and rejects below ``min_purchase``);
* a coded discount on a sale is priced from the *rule*, ignoring any client
  ``discount_amount``;
* ``max_uses=1`` is rejected on the second sale and ``usage_count`` increments
  exactly once per applied sale;
* a manual (codeless) ``discount_amount`` requires the ``pos.discount``
  permission (deny-wins).
"""
import uuid

from sqlalchemy import select

from conftest import (
    add_product,
    auth_headers,
    make_client_account,
)
from core.database import db_manager
from models.discounts import Discounts
from models.permissions import Permissions


async def _create_discount(client, headers, *, code, type="percentage", value=10.0,
                           min_purchase=None, max_uses=None):
    # The generated DiscountsData schema rejects an explicit null for the optional
    # numeric fields, so only send the keys that are set.
    body = {"code": code, "type": type, "value": value, "is_active": True}
    if min_purchase is not None:
        body["min_purchase"] = min_purchase
    if max_uses is not None:
        body["max_uses"] = max_uses
    resp = await client.post(
        "/api/v1/entities/discounts", json=body, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _sale(client, headers, pid, *, price=50.0, qty=2, discount_code=None,
                discount_amount=None):
    body = {
        "items": [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}],
        "payment_method": "cash",
    }
    if discount_code is not None:
        body["discount_code"] = discount_code
    if discount_amount is not None:
        body["discount_amount"] = discount_amount
    return await client.post("/api/v1/pos/transaction", json=body, headers=headers)


async def _usage_count(code: str, user_id: str) -> int:
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Discounts).where(
                    Discounts.code == code, Discounts.user_id == str(user_id)
                )
            )
        ).scalar_one()
        return row.usage_count or 0


# ---------------------------------------------------------------------------
# Validate endpoint: server-authoritative amount + min-purchase floor
# ---------------------------------------------------------------------------
async def test_validate_endpoint_returns_server_amount(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    code = f"SAVE10_{uuid.uuid4().hex[:6]}"
    await _create_discount(client, headers, code=code, type="percentage", value=10.0)

    resp = await client.post(
        "/api/v1/entities/discounts/validate",
        json={"code": code, "subtotal": 100.0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert abs(body["discount_amount"] - 10.0) < 0.01


async def test_validate_rejects_below_min_purchase(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    code = f"MIN50_{uuid.uuid4().hex[:6]}"
    await _create_discount(client, headers, code=code, type="fixed", value=5.0,
                           min_purchase=50.0)

    resp = await client.post(
        "/api/v1/entities/discounts/validate",
        json={"code": code, "subtotal": 20.0},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


async def test_validate_rejects_unknown_code(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    resp = await client.post(
        "/api/v1/entities/discounts/validate",
        json={"code": "NOPE", "subtotal": 100.0},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# Coded discount on a sale is priced from the rule (client amount ignored)
# ---------------------------------------------------------------------------
async def test_coded_discount_is_server_priced_and_ignores_client_amount(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=50.0)
    code = f"FLAT5_{uuid.uuid4().hex[:6]}"
    await _create_discount(client, headers, code=code, type="fixed", value=5.0)

    # Subtotal is 100; the client lies and claims a 999 discount.
    resp = await _sale(client, headers, pid, discount_code=code, discount_amount=999.0)
    assert resp.status_code == 200, resp.text
    # Server prices the discount from the rule: a flat 5, never the forged 999.
    assert abs(resp.json()["discount_amount"] - 5.0) < 0.01


# ---------------------------------------------------------------------------
# Usage caps (the named "catch forever" test)
# ---------------------------------------------------------------------------
async def test_max_uses_one_discount_rejected_on_second_sale(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=50.0)
    code = f"ONCE_{uuid.uuid4().hex[:6]}"
    await _create_discount(client, headers, code=code, type="percentage", value=10.0,
                           max_uses=1)

    first = await _sale(client, headers, pid, discount_code=code)
    assert first.status_code == 200, first.text
    assert abs(first.json()["discount_amount"] - 10.0) < 0.01

    second = await _sale(client, headers, pid, discount_code=code)
    assert second.status_code == 400, second.text

    # The cap consumed exactly one use, even though a second sale was attempted.
    assert await _usage_count(code, user["id"]) == 1


async def test_usage_count_increments_once_per_applied_sale(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=50.0)
    code = f"FIVE_{uuid.uuid4().hex[:6]}"
    await _create_discount(client, headers, code=code, type="percentage", value=10.0,
                           max_uses=5)

    for _ in range(3):
        resp = await _sale(client, headers, pid, discount_code=code)
        assert resp.status_code == 200, resp.text

    assert await _usage_count(code, user["id"]) == 3


# ---------------------------------------------------------------------------
# Manual (codeless) discount is permissioned (pos.discount, deny-wins)
# ---------------------------------------------------------------------------
async def test_manual_discount_allowed_by_default(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=50.0)

    # No deny row → the account owner can apply a manual discount.
    resp = await _sale(client, headers, pid, discount_amount=7.0)
    assert resp.status_code == 200, resp.text
    assert abs(resp.json()["discount_amount"] - 7.0) < 0.01


async def test_manual_discount_denied_without_permission(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=50.0)

    # Explicitly deny pos.discount for this user.
    async with db_manager.async_session_maker() as db:
        db.add(
            Permissions(
                user_id=user["id"],
                role="client",
                permission_key="pos.discount",
                is_granted=False,
            )
        )
        await db.commit()

    resp = await _sale(client, headers, pid, discount_amount=7.0)
    assert resp.status_code == 403, resp.text

    # A codeless sale with no discount still works (the gate only fires on a
    # non-zero manual amount).
    ok = await _sale(client, headers, pid)
    assert ok.status_code == 200, ok.text
