"""Issue #230 (Integrations) — retail-scale embedded-barcode integration.

A price-computing / weighing scale prints a **variable-measure EAN-13** barcode:
a GS1 in-store flag (``2``) followed by a 5-digit item code (PLU), a value check
digit, a 5-digit embedded value, and the EAN-13 check digit. Each weigh prints a
*different* value, so the barcode never matches a stored catalog barcode exactly;
the POS must recognise the format, pull the item code out, resolve the product by
that code, and read the embedded value off the scan.

The embedded value's meaning follows the resolved product:

* a **weighted** product (``is_weighted``) → the value is a **weight in grams**,
  so the scan carries the line quantity (e.g. ``01234`` → 1.234 kg);
* any other product → the value is a **total price in halalas** (the scale did
  the price×weight maths itself), so the scan carries the line price
  (e.g. ``00850`` → 8.50).

These tests drive the behaviour end-to-end through the existing POS barcode
resolver (``GET /api/v1/pos/resolve-barcode``).
"""
import uuid

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.products import Products
from services.scale_barcode import ean13_check_digit


def _scale_barcode(item_code: str, value: int) -> str:
    """Build a valid variable-measure EAN-13: flag ``2`` + 5-digit item + value
    check placeholder + 5-digit value + EAN-13 check digit."""
    body = f"2{item_code:0>5}0{value:0>5}"
    return body + ean13_check_digit(body)


async def _add_product(client_id, user_id, *, name, price, barcode,
                       is_weighted=False, unit_label=None, quantity=100.0):
    async with db_manager.async_session_maker() as db:
        product = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=price,
            quantity=quantity,
            barcode=barcode,
            is_weighted=is_weighted,
            unit_label=unit_label,
            is_active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product.id


def test_parser_is_strict_about_the_scale_format():
    """The parser only accepts a 13-digit, flag-``2``, checksum-valid code so an
    ordinary EAN-13 or a corrupted scan is never mis-read as a scale barcode."""
    from services.scale_barcode import parse_scale_barcode

    good = _scale_barcode("00042", 1234)
    assert parse_scale_barcode(good) is not None
    # A non-``2`` flag (ordinary product EAN) is not a scale barcode.
    assert parse_scale_barcode("5901234123457") is None
    # A flag-2 code whose EAN-13 checksum is wrong (last digit flipped) is rejected.
    assert parse_scale_barcode(good[:12] + str((int(good[12]) + 1) % 10)) is None
    # Wrong length / non-digit is rejected.
    assert parse_scale_barcode("200420") is None
    assert parse_scale_barcode("2ABCDE01234C") is None
    assert parse_scale_barcode(None) is None


async def test_weighted_scale_barcode_carries_embedded_weight(client):
    """A weighted product scanned via a scale barcode resolves by item code and
    the scan carries the embedded weight as the line quantity."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Catalog template barcode for item 00042 (zeroed value), sold by the kg.
    template = _scale_barcode("00042", 0)
    pid = await _add_product(
        client_id, user["id"], name="Bananas", price=6.0,
        barcode=template, is_weighted=True, unit_label="kg",
    )

    # The scale weighs 1.234 kg → value 01234 g, a different barcode each weigh.
    scanned = _scale_barcode("00042", 1234)
    assert scanned != template

    r = await client.get(
        f"/api/v1/pos/resolve-barcode?barcode={scanned}", headers=headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "product"
    assert body["product_id"] == pid
    assert body["scale"] is True
    assert body["scale_kind"] == "weight"
    assert abs(body["scale_weight"] - 1.234) < 1e-9
    assert abs(body["price"] - 6.0) < 1e-9  # per-kg price, unchanged


async def test_price_embedded_scale_barcode_carries_total_price(client):
    """A non-weighted product scanned via a scale barcode reads the embedded
    value as the line's total price (the scale did the price×weight maths)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    template = _scale_barcode("00099", 0)
    pid = await _add_product(
        client_id, user["id"], name="Deli platter", price=0.0, barcode=template,
    )

    # Scale printed a total of 8.50 → value 00850 halalas.
    scanned = _scale_barcode("00099", 850)
    r = await client.get(
        f"/api/v1/pos/resolve-barcode?barcode={scanned}", headers=headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "product"
    assert body["product_id"] == pid
    assert body["scale"] is True
    assert body["scale_kind"] == "price"
    assert abs(body["scale_price"] - 8.50) < 1e-9
    assert body["scale_weight"] is None


async def test_ordinary_barcode_is_not_treated_as_a_scale_scan(client):
    """A plain catalog barcode resolves exactly as before — no scale fields — and
    an unknown code (including a well-formed scale barcode for an item the catalog
    has no product for) still resolves to ``none``."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(
        client_id, user["id"], name="Boxed cereal", price=12.0, barcode="5901234123457",
    )

    r = await client.get(
        "/api/v1/pos/resolve-barcode?barcode=5901234123457", headers=headers
    )
    body = r.json()
    assert body["kind"] == "product"
    assert body["product_id"] == pid
    assert body["scale"] is False
    assert body["scale_kind"] is None

    # A valid scale barcode for an item code the catalog does not stock.
    orphan = _scale_barcode("77777", 500)
    r2 = await client.get(
        f"/api/v1/pos/resolve-barcode?barcode={orphan}", headers=headers
    )
    assert r2.json()["kind"] == "none"
