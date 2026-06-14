"""F-062 — Composite / recipe BOM depletion.

A restaurant manager defines a **bill of materials**: a parent product (a dish or a
bundle SKU) made of component products each with a **qty-per**. Selling a BOM-backed
line expands the parent into ``qty_per × qty_sold`` deductions of every component,
and that expansion happens **inside the same atomic stock transaction as the sale**
— so a failed sale never leaves a partial component deduction. Component costs roll
up to a true cost-of-goods value on the parent (the hook F-068 later reports on).

Catches forever (per the slice F-062):
* selling a BOM-backed product depletes each component by ``qty_per × qty_sold``;
* a depletion that would oversell a component (without overdraft) is rejected and
  leaves NO partial component deduction (atomic);
* component costs roll up to a cost-of-goods value on the parent;
* the BOM entities + depletion are owner-scoped (SEC-02) and behind the double-gate.

Depletion is owned by the **single atomic settle path** (F-059): settling a ticket
mints the fiscal sale and deducts every recipe component exactly once, in the same
transaction. There is deliberately no standalone ``/deplete-stock`` endpoint — a
second depletion path deducted the very same components the settle already deducts,
double-counting every recipe component per sale (ISSUE-104, U4.1). These tests
therefore exercise depletion through ``…/settle``, the path a real sale takes.
"""
from sqlalchemy import select

from conftest import add_product, auth_headers, get_product_quantity, make_client_account
from core.database import db_manager
from models.clients import Clients


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _make_table(client, token, name="T1"):
    return (
        await client.post(
            "/api/v1/restaurant/tables",
            json={"name": name, "seats": 4},
            headers=auth_headers(token),
        )
    ).json()["id"]


async def _open_dine_in(client, token, table_id):
    return (
        await client.post(
            "/api/v1/restaurant/order-tickets",
            json={"order_type": "dine_in", "table_id": table_id},
            headers=auth_headers(token),
        )
    ).json()["id"]


async def _add_line(client, token, ticket_id, product_id, qty=1):
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": product_id, "qty": qty},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_bom(client, token, parent_id, component_id, qty_per):
    resp = await client.post(
        f"/api/v1/restaurant/products/{parent_id}/bom",
        json={"component_product_id": component_id, "qty_per": qty_per},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _settle(client, token, ticket_id, *, allow_negative_stock=False):
    """Settle a ticket for cash through the one atomic sale path (F-059).

    This is the sole BOM-depletion path: it deducts every recipe component exactly
    once, in the same transaction as the fiscal sale. Returns the raw response so a
    test can assert a shortfall (400) or a successful depletion (200)."""
    return await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash", "allow_negative_stock": allow_negative_stock},
        headers=auth_headers(token),
    )


