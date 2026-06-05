# PRD — Reporting Depth (RPT core, F-068–F-072)

> **Status:** ready-for-agent · **Source:** `COMPLETENESS_REVIEW.md` §R2 (F-068–F-072, RPT-04/05/07/08/10) · **Bar:** Foodics / Rewaa / Marn parity, localized for Saudi · **Spec authority:** `srs.md` v2.0 + `INTENDED_BEHAVIOR.md` (when code and SRS disagree, SRS wins).
>
> Covers the five open reporting findings: F-068 (profit/COGS/margin + dead-stock), F-069 (VAT report by rate), F-070 (inventory valuation at cost + movements), F-071 (refund/void + discount reports), F-072 (PDF export for every report).

---

## Problem Statement

The data exists; the merchant can't see it. Today the app books COGS (moving-average on PO receive) and VAT, runs an atomic sale, tracks stock by branch, and logs voids/refunds/discounts — but **none of it surfaces as a report a merchant can act on or file taxes from.** Concretely:

- **No profit.** A merchant cannot see gross profit or per-item/category margin anywhere. COGS is computed but buried inside the GL journal export — there is no P&L, no margin %, no dead-stock / slow-mover list.
- **No VAT return support.** Filing a ZATCA VAT return, the merchant has no output-VAT-by-rate report (15% / 0% / exempt); `vat_amount` is one aggregate line in the journal.
- **No inventory valuation.** There is no on-hand-value-at-cost report and no stock-movement ledger. The only stock figure is a dashboard stat valued at **sale price**, not cost — a latent bug.
- **No refund/void/discount audit.** A manager cannot pull refunds, voids, or discounts as a cross-period report with actor + reason; those totals live only inside a single shift's Z-report.
- **CSV only.** Every data report is CSV-only; PDF rendering exists for invoices but not for reports.

Net effect: the owner cannot answer "Am I making money?", "What do I owe in VAT?", "What is my stock worth?", or "Who discounted what?" — table-stakes for the category leaders.

## Solution

Add a reporting layer over the data the system already captures, matching what Foodics/Rewaa/Marn expose, localized for Saudi (VAT-return boxes, Arabic-capable PDF). Each report is a new `GET /api/v1/reports/*` endpoint plus a tab on the back-office ReportsAnalytics surface, CSV today and PDF via a shared renderer. From the merchant's perspective, after this ships:

- A **profit/margin report** shows per-item and per-category revenue, COGS, and margin %, plus a **dead-stock** list (no sale in N days, on-hand > 0).
- A **VAT summary** buckets sales into standard-rated / zero-rated / exempt (taxable base + VAT per rate) matching the ZATCA VAT-return boxes, with credit notes netted.
- An **inventory report** values on-hand stock at **cost** and shows a movements feed (PO receipts, branch transfers, adjustments).
- **Refund/void** and **discount** reports list each event over a window with actor, reason, and amount.
- **Every report exports to PDF** (RTL-aware) as well as CSV.

Every new screen renders its loading / empty / error / permission / offline states (per `INTENDED_BEHAVIOR.md`), uses brand tokens, is translated across all four languages with RTL verified, and is owner-scoped in the service layer (SEC-02).

---

## Implementation Decisions

### Tracer-bullet ordering
Reports 01–04 are independent; the PDF wrapper consumes all of them, so it goes last:
1. **F-068 profit/COGS/margin** — also snapshots `cost_price` onto the sale line so historical margin is stable (a small sale-path data-capture change; additive, behavior-preserving for the existing atomic sale).
2. **F-069 VAT summary by rate.**
3. **F-070 inventory valuation at cost + movements** — also fix the dashboard stat that values stock at sale price.
4. **F-071 refund/void + discount reports.**
5. **F-072 generic report→PDF renderer** + `?format=pdf` on every `/reports/*` (old and new).

### Backend
- New endpoints under the existing `routers/features.py` `/api/v1/reports/*` namespace (or a sibling module exposing `router`): `profit-margin`, `vat-summary`, `inventory`, `refunds-voids`, `discounts`. All owner-scoped (`user_id`/`client_id`) in the service layer, windowed by date range.
- Reuse existing streams: the journal COGS stream (`features.py` journal-export `:1168-1199`), `_aggregate_zreport` refund/void/discount logic (`:1376-1487`) generalized across a window, moving-average `cost_price`, and `audit_logs`/`transactions` joins for actor + reason.
- **Snapshot `cost_price` onto the sale line** at sale time (F-068) so margin is historically stable rather than recomputed from current cost.
- Aggregate in SQL / streaming — do **not** load-everything (respect OPS-05; F-048 set the precedent).

### Frontend
- New tabs on the ReportsAnalytics back-office surface, one per report; date-range picker; CSV + PDF download buttons. Typed wrappers in `src/lib/api.ts` (incl. `downloadReportPdf`); base URL resolved at runtime. i18n keys ×4 (ar/en/hi/ur) with RTL.

### Printables (F-072)
- A generic report→PDF renderer (fpdf2, RTL-aware table) alongside the existing invoice renderer in `pdf_render.py`; a `?format=pdf` branch on each `/reports/*` returns `application/pdf`.

---

## Testing Decisions

Drive the real ASGI app over HTTP (`httpx.AsyncClient`) with the existing `backend/tests/conftest.py` fixtures (`make_client_account`, `add_product` w/ `cost_price`, `get_product_quantity`). Assert on response payloads and durable state, not private functions. Named "catch-forever" tests (from the findings):
- F-068: `test_margin_report_uses_cogs` (revenue 100, COGS 60, gross 40).
- F-069: sales at 15% and 0% split into the right buckets; net VAT = collected − reversed.
- F-070: valuation uses `cost_price`; a PO receive + a transfer appear in movements.
- F-071: a void (with reason) and a discounted sale each appear with actor / reason / amount.
- F-072: each report with `format=pdf` returns `application/pdf` (`%PDF` magic bytes).

**Regression gate:** the full existing `backend/tests` suite stays green; the F-068 `cost_price`-on-sale-line snapshot must not change existing POS/ZATCA sale behavior.

## Out of Scope

- **F-073+ finance** (P&L + expense attachment, AP, accounting integrations) — separate Finance PRD.
- **Accounting-package push** (Zoho/QuickBooks/Odoo, F-074).
- **Reseller / white-label** reporting (settlement statements F-088) — separate PRD.
- New data capture beyond the F-068 `cost_price` snapshot; reports read what the system already records.
