"""Phase 2 (ISSUE-027 / H5) — the AuditLog read API renders against real fields.

The audit middleware stores the *actor's* ``user_id`` and a verbose
``METHOD /path`` action. The AuditLog page expects a resolved ``user_email`` and
normalized action verbs. These tests pin the read-side enrichment: the GET
endpoint resolves the actor's email and maps the stored action to a verb the UI
badges/filters on, without rewriting the stored compliance row.
"""
import pytest

from conftest import add_product, auth_headers, make_client_account


@pytest.mark.parametrize(
    "raw,verb",
    [
        ("POST /api/v1/entities/products", "create"),
        ("PUT /api/v1/entities/products/5", "update"),
        ("PATCH /api/v1/entities/products/5", "update"),
        ("DELETE /api/v1/entities/products/5", "delete"),
        ("POST /api/v1/pos/transaction", "sale"),
        ("GET /api/v1/reports/sales/export", "export"),
        ("AUTH_FAILURE POST /api/v1/entities/products", "auth_failure"),
        ("", "other"),
        (None, "other"),
    ],
)
def test_normalize_action_maps_verbose_strings_to_verbs(raw, verb):
    from services.audit_logs import normalize_action

    assert normalize_action(raw) == verb


async def _fetch_audit_logs(client, headers):
    resp = await client.get("/api/v1/entities/audit_logs", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def test_response_resolves_actor_email_and_normalizes_action(client):
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

    items = await _fetch_audit_logs(client, headers)
    assert items, "expected at least one audit row for the mutation"
    row = items[0]
    # User column: resolved from the actor's user_id, not a bare id.
    assert row["user_email"] == user["email"]
    # A POS sale normalizes to the ``sale`` verb (not the verbose path).
    assert row["action"] == "sale"


async def test_owner_sees_staff_action_with_resolved_staff_email(client):
    """An owner's audit query surfaces a staff member's action, with the *staff*
    actor's email resolved (owner-scoped reads from #12 + email resolution)."""
    from core.database import db_manager
    from models.staff_members import Staff_members
    from services.audit import write_audit_log
    from tests.conftest import register_user

    owner, owner_token, _ = await make_client_account(client)
    staff_user, _, _ = await register_user(client)

    # Link the staff login to the owning merchant so the writer tags the row
    # with the owner (resolve_owner_user_id maps staff → owner).
    async with db_manager.async_session_maker() as db:
        db.add(
            Staff_members(
                user_id=owner["id"],
                login_user_id=staff_user["id"],
                name="Cashier",
                email=staff_user["email"],
                role="cashier",
                is_active=True,
            )
        )
        await db.commit()

    # The staff member deletes a product (recorded by the production writer).
    await write_audit_log(
        user_id=staff_user["id"],
        action="DELETE /api/v1/entities/products/5",
    )

    items = await _fetch_audit_logs(client, auth_headers(owner_token))
    staff_rows = [r for r in items if r["user_email"] == staff_user["email"]]
    assert staff_rows, "owner should see the staff member's audit row"
    assert staff_rows[0]["action"] == "delete"
