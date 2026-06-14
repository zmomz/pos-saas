"""ISSUE-066 — Retail modifiers/combos in catalog.

Modifiers/combos were built for the restaurant vertical and sit behind the
restaurant double-gate (``business_type`` ∈ restaurant/both + the ``restaurant``
feature). A *retail* merchant could not reach them at all. This slice surfaces
the same catalog primitives — modifier groups, modifiers, product↔group
attachment and combos — on a ``/api/v1/catalog`` surface that any client merchant
can use, regardless of business type, and makes a retail **combo** deduct its
component stock when it is sold through the POS (consistent with ISSUE-032).

The catch-forever behaviours:
* ``test_retail_merchant_can_build_modifiers_and_combos`` — a ``retail`` client
  (which the restaurant surface 403s) can create a group, add a modifier, attach
  the group to a product and define a combo through ``/api/v1/catalog``.
* ``test_retail_combo_sale_deducts_component_stock`` — selling a combo at the POS
  depletes each component product's stock by component-qty × line-qty.
"""
from conftest import add_product, auth_headers, get_product_quantity, make_client_account


async def _make_group(client, headers, *, name="Add-ons", required=False, min_select=0, max_select=2):
    return await client.post(
        "/api/v1/catalog/modifier-groups",
        json={
            "name": name,
            "name_ar": "إضافات",
            "required": required,
            "min_select": min_select,
            "max_select": max_select,
        },
        headers=headers,
    )


async def test_retail_merchant_can_create_modifier_group(client):
    """A retail merchant reaches the catalog modifier surface the restaurant gate blocks."""
    _user, token, _cid = await make_client_account(client, business_type="retail")
    headers = auth_headers(token)

    resp = await _make_group(client, headers, name="Gift wrap")
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Gift wrap"


async def test_retail_merchant_can_build_modifiers_and_combos(client):
    """A retail client can add a modifier, attach the group to a product, and define a combo."""
    user, token, cid = await make_client_account(client, business_type="retail")
    headers = auth_headers(token)
    pid = await add_product(cid, user["id"], name="Mug", price=20.0)
    comp_id = await add_product(cid, user["id"], name="Coaster", price=8.0)

    group_id = (await _make_group(client, headers, name="Add-ons")).json()["id"]

    # Add a modifier to the group.
    mod = await client.post(
        f"/api/v1/catalog/modifier-groups/{group_id}/modifiers",
        json={"name": "Bigger size", "name_ar": "حجم أكبر", "price_delta": 5.0},
        headers=headers,
    )
    assert mod.status_code == 201, mod.text

    # Attach the group to the product; it surfaces on the product's group list.
    attach = await client.post(
        f"/api/v1/catalog/products/{pid}/modifier-groups/{group_id}", headers=headers
    )
    assert attach.status_code == 201, attach.text
    listed = await client.get(
        f"/api/v1/catalog/products/{pid}/modifier-groups", headers=headers
    )
    groups = listed.json()["items"]
    assert [g["id"] for g in groups] == [group_id]
    assert groups[0]["modifiers"][0]["name"] == "Bigger size"

    # Define a combo (bundle price overrides the component sum).
    combo = await client.post(
        "/api/v1/catalog/combos",
        json={
            "name": "Mug + Coaster",
            "name_ar": "كوب وقاعدة",
            "bundle_price": 25.0,
            "components": [{"product_id": pid, "qty": 1}, {"product_id": comp_id, "qty": 1}],
        },
        headers=headers,
    )
    assert combo.status_code == 201, combo.text
    body = combo.json()
    assert body["bundle_price"] == 25.0
    assert body["component_sum"] == 28.0  # 20 + 8 catalog prices, overridden by the bundle


async def test_catalog_entities_are_owner_scoped(client):
    """A second merchant cannot see or mutate the first's catalog rows (SEC-02)."""
    _u1, token1, _c1 = await make_client_account(client, business_type="retail")
    group_id = (await _make_group(client, auth_headers(token1))).json()["id"]

    _u2, token2, _c2 = await make_client_account(client, business_type="retail")
    # The intruder's listing is empty and a delete of the victim's group 404s.
    seen = await client.get("/api/v1/catalog/modifier-groups", headers=auth_headers(token2))
    assert seen.json() == []
    denied = await client.delete(
        f"/api/v1/catalog/modifier-groups/{group_id}", headers=auth_headers(token2)
    )
    assert denied.status_code == 404


async def test_retail_combo_sale_deducts_component_stock(client):
    """Selling a combo at the POS depletes each component's stock (ISSUE-032 parity)."""
    user, token, cid = await make_client_account(client, business_type="retail")
    headers = auth_headers(token)
    burger = await add_product(cid, user["id"], name="Burger", price=20.0, quantity=10)
    fries = await add_product(cid, user["id"], name="Fries", price=8.0, quantity=10)

    combo_id = (
        await client.post(
            "/api/v1/catalog/combos",
            json={
                "name": "Meal deal",
                "bundle_price": 25.0,
                "components": [
                    {"product_id": burger, "qty": 1},
                    {"product_id": fries, "qty": 2},
                ],
            },
            headers=headers,
        )
    ).json()["id"]

    # Sell 3 of the combo through the POS.
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [
                {"combo_id": combo_id, "name": "Meal deal", "price": 25.0, "quantity": 3}
            ],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text

    # Each component was depleted by component-qty × line-qty.
    assert await get_product_quantity(burger) == 10 - 1 * 3  # 7
    assert await get_product_quantity(fries) == 10 - 2 * 3  # 4
