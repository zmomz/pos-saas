"""F-056 — Modifiers, modifier groups & combos.

Drives the menu-expressiveness slice over HTTP (the real ASGI app):

* a manager defines a modifier group (required + min/max) with bilingual
  modifiers carrying price deltas, and attaches the group to a product;
* adding the product with an unsatisfied *required* group is rejected, and
  satisfying it succeeds with the deltas folded into the line total before VAT;
* a combo's bundle price overrides the sum of its components' catalog prices,
  and adding the combo to a ticket prices the line at the bundle price;
* the selected modifiers are persisted on the line (the kitchen-ticket payload);
* every new entity is owner-scoped (SEC-02) and behind the restaurant gate.

The named "catch-forever" tests required by the slice are
``test_required_modifier_group_enforced`` and
``test_combo_price_overrides_component_sum``.
"""
import json

from conftest import add_product, auth_headers, make_client_account


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _open_ticket(client, token, table_name="T1"):
    """Create a table and open an order on it; return (table_id, ticket_id)."""
    headers = auth_headers(token)
    table_id = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": table_name, "seats": 4}, headers=headers
        )
    ).json()["id"]
    ticket_id = (
        await client.post(
            f"/api/v1/restaurant/tables/{table_id}/open-order",
            json={"order_type": "dine_in", "party_size": 2},
            headers=headers,
        )
    ).json()["id"]
    return table_id, ticket_id


async def _make_group(client, headers, *, name="Doneness", required=True, min_select=1, max_select=1):
    return (
        await client.post(
            "/api/v1/restaurant/modifier-groups",
            json={
                "name": name,
                "name_ar": "الاستواء",
                "required": required,
                "min_select": min_select,
                "max_select": max_select,
            },
            headers=headers,
        )
    ).json()["id"]


async def _add_modifier(client, headers, group_id, *, name="Extra cheese", price_delta=5.0):
    return (
        await client.post(
            f"/api/v1/restaurant/modifier-groups/{group_id}/modifiers",
            json={"name": name, "name_ar": "جبنة إضافية", "price_delta": price_delta},
            headers=headers,
        )
    ).json()["id"]


# ---------------------------------------------------------------------------
# Modifier-group / modifier CRUD.
# ---------------------------------------------------------------------------
async def test_define_group_modifiers_and_attach_to_product(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Burger", price=30.0)

    group_id = await _make_group(client, headers, name="Add-ons", required=False, min_select=0, max_select=2)
    mod_id = await _add_modifier(client, headers, group_id, name="Bacon", price_delta=7.0)

    # Modifier is listed under its group.
    mods = await client.get(
        f"/api/v1/restaurant/modifier-groups/{group_id}/modifiers", headers=headers
    )
    assert mods.status_code == 200
    assert [m["id"] for m in mods.json()] == [mod_id]

    # Attach the group to the product; it surfaces on the product's group list.
    attach = await client.post(
        f"/api/v1/restaurant/products/{pid}/modifier-groups/{group_id}", headers=headers
    )
    assert attach.status_code == 201, attach.text
    listed = await client.get(
        f"/api/v1/restaurant/products/{pid}/modifier-groups", headers=headers
    )
    groups = listed.json()["items"]
    assert len(groups) == 1
    assert groups[0]["id"] == group_id
    assert groups[0]["modifiers"][0]["name"] == "Bacon"
    assert groups[0]["modifiers"][0]["price_delta"] == 7.0


# ---------------------------------------------------------------------------
# Named slice test: a required modifier group is enforced.
# ---------------------------------------------------------------------------
async def test_required_modifier_group_enforced(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Steak", price=80.0)
    _tbl, ticket_id = await _open_ticket(client, token)

    group_id = await _make_group(client, headers, required=True, min_select=1, max_select=1)
    rare = await _add_modifier(client, headers, group_id, name="Rare", price_delta=0.0)
    await _add_modifier(client, headers, group_id, name="Well done", price_delta=0.0)
    await client.post(
        f"/api/v1/restaurant/products/{pid}/modifier-groups/{group_id}", headers=headers
    )

    # Adding the item WITHOUT satisfying the required group is rejected.
    blocked = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains"},
        headers=headers,
    )
    assert blocked.status_code == 400, blocked.text
    assert "required" in blocked.json()["detail"].lower()

    # Satisfying it succeeds.
    ok = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains", "modifiers": [rare]},
        headers=headers,
    )
    assert ok.status_code == 201, ok.text


