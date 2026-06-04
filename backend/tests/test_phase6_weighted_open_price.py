"""Phase 6 — Weighted & open-price items (POS-11, F-011).

Before F-011 a cart line carried an integer ``quantity`` and the POS could not
sell a product by fractional weight or accept a sale-time price; an open-price
product's price entry also tripped the ``pos.price_override`` fraud gate (POS-08).

These tests pin the closed gap:

* a **weighted** line with a fractional quantity prices ``price × quantity`` and
  deducts the fractional amount from stock;
* an **open-price** product accepts a sale-time price WITHOUT the
  ``pos.price_override`` permission (price entry is expected by design);
* a **fixed-price** product still requires ``pos.price_override`` to change its
  unit price (the F-013 fraud gate is preserved).
"""
import uuid

from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.permissions import Permissions
from models.products import Products


async def _add_product(
    client_id: int,
    user_id: str,
    *,
    name: str = "Apples",
    price: float = 20.0,
    quantity: float = 12.5,
    is_weighted: bool = False,
    is_open_price: bool = False,
    unit_label: str | None = None,
) -> int:
    async with db_manager.async_session_maker() as db:
        product = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=price,
            quantity=quantity,
            is_weighted=is_weighted,
            is_open_price=is_open_price,
            unit_label=unit_label,
            is_active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product.id


async def _on_hand(pid: int) -> float:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Products.quantity).where(Products.id == pid))
        ).scalar_one()


async def _deny(user_id: str, key: str) -> None:
    async with db_manager.async_session_maker() as db:
        db.add(
            Permissions(
                user_id=user_id, role="client", permission_key=key, is_granted=False
            )
        )
        await db.commit()


async def _sale(client, headers, pid, *, price, qty):
    body = {
        "items": [
            {"product_id": pid, "name": "Apples", "price": price, "quantity": qty}
        ],
        "payment_method": "cash",
    }
    return await client.post("/api/v1/pos/transaction", json=body, headers=headers)


# ---------------------------------------------------------------------------
# Weighted: fractional quantity prices price × quantity and deducts fractionally
# ---------------------------------------------------------------------------
async def test_weighted_line_subtotal_is_price_times_fractional_quantity(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    # 20.00 / kg, 12.5 kg on hand.
    pid = await _add_product(
        client_id, user["id"], price=20.0, quantity=12.5,
        is_weighted=True, unit_label="kg",
    )

    resp = await _sale(client, headers, pid, price=20.0, qty=0.45)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 20.00 × 0.45 = 9.00
    assert abs(body["subtotal"] - 9.0) < 0.001, body

    # Stock deducted by the fractional amount sold: 12.5 - 0.45 = 12.05
    assert abs(await _on_hand(pid) - 12.05) < 0.001


# ---------------------------------------------------------------------------
# Open-price: a sale-time price is NOT a permissioned override
# ---------------------------------------------------------------------------
async def test_open_price_product_accepts_sale_time_price_without_override_permission(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    # Open-price product: catalog price is a placeholder; price entered at sale.
    pid = await _add_product(
        client_id, user["id"], name="Misc", price=0.0, quantity=100,
        is_open_price=True,
    )
    # Even with the override permission explicitly denied, an open-price line is
    # accepted because a sale-time price is expected by design.
    await _deny(user["id"], "pos.price_override")

    resp = await _sale(client, headers, pid, price=17.5, qty=1)
    assert resp.status_code == 200, resp.text
    assert abs(resp.json()["subtotal"] - 17.5) < 0.001


# ---------------------------------------------------------------------------
# Fixed-price: changing the unit price still requires pos.price_override (F-013)
# ---------------------------------------------------------------------------
async def test_fixed_price_product_still_requires_price_override_permission(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await _add_product(
        client_id, user["id"], name="Widget", price=50.0, quantity=100,
        is_open_price=False,
    )
    await _deny(user["id"], "pos.price_override")

    # 40.00 differs from the catalog 50.00 on a fixed-price product → gated.
    resp = await _sale(client, headers, pid, price=40.0, qty=1)
    assert resp.status_code == 403, resp.text

    # The same line at the catalog price is fine (no override).
    ok = await _sale(client, headers, pid, price=50.0, qty=1)
    assert ok.status_code == 200, ok.text
