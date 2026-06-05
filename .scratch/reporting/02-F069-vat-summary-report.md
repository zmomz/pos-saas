# F-069 — VAT / tax report (output VAT by rate)

## Parent

`docs/prd/PRD-RPT-reporting-depth.md` — Reporting Depth (RPT core). Source finding F-069 (RPT-05).

## What to build

A merchant filing a ZATCA VAT return has no report of output VAT by rate — `vat_amount` is a single aggregate line in the journal. Build a VAT summary:

- **`GET /api/v1/reports/vat-summary`** (owner-scoped, date-range windowed): aggregate transactions into **standard-rated (15%) / zero-rated (0%) / exempt** buckets, each with **taxable base + VAT amount**, matching the ZATCA VAT-return boxes.
- **Credit notes netted**: net VAT = collected − reversed (refunds/credit notes reduce the bucket).
- CSV export; aggregate in SQL / streaming.

Frontend: a VAT Summary tab on ReportsAnalytics with date-range + CSV download; typed `api.ts` wrapper; i18n ×4 with RTL.

## Acceptance criteria

- [ ] `GET /reports/vat-summary` returns standard-rated / zero-rated / exempt buckets, each with taxable base and VAT, over a date window, owner-scoped.
- [ ] Sales at 15% and 0% land in the correct buckets.
- [ ] Credit notes / refunds are netted: net VAT = collected − reversed.
- [ ] Buckets align with ZATCA VAT-return boxes.
- [ ] CSV export works; aggregation in SQL/stream.
- [ ] Tests added and green: sales at 15% and 0% split correctly; net VAT = collected − reversed.
- [ ] VAT Summary tab renders loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

None - can start immediately.