# ---------------------------------------------------------------------------
# Named slice test: selling a BOM-backed product depletes its components.
# ---------------------------------------------------------------------------
async def test_bom_sale_depletes_components(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    table_id = await _make_table(client, token, name="B1")
    ticket_id = await _open_dine_in(client, token, table_id)

    # A "Cheeseburger" dish made of 1 bun + 0.2 (kg) beef patty.
    burger = await add_product(client_id, user["id"], name="Cheeseburger", quantity=50, price=30.0)
    bun = await add_product(client_id, user["id"], name="Bun", quantity=100, price=1.0)
    beef = await add_product(client_id, user["id"], name="Beef", quantity=10.0, price=5.0)
    await _add_bom(client, token, burger, bun, qty_per=1)
    await _add_bom(client, token, burger, beef, qty_per=0.2)

    # Sell 3 burgers and settle.
    await _add_line(client, token, ticket_id, burger, qty=3)
    resp = await _settle(client, token, ticket_id)
    assert resp.status_code == 200, resp.text

    # The finished line and each component deduct exactly once: 3 burgers off the
    # parent, qty_per × 3 off each component.
    assert await get_product_quantity(burger) == 50 - 3
    assert await get_product_quantity(bun) == 100 - 3 * 1
    assert abs(await get_product_quantity(beef) - (10.0 - 3 * 0.2)) < 0.001


# ---------------------------------------------------------------------------
# A component shared across two BOM-backed lines aggregates its deduction.
# ---------------------------------------------------------------------------
async def test_shared_component_deduction_aggregates(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    table_id = await _make_table(client, token, name="B2")
    ticket_id = await _open_dine_in(client, token, table_id)

    cheese = await add_product(client_id, user["id"], name="Cheese", quantity=100, price=2.0)
    burger = await add_product(client_id, user["id"], name="Burger", quantity=10, price=30.0)
    pizza = await add_product(client_id, user["id"], name="Pizza", quantity=10, price=40.0)
    await _add_bom(client, token, burger, cheese, qty_per=1)
    await _add_bom(client, token, pizza, cheese, qty_per=3)

    await _add_line(client, token, ticket_id, burger, qty=2)  # 2 cheese
    await _add_line(client, token, ticket_id, pizza, qty=1)   # 3 cheese

    resp = await _settle(client, token, ticket_id)
    assert resp.status_code == 200, resp.text
    # The shared component aggregates across both lines and deducts once: 2 + 3 = 5.
    assert await get_product_quantity(cheese) == 100 - (2 * 1 + 1 * 3)


# ---------------------------------------------------------------------------
# Atomic: a shortfall on one component leaves NO partial deduction.
# ---------------------------------------------------------------------------
async def test_insufficient_component_leaves_no_partial_deduction(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    table_id = await _make_table(client, token, name="B3")
    ticket_id = await _open_dine_in(client, token, table_id)

    # The parent is stocked plentifully so the ONLY shortfall is the component.
    dish = await add_product(client_id, user["id"], name="Combo Plate", quantity=1000, price=50.0)
    plenty = await add_product(client_id, user["id"], name="Rice", quantity=100, price=1.0)
    scarce = await add_product(client_id, user["id"], name="Lobster", quantity=1, price=80.0)
    await _add_bom(client, token, dish, plenty, qty_per=1)
    await _add_bom(client, token, dish, scarce, qty_per=1)

    # Sell 5 — only 1 lobster on hand → the whole sale must fail.
    await _add_line(client, token, ticket_id, dish, qty=5)
    resp = await _settle(client, token, ticket_id)
    assert resp.status_code == 400, resp.text

    # Nothing moved — no partial deduction (atomic with the sale): not the other
    # component, and not the parent line either.
    assert await get_product_quantity(plenty) == 100
    assert await get_product_quantity(scarce) == 1
    assert await get_product_quantity(dish) == 1000


# ---------------------------------------------------------------------------
# allow_negative_stock lets the depletion oversell (e.g. count later).
# ---------------------------------------------------------------------------
async def test_depletion_allows_negative_stock_when_requested(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    table_id = await _make_table(client, token, name="B4")
    ticket_id = await _open_dine_in(client, token, table_id)

    dish = await add_product(client_id, user["id"], name="Soup", quantity=0, price=20.0)
    stock = await add_product(client_id, user["id"], name="Broth", quantity=2, price=1.0)
    await _add_bom(client, token, dish, stock, qty_per=1)
    await _add_line(client, token, ticket_id, dish, qty=5)

    resp = await _settle(client, token, ticket_id, allow_negative_stock=True)
    assert resp.status_code == 200, resp.text
    assert await get_product_quantity(stock) == 2 - 5  # -3, overdraft allowed


# ---------------------------------------------------------------------------
# Component costs roll up to a cost-of-goods value on the parent (F-068 hook).
# ---------------------------------------------------------------------------
async def test_component_costs_roll_up_to_parent_cogs(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")

    burger = await add_product(client_id, user["id"], name="Burger", quantity=0, price=30.0)
    bun = await add_product(client_id, user["id"], name="Bun", quantity=100, price=1.0, cost_price=0.5)
    beef = await add_product(client_id, user["id"], name="Beef", quantity=10, price=5.0, cost_price=4.0)
    await _add_bom(client, token, burger, bun, qty_per=1)
    await _add_bom(client, token, burger, beef, qty_per=0.25)

    resp = await client.get(
        f"/api/v1/restaurant/products/{burger}/bom", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    # COGS = 1×0.5 + 0.25×4.0 = 1.5
    assert abs(body["cost_of_goods"] - 1.5) < 0.001


# ---------------------------------------------------------------------------
# Validation: self-component and non-positive qty-per are rejected.
# ---------------------------------------------------------------------------
async def test_self_component_rejected(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    pid = await add_product(client_id, user["id"], name="Thing", quantity=5, price=10.0)
    resp = await client.post(
        f"/api/v1/restaurant/products/{pid}/bom",
        json={"component_product_id": pid, "qty_per": 1},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text


async def test_non_positive_qty_per_rejected(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    parent = await add_product(client_id, user["id"], name="Dish", quantity=0, price=10.0)
    comp = await add_product(client_id, user["id"], name="Ingredient", quantity=5, price=2.0)
    resp = await client.post(
        f"/api/v1/restaurant/products/{parent}/bom",
        json={"component_product_id": comp, "qty_per": 0},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text


async def test_bom_unknown_component_404(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    parent = await add_product(client_id, user["id"], name="Dish", quantity=0, price=10.0)
    resp = await client.post(
        f"/api/v1/restaurant/products/{parent}/bom",
        json={"component_product_id": 999999, "qty_per": 1},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Owner scoping (SEC-02) and the restaurant double-gate.
# ---------------------------------------------------------------------------
async def test_bom_owner_scoped(client):
    u1, token1, c1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _c2 = await make_client_account(client, business_type="restaurant")

    parent = await add_product(c1, u1["id"], name="Dish", quantity=0, price=10.0)
    comp = await add_product(c1, u1["id"], name="Ingredient", quantity=5, price=2.0)
    await _add_bom(client, token1, parent, comp, qty_per=1)

    # A second client cannot read the first client's product BOM rows.
    resp = await client.get(
        f"/api/v1/restaurant/products/{parent}/bom", headers=auth_headers(token2)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


async def test_bom_requires_restaurant_business_type(client):
    user, token, client_id = await make_client_account(client, business_type="retail")
    pid = await add_product(client_id, user["id"], name="Thing", quantity=5, price=10.0)
    resp = await client.get(
        f"/api/v1/restaurant/products/{pid}/bom", headers=auth_headers(token)
    )
    assert resp.status_code == 403, resp.text