async def test_max_select_exceeded_is_rejected(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Pizza", price=40.0)
    _tbl, ticket_id = await _open_ticket(client, token)

    group_id = await _make_group(client, headers, name="Toppings", required=False, min_select=0, max_select=1)
    m1 = await _add_modifier(client, headers, group_id, name="Olives", price_delta=3.0)
    m2 = await _add_modifier(client, headers, group_id, name="Mushrooms", price_delta=3.0)
    await client.post(
        f"/api/v1/restaurant/products/{pid}/modifier-groups/{group_id}", headers=headers
    )

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "modifiers": [m1, m2]},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "at most" in resp.json()["detail"].lower()


async def test_modifier_delta_in_line_total_before_vat(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Burger", price=30.0)
    _tbl, ticket_id = await _open_ticket(client, token)

    group_id = await _make_group(client, headers, name="Add-ons", required=False, min_select=0, max_select=3)
    cheese = await _add_modifier(client, headers, group_id, name="Extra cheese", price_delta=5.0)
    bacon = await _add_modifier(client, headers, group_id, name="Bacon", price_delta=7.0)
    await client.post(
        f"/api/v1/restaurant/products/{pid}/modifier-groups/{group_id}", headers=headers
    )

    # qty 2 × 30 = 60, plus 5 + 7 (added once, per the line-math contract) = 72.
    line = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 2, "modifiers": [cheese, bacon]},
        headers=headers,
    )
    assert line.status_code == 201, line.text
    body = line.json()
    assert body["line_total"] == 72.0
    # The selected modifiers are persisted on the line (kitchen-ticket payload).
    persisted = json.loads(body["modifiers"])
    assert {m["name"] for m in persisted} == {"Extra cheese", "Bacon"}


# ---------------------------------------------------------------------------
# Named slice test: a combo's bundle price overrides the component sum.
# ---------------------------------------------------------------------------
async def test_combo_price_overrides_component_sum(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    burger = await add_product(cid, _user["id"], name="Burger", price=30.0)
    fries = await add_product(cid, _user["id"], name="Fries", price=12.0)
    drink = await add_product(cid, _user["id"], name="Cola", price=8.0)
    # Components sum to 50; the bundle sells for 39.
    combo = await client.post(
        "/api/v1/restaurant/combos",
        json={
            "name": "Meal Deal",
            "name_ar": "وجبة",
            "bundle_price": 39.0,
            "components": [
                {"product_id": burger, "qty": 1},
                {"product_id": fries, "qty": 1},
                {"product_id": drink, "qty": 1},
            ],
        },
        headers=headers,
    )
    assert combo.status_code == 201, combo.text
    cbody = combo.json()
    assert cbody["component_sum"] == 50.0
    assert cbody["bundle_price"] == 39.0
    # The bundle price overrides (is cheaper than) the component sum.
    assert cbody["bundle_price"] < cbody["component_sum"]

    # Adding the combo to a ticket prices the line at the bundle price.
    _tbl, ticket_id = await _open_ticket(client, token)
    line = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"combo_id": cbody["id"], "qty": 1},
        headers=headers,
    )
    assert line.status_code == 201, line.text
    lbody = line.json()
    assert lbody["unit_price"] == 39.0
    assert lbody["line_total"] == 39.0
    assert lbody["name"] == "Meal Deal"


# ---------------------------------------------------------------------------
# Ownership (SEC-02) + gating.
# ---------------------------------------------------------------------------
async def test_modifier_groups_owner_scoped(client):
    _u1, token1, _cid1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _cid2 = await make_client_account(client, business_type="restaurant")
    group_id = await _make_group(client, auth_headers(token1))

    # The second client can neither see nor mutate the first client's group.
    seen = await client.get("/api/v1/restaurant/modifier-groups", headers=auth_headers(token2))
    assert all(g["id"] != group_id for g in seen.json())
    blocked = await client.delete(
        f"/api/v1/restaurant/modifier-groups/{group_id}", headers=auth_headers(token2)
    )
    assert blocked.status_code == 404, blocked.text


async def test_combos_owner_scoped(client):
    _u1, token1, _cid1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _cid2 = await make_client_account(client, business_type="restaurant")
    combo = await client.post(
        "/api/v1/restaurant/combos",
        json={"name": "Deal", "bundle_price": 20.0, "components": []},
        headers=auth_headers(token1),
    )
    combo_id = combo.json()["id"]
    other = await client.get(
        f"/api/v1/restaurant/combos/{combo_id}", headers=auth_headers(token2)
    )
    assert other.status_code == 404, other.text


async def test_modifier_features_blocked_for_retail(client):
    """A retail-only merchant can't reach the modifier menu-builder (double-gate)."""
    _user, token, _cid = await make_client_account(client, business_type="retail")
    resp = await client.get("/api/v1/restaurant/modifier-groups", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
