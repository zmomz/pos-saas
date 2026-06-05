# F-068 — Profit / COGS / margin report + dead-stock

## Parent

`docs/prd/PRD-RPT-reporting-depth.md` — Reporting Depth (RPT core). Source finding F-068 (RPT-04 / INV-09).

## What to build

A merchant cannot see gross profit or margin anywhere — COGS is computed (moving-average on PO receive) but only surfaces inside the GL journal export. Build a profit/margin report:

- **`GET /api/v1/reports/profit-margin`** (owner-scoped, date-range windowed): per-item and per-category **revenue, COGS, gross profit, and margin %**, reusing the journal COGS stream + revenue-by-product.
- **Dead-stock / slow-mover list**: products with no sale in N days and on-hand > 0.
- **Snapshot `cost_price` onto the sale line at sale time** so historical margin is stable (not recomputed from current cost). This is a small, additive change to the sale path — it must be **behavior-preserving** for the existing atomic sale (existing POS/ZATCA tests stay green).
- CSV export; aggregate in SQL / streaming (do not load-everything — respect OPS-05).

Frontend: a Profit/Margin tab on the ReportsAnalytics back-office surface with a date-range picker and CSV download; typed `api.ts` wrapper; i18n ×4 (ar/en/hi/ur) with RTL.

## Acceptance criteria

- [ ] `GET /reports/profit-margin` returns per-item and per-category revenue, COGS, gross profit, and margin % over a date window, owner-scoped.
- [ ] A dead-stock list (no sale in N days, on-hand > 0) is included or available via the endpoint.
- [ ] The sale line snapshots `cost_price` at sale time; the report uses the snapshot, not current cost.
- [ ] The `cost_price` snapshot does not change existing sale behavior — `test_pos_atomic.py` / `test_phase2_zatca_sale.py` pass unchanged.
- [ ] CSV export works; aggregation is done in SQL/stream, not by loading all rows.
- [ ] Tests added and green: `test_margin_report_uses_cogs` (revenue 100, COGS 60, gross 40).
- [ ] Profit/Margin tab renders loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

None - can start immediately.
