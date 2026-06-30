"""#220 (M4·Inventory multi-branch): cross-branch sales reporting.

A multi-location chain needs one report that rolls each branch's sales up side by
side. The summary groups non-excluded transactions by ``branch_id`` and returns
per-branch net sales and a sale count, plus chain-wide totals. A credit note
carries negative signed amounts (F-007), so a signed SUM nets refunds out; held
and voided rows are excluded. Every read is owner-scoped (SEC-02).
"""
import pytest

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches",
        json={"name": name, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _seed_txn(
    user_id, client_id, branch_id, total, *, status="completed", invoice="INV"
):
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=str(user_id),
                client_id=client_id,
                invoice_number=f"{invoice}-{branch_id}-{total}-{status}",
                subtotal=total,
                total_amount=total,
                payment_method="cash",
                status=status,
                branch_id=branch_id,
            )
        )
        await db.commit()


async def _summary(client, headers):
    resp = await client.get(
        "/api/v1/pos/reports/cross-branch-sales", headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_summary_groups_net_sales_and_count_per_branch(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    airport = await _make_branch(client, headers, "Airport")
    suburb = await _make_branch(client, headers, "Suburb")

    await _seed_txn(user["id"], client_id, airport, 100.0)
    await _seed_txn(user["id"], client_id, airport, 50.0)
    await _seed_txn(user["id"], client_id, suburb, 25.0)

    summary = await _summary(client, headers)
    by_id = {b["branch_id"]: b for b in summary["branches"]}

    assert by_id[airport]["net_sales"] == 150.0
    assert by_id[airport]["sales_count"] == 2
    assert by_id[airport]["branch_name"] == "Airport"
    assert by_id[suburb]["net_sales"] == 25.0
    assert by_id[suburb]["sales_count"] == 1
    assert summary["total_net_sales"] == 175.0
    assert summary["total_sales_count"] == 3


@pytest.mark.asyncio
async def test_refunds_net_out_and_held_voided_excluded(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    airport = await _make_branch(client, headers, "Airport")

    await _seed_txn(user["id"], client_id, airport, 100.0)
    # A credit note carries negative signed amounts (F-007): nets out of revenue.
    await _seed_txn(user["id"], client_id, airport, -30.0, status="credit_note")
    # Held tickets and voided sales are not fiscal documents — excluded entirely.
    await _seed_txn(user["id"], client_id, airport, 999.0, status="held")
    await _seed_txn(user["id"], client_id, airport, 999.0, status="voided")

    summary = await _summary(client, headers)
    by_id = {b["branch_id"]: b for b in summary["branches"]}

    # 100 − 30 = 70 net; the two excluded rows never count.
    assert by_id[airport]["net_sales"] == 70.0
    assert by_id[airport]["sales_count"] == 2  # sale + credit note only
    assert summary["total_net_sales"] == 70.0


@pytest.mark.asyncio
async def test_summary_is_owner_scoped(client):
    """A second tenant's branch sales never appear in the first tenant's report
    (SEC-02): the summary is scoped to the caller's own client/owner."""
    user_a, token_a, cid_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    branch_a = await _make_branch(client, headers_a, "A-Airport")
    await _seed_txn(user_a["id"], cid_a, branch_a, 100.0)

    user_b, token_b, cid_b = await make_client_account(client)
    headers_b = auth_headers(token_b)
    branch_b = await _make_branch(client, headers_b, "B-Suburb")
    await _seed_txn(user_b["id"], cid_b, branch_b, 500.0)

    summary_b = await _summary(client, headers_b)
    branch_ids = {b["branch_id"] for b in summary_b["branches"]}
    assert branch_a not in branch_ids
    assert summary_b["total_net_sales"] == 500.0
    assert summary_b["total_sales_count"] == 1


@pytest.mark.asyncio
async def test_window_bounds_by_created_at(client):
    """An ISO start/end half-open window filters the rolled-up sales."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Airport")

    async with db_manager.async_session_maker() as db:
        from datetime import datetime, timezone

        for day, amount in ((10, 40.0), (20, 60.0)):
            db.add(
                Transactions(
                    user_id=str(user["id"]),
                    client_id=client_id,
                    invoice_number=f"W-{day}",
                    subtotal=amount,
                    total_amount=amount,
                    payment_method="cash",
                    status="completed",
                    branch_id=branch,
                    created_at=datetime(2026, 1, day, tzinfo=timezone.utc),
                )
            )
        await db.commit()

    # Window [Jan 15, Jan 25) captures only the Jan 20 sale.
    resp = await client.get(
        "/api/v1/pos/reports/cross-branch-sales"
        "?start=2026-01-15T00:00:00&end=2026-01-25T00:00:00",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_net_sales"] == 60.0
