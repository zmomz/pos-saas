"""SEC-05 (F-050): PDPL — consent capture + data-subject export/erasure.

Saudi PDPL (Personal Data Protection Law) requires a merchant (the data
controller) to:
  * capture explicit marketing consent (CRM-05) — default off;
  * honour a data subject's right to access/portability (export everything held
    about them, including linked fiscal records);
  * honour the right to erasure (tombstone PII) while retaining fiscal records
    that ZATCA law obliges the merchant to keep for 6 years.

These tests pin:
  * a customer's data export returns the CRM record + all customer-linked fiscal
    rows;
  * erasure tombstones the PII (name redacted, phone/email/VAT/notes nulled,
    consent withdrawn, ``pii_erased_at`` stamped) but keeps the row;
  * consent defaults to off and is stamped when set;
  * both endpoints are owner-scoped (a foreign/unknown id → 404, SEC-02).
"""
import uuid

import pytest

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions

CUSTOMERS = "/api/v1/entities/customers"


async def _add_transaction(user_id: str, client_id: int, *, name: str, phone: str):
    """Insert a completed sale denormalizing the customer PII (as the POS does)."""
    async with db_manager.async_session_maker() as db:
        txn = Transactions(
            user_id=user_id,
            client_id=client_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            subtotal=100.0,
            vat_amount=15.0,
            total_amount=115.0,
            payment_method="cash",
            status="completed",
            customer_name=name,
            customer_phone=phone,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)
        return txn.id


async def _create_customer(client, token, **fields):
    body = {"name": "Layla", "phone": "+966500000001", "email": "layla@example.com"}
    body.update(fields)
    resp = await client.post(CUSTOMERS, json=body, headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_data_export_returns_customer_and_linked_rows(client):
    """PDPL access right: export returns the CRM record + all linked fiscal rows."""
    user, token, client_id = await make_client_account(client)
    customer = await _create_customer(client, token, phone="+966500111222")

    # Two sales linked by the customer's phone, one unrelated sale.
    await _add_transaction(user["id"], client_id, name="Layla", phone="+966500111222")
    await _add_transaction(user["id"], client_id, name="Layla", phone="+966500111222")
    await _add_transaction(user["id"], client_id, name="Other", phone="+966509999999")

    resp = await client.get(
        f"{CUSTOMERS}/{customer['id']}/data-export", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer"]["id"] == customer["id"]
    assert body["customer"]["phone"] == "+966500111222"
    assert body["transaction_count"] == 2
    invoices = {t["invoice_number"] for t in body["transactions"]}
    assert len(invoices) == 2
    assert body["retention_notice"]


@pytest.mark.asyncio
async def test_erase_tombstones_pii_but_keeps_row(client):
    """PDPL erasure: PII scrubbed, row retained, consent withdrawn, stamp set."""
    user, token, client_id = await make_client_account(client)
    customer = await _create_customer(
        client, token, phone="+966500333444", vat_number="300000000000003",
        notes="VIP", marketing_consent=True,
    )

    resp = await client.post(
        f"{CUSTOMERS}/{customer['id']}/erase", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    erased = resp.json()
    assert erased["id"] == customer["id"]  # row retained
    assert erased["name"] == "[erased]"
    assert erased["phone"] is None
    assert erased["email"] is None
    assert erased["vat_number"] is None
    assert erased["notes"] is None
    assert erased["marketing_consent"] is False
    assert erased["pii_erased_at"] is not None

    # Persisted: a fresh read reflects the tombstone.
    again = await client.get(
        f"{CUSTOMERS}/{customer['id']}", headers=auth_headers(token)
    )
    assert again.status_code == 200, again.text
    assert again.json()["name"] == "[erased]"
    assert again.json()["phone"] is None


@pytest.mark.asyncio
async def test_marketing_consent_defaults_off_and_stamps_when_set(client):
    """CRM-05: consent is off unless explicitly given; setting it stamps the time."""
    _user, token, _cid = await make_client_account(client)

    # Created without consent → off, no stamp.
    no_consent = await _create_customer(client, token, phone="+966500555666")
    assert no_consent["marketing_consent"] in (False, None)
    assert no_consent["consent_updated_at"] is None

    # Opt in via update → flag set and stamped.
    upd = await client.put(
        f"{CUSTOMERS}/{no_consent['id']}",
        json={"marketing_consent": True},
        headers=auth_headers(token),
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["marketing_consent"] is True
    assert upd.json()["consent_updated_at"] is not None


@pytest.mark.asyncio
async def test_data_subject_endpoints_are_owner_scoped(client):
    """SEC-02: one merchant cannot export or erase another merchant's customer."""
    _u1, token1, _c1 = await make_client_account(client)
    _u2, token2, _c2 = await make_client_account(client)

    customer = await _create_customer(client, token1, phone="+966500777888")

    # Merchant 2 cannot export merchant 1's customer.
    export = await client.get(
        f"{CUSTOMERS}/{customer['id']}/data-export", headers=auth_headers(token2)
    )
    assert export.status_code == 404, export.text

    # Merchant 2 cannot erase merchant 1's customer.
    erase = await client.post(
        f"{CUSTOMERS}/{customer['id']}/erase", headers=auth_headers(token2)
    )
    assert erase.status_code == 404, erase.text

    # Merchant 1's customer is untouched.
    still = await client.get(
        f"{CUSTOMERS}/{customer['id']}", headers=auth_headers(token1)
    )
    assert still.json()["phone"] == "+966500777888"
