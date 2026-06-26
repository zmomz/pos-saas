"""Advanced discounts — promotion engine (ISSUE-058, P2 pricing).

The order-level coded discount (``services.discounts``) only ever priced one flat
or percentage amount against the whole order. A real POS needs line-level,
category-level, and BOGO promotions that *auto-apply* when the cart meets their
conditions, and the resulting discount has to compose with VAT exactly like the
existing order discount: it reduces the taxable base, then VAT is charged on the
net.

These tests drive the pure engine ``services.promotions.compute_promotions`` —
one behaviour per test, exercised through its public interface — and the e2e
wiring into the POS sale path / preview endpoint.
"""
from conftest import add_product, auth_headers, make_client_account
from services.promotions import CartLine, PromoRule, compute_promotions


def _vat(taxable: float, rate: float = 15.0) -> float:
    return round(taxable * rate / 100, 2)


async def _create_promotion(client, headers, **payload):
    resp = await client.post(
        "/api/v1/entities/promotions", json=payload, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_line_level_percentage_discount_composes_with_vat():
    """A line-level % promo discounts only the matching product, before VAT [AC1]."""
    lines = [
        CartLine(product_id=1, category="Drinks", price=10.0, quantity=2),  # 20.00
        CartLine(product_id=2, category="Food", price=30.0, quantity=1),    # 30.00
    ]
    # 25% off product 1 only.
    rule = PromoRule(id=1, name="25% off cola", kind="line", disc_type="percentage",
                     value=25.0, product_id=1)

    result = compute_promotions(lines, [rule])

    # 25% of the 20.00 cola line = 5.00; the 30.00 food line is untouched.
    assert result.total_discount == 5.00
    assert [(a.name, a.amount) for a in result.applied] == [("25% off cola", 5.00)]

    # Composes with VAT: taxable base is subtotal (50) minus the promo (5) = 45,
    # VAT on the net, not the gross. The engine returns a Decimal discount (FIN-03).
    subtotal = 50.0
    taxable = subtotal - float(result.total_discount)
    assert taxable == 45.0
    assert _vat(taxable) == 6.75


def test_category_level_discount_targets_every_matching_line():
    """A category promo discounts every line in that category, case-insensitively [AC1]."""
    lines = [
        CartLine(product_id=1, category="Drinks", price=10.0, quantity=2),  # 20.00
        CartLine(product_id=2, category="drinks", price=5.0, quantity=4),   # 20.00
        CartLine(product_id=3, category="Food", price=30.0, quantity=1),    # 30.00
    ]
    rule = PromoRule(id=7, name="10% off Drinks", kind="category",
                     disc_type="percentage", value=10.0, category="Drinks")

    result = compute_promotions(lines, [rule])

    # 10% of the two drink lines (40.00 total) = 4.00; food untouched.
    assert result.total_discount == 4.00
    assert result.applied[0].kind == "category"


def test_bogo_buy_one_get_one_free_discounts_every_second_unit():
    """Buy-one-get-one-free: every 2nd target unit is free [AC1]."""
    # 5 units of a 10.00 product: 2 full pairs ⇒ 2 free units; the 5th is paid.
    lines = [CartLine(product_id=1, category="Drinks", price=10.0, quantity=5)]
    rule = PromoRule(id=3, name="BOGO cola", kind="bogo", product_id=1,
                     bogo_buy_qty=1, bogo_get_qty=1, bogo_get_percent=100.0)

    result = compute_promotions(lines, [rule])

    # floor(5/2)=2 free units × 10.00 = 20.00 off.
    assert result.total_discount == 20.00
    assert result.applied[0].kind == "bogo"


def test_bogo_buy_two_get_one_half_off_partial_groups_dont_discount():
    """Buy-2-get-1-at-50%: only complete buy+get groups earn the discount [AC1]."""
    # 7 units, group size 3 ⇒ 2 complete groups ⇒ 2 discounted units at 50%.
    lines = [CartLine(product_id=1, category="Food", price=20.0, quantity=7)]
    rule = PromoRule(id=4, name="B2G1 half", kind="bogo", product_id=1,
                     bogo_buy_qty=2, bogo_get_qty=1, bogo_get_percent=50.0)

    result = compute_promotions(lines, [rule])

    # floor(7/3)=2 discounted units × 20.00 × 50% = 20.00 off.
    assert result.total_discount == 20.00


def test_auto_promotion_fires_only_when_cart_condition_met():
    """A min-subtotal auto-promo applies only once the cart clears its floor [AC2]."""
    rule = PromoRule(id=9, name="SAR 10 off over 100", kind="line",
                     disc_type="fixed", value=10.0, product_id=1, min_subtotal=100.0)

    # Below the floor: nothing fires, no discount surfaced to the cashier.
    small = [CartLine(product_id=1, category="Food", price=50.0, quantity=1)]
    below = compute_promotions(small, [rule])
    assert below.total_discount == 0.0
    assert below.applied == []

    # At/over the floor: the promo fires and surfaces.
    big = [CartLine(product_id=1, category="Food", price=50.0, quantity=2)]  # 100.00
    over = compute_promotions(big, [rule])
    assert over.total_discount == 10.0
    assert [a.name for a in over.applied] == ["SAR 10 off over 100"]


def test_inactive_promotion_never_fires():
    """An inactive rule contributes nothing even when it would otherwise match [AC2]."""
    lines = [CartLine(product_id=1, category="Food", price=50.0, quantity=1)]
    rule = PromoRule(id=11, name="disabled", kind="line", disc_type="percentage",
                     value=50.0, product_id=1, is_active=False)

    assert compute_promotions(lines, [rule]).applied == []


def test_total_discount_clamped_to_subtotal():
    """Stacked promos can never push the order negative [AC1]."""
    lines = [CartLine(product_id=1, category="Food", price=10.0, quantity=1)]
    rules = [
        PromoRule(id=1, name="big fixed", kind="line", disc_type="fixed",
                  value=8.0, product_id=1),
        PromoRule(id=2, name="another", kind="line", disc_type="fixed",
                  value=8.0, product_id=1),
    ]
    # Two SAR 8 fixed promos on a SAR 10 line would be 16; clamped to 10.
    assert compute_promotions(lines, rules).total_discount == 10.0


# ---------------------------------------------------------------------------
# e2e — an auto-promotion fires on the live POS sale path and composes with VAT
# ---------------------------------------------------------------------------
async def test_auto_promotion_applied_on_sale_reduces_taxable_base(client):
    """A stored line promo auto-applies at checkout; VAT is charged on the net [AC1/AC2]."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    # A 20%-off-Cola promotion the merchant configured once.
    await _create_promotion(
        client, headers, name="20% off Cola", kind="line",
        disc_type="percentage", value=20.0, product_id=pid,
    )

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 20% of the 100.00 line = 20.00 discount; VAT on the 80.00 net, total 92.00.
    assert abs(body["subtotal"] - 100.0) < 0.01
    assert abs(body["discount_amount"] - 20.0) < 0.01
    assert abs(body["vat_amount"] - 12.0) < 0.01
    assert abs(body["total_amount"] - 92.0) < 0.01

    # The fired promotion surfaces on the sale so the cashier sees why.
    applied = body.get("applied_promotions") or []
    assert [p["name"] for p in applied] == ["20% off Cola"]
    assert abs(applied[0]["amount"] - 20.0) < 0.01


async def test_promotion_preview_surfaces_applicable_promotions(client):
    """The preview endpoint shows which promos a cart would earn, no sale made [AC2]."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=50.0)

    await _create_promotion(
        client, headers, name="SAR 10 off over 80", kind="line", disc_type="fixed",
        value=10.0, product_id=pid, min_subtotal=80.0,
    )

    # Below the floor (1 × 50 = 50): nothing fires.
    below = await client.post(
        "/api/v1/pos/promotions/preview",
        json={"items": [{"product_id": pid, "name": "Cola", "price": 50.0, "quantity": 1}]},
        headers=headers,
    )
    assert below.status_code == 200, below.text
    assert below.json()["total_discount"] == 0.0
    assert below.json()["applied"] == []

    # Over the floor (2 × 50 = 100): the promo surfaces for the cashier.
    over = await client.post(
        "/api/v1/pos/promotions/preview",
        json={"items": [{"product_id": pid, "name": "Cola", "price": 50.0, "quantity": 2}]},
        headers=headers,
    )
    assert over.status_code == 200, over.text
    body = over.json()
    assert abs(body["total_discount"] - 10.0) < 0.01
    assert [p["name"] for p in body["applied"]] == ["SAR 10 off over 80"]
