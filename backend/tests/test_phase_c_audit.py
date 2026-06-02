"""Phase C — automatic audit-log writing on authenticated mutations."""
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account


async def _audit_rows_for(user_id: str):
    from core.database import db_manager
    from models.audit_logs import Audit_logs

    async with db_manager.async_session_maker() as db:
        result = await db.execute(
            select(Audit_logs).where(Audit_logs.user_id == str(user_id))
        )
        return result.scalars().all()


async def test_mutation_writes_audit_log(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=5.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Item", "price": 5.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows_for(user["id"])
    actions = [r.action for r in rows]
    assert any("POST /api/v1/pos/transaction" in a for a in actions), actions


async def test_get_requests_are_not_audited(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await client.get("/api/v1/pos/transactions", headers=headers)

    rows = await _audit_rows_for(user["id"])
    # No mutation performed by this user → no audit rows from the GET.
    assert all(not r.action.startswith("GET") for r in rows)
