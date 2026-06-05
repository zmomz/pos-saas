# F-072 — PDF export for every report

## Parent

`docs/prd/PRD-RPT-reporting-depth.md` — Reporting Depth (RPT core). Source finding F-072 (RPT-10).

## What to build

Every data report is CSV-only; PDF rendering exists for invoices but not reports. Add a generic report→PDF path:

- A **generic report→PDF renderer** (fpdf2, **RTL-aware** table) alongside the existing invoice renderer in `pdf_render.py`.
- A **`?format=pdf` branch on each `/reports/*` endpoint** — both the existing ones (sales-summary, top-products, payment-breakdown, journal) **and the four new ones** (profit-margin, vat-summary, inventory, refunds-voids/discounts) — returning `application/pdf`.
- Reports render Arabic correctly regardless of UI language (consistent with the fiscal-Arabic rule).

Frontend: a `downloadReportPdf` wrapper in `api.ts` and a PDF download button on each ReportsAnalytics tab; i18n ×4 with RTL.

## Acceptance criteria

- [ ] A shared report→PDF renderer (fpdf2, RTL-aware) exists alongside the invoice renderer.
- [ ] Every `/reports/*` endpoint (existing + the four new) accepts `?format=pdf` and returns `application/pdf`.
- [ ] PDFs render Arabic content correctly (RTL).
- [ ] `downloadReportPdf` wired into `api.ts`; each Reports tab has a working PDF download button.
- [ ] Tests added and green: each report with `format=pdf` returns `application/pdf` (`%PDF` magic bytes).
- [ ] PDF buttons render correctly across all Reports tabs; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `01-F068-profit-margin-report.md`, `02-F069-vat-summary-report.md`, `03-F070-inventory-report.md`, `04-F071-refund-void-discount-reports.md` (the PDF wrapper applies `?format=pdf` to these new reports, so they must exist first).
