"""ISSUE-223 (M4 Product) — expiry enforced at sale.

The remaining portion of the acceptance criterion "Batch/expiry/serial/IMEI
tracking ... enforced at sale" after serial/IMEI and batch number: the **expiry**
piece. A batch-tracked product (``track_batch`` — a lot-controlled perishable
such as a medicine or food item) captures the dispensed lot's expiry date at the
point of sale. The server is authoritative: an expired lot (``expiry_date``
strictly before today) CANNOT be rung up — selling expired stock is rejected
(400) before anything is booked. A not-yet-expired lot sells and its expiry is
persisted onto the sale line.

Pinned end-to-end:

* selling a batch-tracked product whose captured ``expiry_date`` is in the past
  is rejected (400, "expired" in the detail);
* selling one with a future ``expiry_date`` (and a batch number) succeeds, and
  the expiry survives onto the recorded sale line (items_json);
* an ordinary (untracked) product is unaffected — a past ``expiry_date`` on it
  still sells, because expiry is only enforced on batch-tracked lots.
"""
import json
from datetime import datetime, timedelta, timezone

from conftest import auth_headers, make_client_account


def _date(days):
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


async def _create_product(client, token, **fields):
    payload = {"name": "Widget", "price": 10.0}
    payload.update(fields)
    resp = await client.post(
        "/api/v1/products/create", json=payload, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _sale(client, token, item):
    body = {"items": [item], "payment_method": "cash"}
    return await client.post(
        "/api/v1/pos/transaction", json=body, headers=auth_headers(token)
    )


async def test_sale_of_expired_batch_tracked_lot_is_rejected(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Amoxicillin", price=20.0, quantity=50, track_batch=True
    )

    resp = await _sale(
        client,
        token,
        {
            "product_id": product["id"],
            "name": "Amoxicillin",
            "price": 20.0,
            "quantity": 1,
            "batch_number": "LOT-A",
            "expiry_date": _date(-1),
        },
    )
    assert resp.status_code == 400, resp.text
    assert "expired" in resp.json()["detail"].lower()


async def test_sale_of_unexpired_batch_tracked_lot_succeeds_and_persists_expiry(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Amoxicillin", price=20.0, quantity=50, track_batch=True
    )

    expiry = _date(30)
    resp = await _sale(
        client,
        token,
        {
            "product_id": product["id"],
            "name": "Amoxicillin",
            "price": 20.0,
            "quantity": 1,
            "batch_number": "LOT-A",
            "expiry_date": expiry,
        },
    )
    assert resp.status_code == 200, resp.text

    # The captured expiry survives onto the recorded sale line.
    listing = await client.get(
        "/api/v1/pos/transactions", headers=auth_headers(token)
    )
    assert listing.status_code == 200, listing.text
    txns = listing.json()["items"]
    lines = json.loads(txns[0]["items_json"])
    sold = next(li for li in lines if li.get("product_id") == product["id"])
    assert sold["expiry_date"] == expiry


async def test_past_expiry_on_untracked_product_still_sells(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="USB cable", price=15.0, quantity=10
    )

    resp = await _sale(
        client,
        token,
        {
            "product_id": product["id"],
            "name": "USB cable",
            "price": 15.0,
            "quantity": 1,
            "expiry_date": _date(-1),
        },
    )
    assert resp.status_code == 200, resp.text
