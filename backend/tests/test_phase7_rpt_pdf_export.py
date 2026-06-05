"""Phase 7 — PDF export for every report (F-072 / RPT-10).

Every data report was CSV-only; PDF rendering existed for invoices but not
reports. This slice adds a generic, RTL-aware report→PDF renderer alongside the
invoice renderer and a ``?format=pdf`` branch on every ``/reports/*`` endpoint.

The catch-forever test: each report answers ``?format=pdf`` with a real
``application/pdf`` document (``%PDF`` magic bytes), and does so even when the
report carries Arabic content — so the always-Arabic fiscal rule extends to the
operational reports without blowing up the renderer.
"""
from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_account,
)

# Every report endpoint that must honour ``?format=pdf`` (the existing four plus
# the four new reporting-depth ones; refunds-voids and discounts are separate).
REPORT_PATHS = [
    "/api/v1/reports/sales-summary",
    "/api/v1/reports/top-products",
    "/api/v1/reports/payment-breakdown",
    "/api/v1/reports/journal-export",
    "/api/v1/reports/profit-margin",
    "/api/v1/reports/vat-summary",
    "/api/v1/reports/inventory",
    "/api/v1/reports/refunds-voids",
    "/api/v1/reports/discounts",
]


async def _sell(client, headers, pid, name, price, qty, discount=0.0):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": name, "price": price, "quantity": qty}],
            "payment_method": "cash",
            "vat_rate": 15.0,
            "discount_amount": discount,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_every_report_exports_pdf_with_arabic(client):
    """Named catch-forever test: each /reports/* answers ?format=pdf with a PDF.

    Seeds an Arabic-named product and a discounted sale (so every report has
    content, including the always-Arabic data path), then asserts every endpoint
    returns ``application/pdf`` whose body starts with the ``%PDF`` magic bytes.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    # Arabic name exercises the reshaper/bidi path inside the renderer.
    pid = await add_product(
        client_id, user["id"], name="قهوة عربية", quantity=100, price=10.0, cost_price=6.0
    )
    await _sell(client, headers, pid, "قهوة عربية", 10.0, 5, discount=3.0)

    for path in REPORT_PATHS:
        resp = await client.get(f"{path}?format=pdf", headers=headers)
        assert resp.status_code == 200, f"{path}: {resp.text}"
        assert resp.headers["content-type"] == "application/pdf", path
        assert resp.content[:4] == b"%PDF", f"{path}: not a PDF ({resp.content[:8]!r})"


async def test_report_default_format_is_json(client):
    """Without ?format=pdf the report still returns its JSON body unchanged."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Widget", quantity=20, price=10.0)
    await _sell(client, headers, pid, "Widget", 10.0, 2)

    resp = await client.get("/api/v1/reports/vat-summary", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/json")
    assert "buckets" in resp.json()


async def test_pdf_export_owner_scoped(client):
    """SEC-02: the role gate runs before the PDF branch — an agent is 403."""
    _, agent_token, _ = await make_agent_account(client)
    for path in REPORT_PATHS:
        resp = await client.get(f"{path}?format=pdf", headers=auth_headers(agent_token))
        assert resp.status_code == 403, f"{path}: {resp.status_code}"
