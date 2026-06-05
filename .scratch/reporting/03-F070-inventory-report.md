# F-070 — Inventory report (on-hand value at cost, movements)

## Parent

`docs/prd/PRD-RPT-reporting-depth.md` — Reporting Depth (RPT core). Source finding F-070 (RPT-07).

## What to build

A merchant cannot pull an inventory valuation at cost or a stock-movement ledger; the only stock figure is a dashboard stat valued at **sale price**. Build an inventory report:

- **`GET /api/v1/reports/inventory`** (owner-scoped): **on-hand valuation at `cost_price`** (per product / branch, with totals) + a **movements feed** sourced from PO receipts, branch transfers, and adjustments over a window.
- **Fix the latent bug**: the dashboard stat at `production.py:1254` (`total_stock_value = Σ price*qty`) values stock at sale price — change it to value at **cost**.
- CSV export; aggregate in SQL / streaming.

Frontend: an Inventory tab on ReportsAnalytics (valuation + movements) with CSV download; typed `api.ts` wrapper; i18n ×4 with RTL.

## Acceptance criteria

- [ ] `GET /reports/inventory` returns on-hand valuation at `cost_price` (not sale price), owner-scoped, with per-product/branch detail + total.
- [ ] A movements feed shows PO receipts, branch transfers, and adjustments over the window.
- [ ] The dashboard `total_stock_value` stat is corrected to value at cost.
- [ ] CSV export works; aggregation in SQL/stream.
- [ ] Tests added and green: valuation uses `cost_price`; a PO receive + a transfer appear in movements.
- [ ] Inventory tab renders loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

None - can start immediately.
