"""Issue #230 (Integrations) — label-printer product-label rendering.

The second hardware-integration slice (after the retail-scale barcode): drive a
**label printer** (a Zebra-class device speaks ZPL) so a merchant can print a
shelf / price label for a catalog product. ``render_product_label`` is a pure
ZPL generator; ``GET /api/v1/products/{id}/label`` hands the payload back for the
caller's own product so the front end can stream it to the device.

A ZPL label is a plain-text program bracketed by ``^XA`` … ``^XZ``; the product's
name and price render as text fields and — when the product carries a catalog
barcode — a Code 128 (``^BC``) symbol the label printer prints as a scannable
barcode. Field data is escaped because ``^`` / ``~`` open ZPL commands: an
unescaped caret in a product name would otherwise break out of the field.
"""
from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.products import Products


async def _add_product(client_id, user_id, *, name, price, barcode=None,
                       is_weighted=False, unit_label=None):
    async with db_manager.async_session_maker() as db:
        product = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=price,
            quantity=10.0,
            barcode=barcode,
            is_weighted=is_weighted,
            unit_label=unit_label,
            is_active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product.id


# ---------- pure renderer ----------

def test_label_is_a_bracketed_zpl_program_with_name_price_and_barcode():
    """A product with a barcode renders a ^XA…^XZ ZPL program carrying the name,
    the price+currency, and a Code 128 (^BC) barcode of the catalog code."""
    from services.product_label import render_product_label

    zpl = render_product_label(name="Flat White", price=14.5, barcode="6281000012345")

    assert zpl.startswith("^XA")
    assert zpl.rstrip().endswith("^XZ")
    assert "Flat White" in zpl
    assert "14.50 SAR" in zpl
    assert "^BC" in zpl              # Code 128 barcode command
    assert "6281000012345" in zpl    # the barcode value is the ^BC field data


def test_label_without_a_barcode_omits_the_symbol_but_keeps_name_and_price():
    """A product with no catalog code prints a name+price label and no ^BC block —
    a variable-measure/weighed item has no fixed code to encode."""
    from services.product_label import render_product_label

    zpl = render_product_label(name="Loose Dates", price=9.0, barcode=None,
                               is_weighted=True, unit_label="kg")

    assert zpl.startswith("^XA")
    assert "^BC" not in zpl
    assert "Loose Dates" in zpl
    # Weighted goods price per unit — the suffix makes the shelf label honest.
    assert "9.00 SAR / kg" in zpl


def test_field_data_is_escaped_so_a_caret_cannot_break_out_of_the_field():
    """``^``/``~``/``_`` open ZPL commands; a name carrying one must be neutralised
    so it can never inject a command into the label program."""
    from services.product_label import render_product_label

    zpl = render_product_label(name="A^B~C_D", price=1.0, barcode="123")

    # None of the raw command characters survive inside the rendered name.
    assert "A^B" not in zpl
    assert "~C" not in zpl
    assert "A B C D" in zpl


# ---------- endpoint: GET /api/v1/products/{id}/label ----------

async def test_endpoint_returns_the_zpl_payload_for_the_callers_product(client):
    """The route fetches the owner's product and returns its rendered ZPL label."""
    user, token, client_id = await make_client_account(client)
    pid = await _add_product(client_id, user["id"], name="Flat White",
                             price=14.5, barcode="6281000012345")

    resp = await client.get(f"/api/v1/products/{pid}/label",
                            headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["format"] == "zpl"
    assert body["product_id"] == pid
    assert body["copies"] == 1
    assert body["payload"].startswith("^XA")
    assert "Flat White" in body["payload"]
    assert "14.50 SAR" in body["payload"]
    assert "6281000012345" in body["payload"]


async def test_endpoint_honours_the_copies_query_parameter(client):
    """``copies`` sets the ZPL print quantity (^PQ) so a merchant can batch."""
    user, token, client_id = await make_client_account(client)
    pid = await _add_product(client_id, user["id"], name="Tag", price=1.0)

    resp = await client.get(f"/api/v1/products/{pid}/label?copies=3",
                            headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["copies"] == 3
    assert "^PQ3" in body["payload"]


async def test_endpoint_rejects_an_unsupported_label_format(client):
    """Only ZPL is supported today; anything else is an explicit 400, not silence."""
    user, token, client_id = await make_client_account(client)
    pid = await _add_product(client_id, user["id"], name="Tag", price=1.0)

    resp = await client.get(f"/api/v1/products/{pid}/label?format=epl",
                            headers=auth_headers(token))
    assert resp.status_code == 400, resp.text


async def test_endpoint_does_not_leak_another_tenants_product(client):
    """Owner scoping (SEC-02): a product id belonging to another client 404s."""
    owner, _, owner_client = await make_client_account(client)
    other_user, other_token, _ = await make_client_account(client)
    pid = await _add_product(owner_client, owner["id"], name="Secret", price=5.0)

    resp = await client.get(f"/api/v1/products/{pid}/label",
                            headers=auth_headers(other_token))
    assert resp.status_code == 404, resp.text


async def test_endpoint_404s_a_missing_product(client):
    user, token, _ = await make_client_account(client)
    resp = await client.get("/api/v1/products/999999/label",
                            headers=auth_headers(token))
    assert resp.status_code == 404, resp.text
