# F-071 — Refund/void report + discount report (who/when/why)

## Parent

`docs/prd/PRD-RPT-reporting-depth.md` — Reporting Depth (RPT core). Source finding F-071 (RPT-08).

## What to build

A manager cannot audit refunds/voids/discounts as a cross-period report with actor + reason — these totals appear only per-shift inside the Z-report. Generalize that logic across a window:

- **`GET /api/v1/reports/refunds-voids`** (owner-scoped, windowed): each refund and void with **actor, reason, amount, timestamp**, joining `audit_logs` / `transactions`.
- **`GET /api/v1/reports/discounts`** (owner-scoped, windowed): each discounted sale with **actor, reason/code, amount, timestamp**.
- Reuse / generalize the `_aggregate_zreport` refund/void/discount logic (`features.py:1376-1487`) from single-shift to a date window.
- CSV export; aggregate in SQL / streaming.

Frontend: Refunds/Voids and Discounts tabs on ReportsAnalytics with date-range + CSV download; typed `api.ts` wrappers; i18n ×4 with RTL.

## Acceptance criteria

- [ ] `GET /reports/refunds-voids` lists each refund/void with actor, reason, amount, timestamp over a window, owner-scoped.
- [ ] `GET /reports/discounts` lists each discounted sale with actor, reason/code, amount, timestamp.
- [ ] Both reuse/generalize the Z-report aggregation rather than forking new logic.
- [ ] CSV export works; aggregation in SQL/stream.
- [ ] Tests added and green: a void (with reason) and a discounted sale each appear with actor / reason / amount.
- [ ] Refunds/Voids and Discounts tabs render loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

None - can start immediately.
