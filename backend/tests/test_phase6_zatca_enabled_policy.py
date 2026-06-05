"""F-022 / ZA-09 — the per-client ``zatca_enabled`` flag is honored on the sale path.

Before F-022 the flag existed but was never read: every sale was signed. These
tests pin the chosen policy ("honor the flag, default ON"):

* a client with ZATCA enabled (the provisioning default) gets a signed
  ``zatca_documents`` row + a stamped QR on the sale, and
* a client whose agent has switched ZATCA off completes the sale with **no**
  ``zatca_documents`` row, no stamp/QR, and ``zatca_status == "disabled"``.

Also covers the agent toggle endpoint (ZA-09 "the UI reflects it") and its
SEC-02 owner-scoping.
"""
from sqlalchemy import func, select, update

from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_account,
    make_client_under_agent,
)
from core.database import db_manager
from models.clients import Clients
from models.zatca_documents import ZatcaDocuments


async def _set_zatca_enabled(client_id: int, value: bool) -> None:
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients).where(Clients.id == client_id).values(zatca_enabled=value)
        )
        await db.commit()


async def _doc_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(ZatcaDocuments.id)).where(
                    ZatcaDocuments.client_id == client_id
                )
            )
        ).scalar() or 0


async def _sale(client, headers, pid):
    return await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )


async def test_zatca_enabled_sale_is_signed(client):
    """A ZATCA-enabled client (the default) signs the sale and archives a document."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10)

    resp = await _sale(client, headers, pid)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["zatca_status"] == "signed"
    assert body["zatca_document_id"] is not None
    assert body["zatca_qr"]
    assert await _doc_count(client_id) == 1


async def test_zatca_disabled_sale_persists_no_document(client):
    """ZA-09: with the flag off, the sale completes but writes no fiscal document."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10)

    await _set_zatca_enabled(client_id, False)

    resp = await _sale(client, headers, pid)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The sale itself still succeeds...
    assert body["status"] in ("completed", "success") or body["invoice_number"]
    # ...but carries no fiscal stamp and created no zatca_documents row.
    assert body["zatca_status"] == "disabled"
    assert body["zatca_document_id"] is None
    assert not body.get("zatca_qr")
    assert await _doc_count(client_id) == 0


async def test_agent_toggles_client_zatca_and_is_owner_scoped(client):
    """The agent toggle endpoint flips the flag and refuses other agents' clients."""
    _agent_user, agent_token, agent_id = await make_agent_account(client)
    _m_user, _m_token, client_id = await make_client_under_agent(client, agent_id)
    headers = auth_headers(agent_token)

    # A freshly provisioned-under-agent client reads as enabled (NULL/True).
    # First toggle switches it OFF.
    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/zatca", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["zatca_enabled"] is False

    # Toggling again switches it back ON.
    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/zatca", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["zatca_enabled"] is True

    # SEC-02: a different agent cannot toggle a client they do not own.
    _other_user, other_token, _other_agent_id = await make_agent_account(client)
    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/zatca",
        json={},
        headers=auth_headers(other_token),
    )
    assert resp.status_code == 404, resp.text
