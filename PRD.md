# PRD — Reporting Depth (RPT core, F-068–F-072)

Ralph driver for the reporting-depth cluster. Each task is one **tracer-bullet
vertical slice** (schema/read-model → API → UI → tests). The one-line task here is a
pointer; the **full spec + acceptance criteria live in the linked slice file** under
`.scratch/reporting/`. Source of truth: `srs.md` v2.0 + `INTENDED_BEHAVIOR.md` (SRS wins
on conflict). Parity bar: Foodics / Rewaa / Marn, localized for Saudi. Parent PRD:
`docs/prd/PRD-RPT-reporting-depth.md`.

> Previous cluster (restaurant vertical, F-055–F-062) is COMPLETE — see
> `docs/prd/PRD-RST-restaurant-vertical.md` and `progress.txt`.

## How to work this PRD (Ralph rules)

- Tasks are in **strict build order**. Always take the **topmost unchecked `- [ ]` task** —
  that ordering already respects every "Blocked by" dependency.
- **Before implementing:** open and read the linked slice file in `.scratch/reporting/`
  for the full spec and the acceptance-criteria checklist. Implement **exactly** that slice.
- **Build to the acceptance criteria**, including the named "catch-forever" tests. Drive
  tests through the real ASGI app over HTTP (`httpx.AsyncClient`) using the existing
  `backend/tests/conftest.py` fixtures (`make_client_account`, `add_product` with
  `cost_price`, `get_product_quantity`, …).
- **Aggregate in SQL / streaming — never load-everything** (respect OPS-05; F-048 is the
  precedent). All report endpoints are owner-scoped in the service layer (SEC-02) and
  windowed by date range.
- **Regression gate:** the full existing `backend/tests` suite must stay green. The F-068
  `cost_price`-on-sale-line snapshot must be behavior-preserving for the atomic sale. Run
  `pytest` (backend) and `pnpm run lint` / `pnpm run build` (frontend) as relevant.
- Every new screen renders loading / empty / error / permission / offline states, uses
  brand tokens, is translated across all four languages (ar/en/hi/ur) with RTL verified.
  Report PDFs render Arabic correctly regardless of UI language.
- When a slice's acceptance criteria are all met and tests pass: **tick its box to `- [x]`**,
  append a line to `progress.txt` (what shipped + commit SHA), and **commit** with the
  finding tag, e.g. `feat(rpt): F-068 — profit/COGS/margin report [F-068]`.
- **ONLY WORK ON A SINGLE TASK per iteration.**
- When every box below is `- [x]`, output `<promise>COMPLETE</promise>`.

## Tasks

- [x] **01 · F-068 — Profit / COGS / margin report + dead-stock** (`/reports/profit-margin`; snapshot cost_price onto the sale line) → `.scratch/reporting/01-F068-profit-margin-report.md` · Blocked by: none
- [x] **02 · F-069 — VAT summary by rate** (`/reports/vat-summary`; standard/zero/exempt, credit notes netted) → `.scratch/reporting/02-F069-vat-summary-report.md` · Blocked by: none
- [x] **03 · F-070 — Inventory report at cost + movements** (`/reports/inventory`; fix dashboard sale-price valuation) → `.scratch/reporting/03-F070-inventory-report.md` · Blocked by: none
- [x] **04 · F-071 — Refund/void + discount reports** (`/reports/refunds-voids`, `/reports/discounts`; actor/reason/amount) → `.scratch/reporting/04-F071-refund-void-discount-reports.md` · Blocked by: none
- [ ] **05 · F-072 — PDF export for every report** (generic fpdf2 RTL renderer + `?format=pdf` on all `/reports/*`) → `.scratch/reporting/05-F072-report-pdf-export.md` · Blocked by: 01, 02, 03, 04
