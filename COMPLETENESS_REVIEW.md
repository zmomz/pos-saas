# COMPLETENESS_REVIEW.md — Code vs. Vision (Prompt 2 audit)

**What this is.** A prioritized backlog of *suspicions* — the gap between the running code and the market-parity vision in `srs.md` v2.0 + `INTENDED_BEHAVIOR.md`, traced end-to-end (`frontend control → src/lib/api.ts → atomsClient.ts → router → service → model → side effect`). It is **for human review and test-promotion, not a release gate.** Every confirmed finding cites `file:line` and states what was searched to rule out an alternate implementation.

**Method.** Audited all 20 feature families across 7 parallel deep traces, each with a mandatory refutation pass. Where the spec's own "suspected" status was **wrong**, that is recorded under Verified-complete so the spec can be corrected (notably: Alembic migrations, audit completeness, triad pagination, i18n key parity — all more built than the docs claim).

**Date:** 2026-06-03 · **Branch:** main · **Bar:** Foodics / Rewaa / Marn parity, localized for Saudi.

---

## 1. Summary table

Counts are against each family's SRS requirement IDs. ✅ implemented · ⚠️ partial/shallow · ❌ missing · ❓ unverifiable. "P0-gap" = P0 table-stakes not fully ✅.

| Family (SRS) | Items | ✅ | ⚠️ | ❌ | ❓ | Findings | P0-gap |
|---|---|---|---|---|---|---|---|
| MA — Master/Agent | 9 | 6 | 1 | 2 | 0 | 2 | 0 |
| AG — White-label | 10 | 4 | 2 | 4 | 0 | 3 | 0 |
| CL — Client/Billing | 11 | 4 | 2 | 5 | 0 | 2 | 0 |
| POS — Retail core | 14 | 6 | 3 | 5 | 0 | 8 | 4 |
| RST — Restaurant | 10 | 0 | 0 | 10 | 0 | 1 | 5 |
| PAY — Payments | 10 | 0 | 1 | 9 | 0 | 5 | 7 |
| INV — Inventory | 11 | 4 | 2 | 5 | 0 | 5 | 1 |
| CRM — Customers | 6 | 2 | 0 | 4 | 0 | 5 | 1 |
| PRC — Pricing | 6 | 0 | 1 | 5 | 0 | 2 | 1 |
| RPT — Reporting | 10 | 2 | 1 | 7 | 0 | 2 | 2 |
| FIN — Finance | 5 | 1 | 2 | 2 | 0 | 3 | 0 |
| OMN — Omnichannel | 5 | 0 | 0 | 5 | 0 | 1 | 0 |
| ZA — ZATCA | 10 | 6 | 2 | 2 | 0 | 5 | 1 (ZA-06) |
| RSL — Reseller econ | 8 | 1 | 1 | 6 | 0 | 3 | 1 (RSL-06) |
| L10N — Localization | 6 | 5 | 1 | 0 | 0 | 1 | 0 |
| HW — Hardware | 8 | 3 | 1 | 4 | 0 | 2 | 1 (HW-03) |
| SEC — Security | 8 | 5 | 1 | 1 | 1 | 2 | 0 |
| OPS — Operations | 8 | 4 | 3 | 1 | 0 | 3 | 1 (OPS-05) |
| UX — Design | 8 | 4 | 2 | 2 | 0 | 3 | 1 (UX-02) |
| PRN — Printables | 9 | 4 | 1 | 4 | 0 | 1 | 2 (PRN-05/09) |
| **Total** | **166** | **61** | **29** | **83** | **2** | **59** | **~27** |

> **The five biggest market gaps (drive the backlog):** (1) **PAY** Saudi tenders + terminal capture — today's "split payment" is a label, not a capture; (2) **RST** restaurant vertical — entirely absent; (3) **POS-07** partial/line refunds — whole-invoice only; (4) **RPT-06/04** Z-report + profit/COGS — absent; (5) **RSL-01 + CL-06 + AG-05/06** reseller depth — commission ledger, dunning, custom domain, branded email — absent. Plus **ZA-06** clearance-vs-reporting (a non-functional façade) and **OPS-05** report pagination.

---

## 2. Confirmed findings

Severity: `BLOCKER` (core flow unusable / P0 table-stake absent / compliance-blocking) · `MAJOR` (feature visibly incomplete or a step silently fails) · `MINOR` (edge/cosmetic) · `INFO`. Confidence: `HIGH`/`MEDIUM`/`LOW`.

### PAY — Payments (Saudi-real)

**F-001 — ✅ DONE — POS sale records payment-method LABELS only; no real terminal/gateway approval is ever captured** · `MISSING_SIDE_EFFECT` / `MARKET_GAP`
- **Fixed (gateway capture wired into the atomic sale):** a new pluggable gateway abstraction (`services/payment_gateway.py`: `PaymentGateway` ABC, deterministic `SandboxGateway`, real `MoyasarGateway` online adapter, `get_gateway()` resolver) is invoked inside `create_transaction` (`routers/pos.py::_capture_tenders`) for every card-like tender (mada/card/applepay/stcpay/tabby/tamara) **before the invoice counter is consumed**. A decline raises 402 and, since nothing has committed, rolls the whole sale back; an approval persists a `payment_tenders` row carrying the real network + approval_code + RRN + gateway_ref (no PAN — PAY-09). The sale response now returns the captured `tenders`, and the always-Arabic receipt prints the approval. Sandbox is the OPS-08 graceful-degradation default; Moyasar activates once `MOYASAR_API_KEY` + a client-side token are present (live-credential step flagged to the operator). Tests: `tests/test_phase2_payments.py::test_card_decline_blocks_sale_and_persists_nothing`, `::test_card_approve_captures_approval_on_tender`, `::test_split_card_plus_cash_captures_only_card_leg`, `::test_cash_sale_records_tender_without_gateway_approval`.
- Violated: PAY-05 (P0) *"push the amount to a connected Mada/card terminal and capture the approval onto the invoice; decline blocks the sale"*; PAY-01 (P0) *"the invoice records the network … and approval/RRN"*; IB §4.4 atomic step ③.
- Manifests: a cashier rings a "card"/"Mada" sale that completes with **zero proof a card was charged** — indistinguishable from cash; a decline cannot block the sale because no authorization is attempted. This is the single biggest POS gap.
- Evidence: `backend/routers/pos.py:312-329` (breakdown is label-only), `:354-370` (txn built with only `payment_method`/`payment_breakdown`); model has no tender fields `backend/models/transactions.py:18-22`; frontend sends labels only `frontend/src/pages/POSTerminal.tsx:385-401`, picker offers cash/card only `:1092-1093`. **Searched** backend for `approval|network|last4|capture|authorize|gateway_ref|acquirer`, repo for `mada|moyasar|geidea|tabby|tamara|terminal|rrn` → all hits are markdown/i18n/UI labels, none in capture code.
- Severity: **BLOCKER** · Confidence: HIGH
- Fix: Add a `payment_tenders` table + a gateway/terminal abstraction; for card/Mada tenders capture a real approval (Geidea SoftPOS in-store / Moyasar online) inside the atomic sale; decline → roll back.
- Catch forever: pytest — a card tender with a stub gateway returning DECLINE returns 4xx and persists no transaction; APPROVE stores non-null `approval_code`/`rrn`.

**F-002 — ✅ DONE (abstraction + online adapter; in-store terminal still F-005) — No Mada / Apple Pay / STC Pay / BNPL integration anywhere** · `MARKET_GAP`
- **Fixed (pluggable gateway layer + Saudi tender taxonomy + capture endpoint):** `services/payment_gateway.py` defines `SUPPORTED_TENDER_TYPES` (cash/card/**mada/applepay/stcpay/tabby/tamara**/transfer/loyalty) and `CARD_LIKE_TENDERS`; per-tender routing runs every card-like leg of a split through the gateway. New `routers/payments_gateway.py` exposes `GET /api/v1/payments/tender-types` (drives the POS picker) and `POST /api/v1/payments/charge` (terminal/online pre-auth surface). The **Moyasar** online adapter is the first real provider (selected by `MOYASAR_API_KEY`); Tap/HyperPay/PayTabs slot behind the same interface later. **In-store SoftPOS terminal capture (Geidea, PAY-05/HW-03) remains F-005** — the online gateways do not do in-store capture. Tests: `tests/test_phase2_payments.py::test_tender_type_enum_includes_saudi_tenders`, `::test_tender_types_endpoint_lists_saudi_tenders`, `::test_charge_endpoint_declines_then_approves`, `::test_charge_endpoint_rejects_cash`.
- Violated: PAY-01..04 (all P0) — Mada first-class, Apple Pay/STC Pay, Tabby/Tamara BNPL, split across all.
- Manifests: end customer cannot pay how Saudis pay; `PaymentEntry` accepts arbitrary method strings that never route to any provider.
- Evidence: `backend/routers/pos.py:46-50` (`PaymentEntry` = method+amount only); no `payments_terminal.py`/gateway adapter (full router listing confirmed); repo grep `moyasar|tabby|tamara|stc|apple|geidea` → only docs/i18n.
- Severity: **BLOCKER** · Confidence: HIGH
- Fix: Pluggable gateway layer (Moyasar online; Geidea in-store) with per-tender routing.
- Catch forever: pytest asserting a `/payments` capture endpoint exists and the tender-type enum includes mada/applepay/stcpay/tabby/tamara.

**F-003 — ✅ DONE (`payment_tenders`; `terminals`/`payment_accounts` deferred) — `payment_tenders`, `terminals`, `payment_accounts` models/tables absent** · `MISSING_SIDE_EFFECT`
- **Fixed (`payment_tenders` model + Alembic migration):** `models/payment_tenders.py` carries `tender_type/amount/network/approval_code/rrn/gateway_ref/last4/token/gateway/status/decline_reason` and **no `pan`/`card_number` column** (PCI minimization, PAY-09). Alembic revision `a1b2c3d4e5f6` (chained from `f5a6b7c8d9e0`) creates it; `alembic upgrade head` is clean on an empty DB. `terminals` (PAY-05/HW-03 in-store) and `payment_accounts` (PAY-06 per-client gateway creds) are deferred to F-005 / a follow-up — today the platform `MOYASAR_API_KEY` drives the single online gateway. Test: `tests/test_phase2_payments.py::test_payment_tenders_schema_carries_proof_but_no_pan`.
- Violated: IB §4.6 entities; srs.md §6 schema (`payment_accounts`, `terminals`); PAY-09 (P0) *"store only tokens/last-4/network"*.
- Manifests: without `payment_tenders`, PAY-09 PCI minimization and PAY-10 refund-to-origin are structurally impossible.
- Evidence: full `backend/models/*.py` listing has no tender/terminal/account model; `models/transactions.py:1-39` has no tender columns.
- Severity: MAJOR · Confidence: HIGH
- Fix: Add the three models (tenders carry token/last4/network/approval/rrn only — never PAN).
- Catch forever: pytest asserting `payment_tenders` has `approval_code/rrn/network/last4/token` and **no** `pan`/`card_number` column.

**F-004 — Refund does not route to the original tender** · `MISSING_SIDE_EFFECT`
- Violated: PAY-10 (P2) *"Refunds routed back to the original tender"*.
- Manifests: refund issues a credit note + restores stock + nets the shift (all real) but sets `payment_method="refund"` and never reverses any charge — money movement is fictional.
- Evidence: `backend/routers/pos.py:740-754` (no gateway call); backend grep `refund.*gateway|reverse|void.*charge` → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: Look up the original tender and call the gateway refund API; record a `refunded` tender row.
- Catch forever: pytest — refunding a card sale invokes the stub gateway's `refund(tender_ref)`.

**F-005 — Integrated payment terminal (HW-03) absent; cash-drawer kick (HW-04) absent** · `MARKET_GAP` / `DEAD_END_UI`
- Violated: HW-03 (P0) *"Integrated payment terminal"*; HW-04 (P1) drawer kick.
- Manifests: no terminal driver (same root as PAY-05); ESC/POS receipt emits no drawer-kick pulse, so a connected drawer never opens on cash sales.
- Evidence: no `payments_terminal.py` (router listing); grep `escpos.py`/`thermalPrint.ts` for `drawer|kick|pulse` → none.
- Severity: HW-03 **BLOCKER** / HW-04 MINOR · Confidence: HIGH
- Fix: HW-03 rides on the PAY-05 terminal SDK; HW-04 append `ESC p` pulse for cash tenders.
- Catch forever: pytest asserting cash-sale ESC/POS output contains the `0x1B 0x70` drawer-kick bytes.

**F-006 — Stripe Checkout router is orphaned (no caller)** · `ORPHAN_CODE`
- Violated: IB §8 orphan ledger; PAY-07 (P1) payment links.
- Evidence: `backend/routers/payment.py:44-72`; `frontend/src` grep `checkout|createCheckout` → none (subscription uses the `tenant.py` Connect path).
- Severity: MINOR · Confidence: HIGH
- Fix: Either wire as the PAY-07 payment-link surface or delete.
- Catch forever: CI lint flagging a backend endpoint with no `api.ts` wrapper.

### POS — Retail core

**F-007 — ✅ DONE — Refund is whole-invoice only; no partial, no line-level, no exchange** · `MISSING_TRANSITION` / `MARKET_GAP`
- **Fixed (partial & line-level refunds on the credit-note path):** `POST /pos/transactions/{id}/refund` now accepts an optional `RefundRequest` body `{lines:[{product_id, quantity}]}` (`routers/pos.py`). Omitting `lines` keeps the legacy whole-invoice refund; passing them credits only the selected units. The handler aggregates the original lines by SKU, sums already-refunded quantities from prior credit notes (new `transactions.original_transaction_id` link, Alembic `c3d4e5f6a7b8` chained from `b2c3d4e5f6a7`; `alembic upgrade head` clean on an empty DB) via `_refunded_quantities`, **validates each requested qty against the remaining balance** (over-refund → 400), restores **only the returned units** to the same stock pool (branch ledger or client-level), and prorates the order-level discount/VAT/total to the returned line subtotal (a full refund reproduces the original amounts exactly). The original lands in `refunded` when every line is fully returned, else **`partial_refunded`**; the credit note is still a real type-381 ECDSA-signed, hash-chained, always-Arabic ZATCA document referencing the original invoice. Frontend `POSTerminal.tsx` refund panel now parses `items_json` into line items and offers a per-line return-quantity stepper with a live refund amount + a "partial" indicator + a "partially refunded" badge; `refundTransaction(id, lines?)` in `api.ts` carries the selection. i18n keys added to all four locales (ar/en/hi/ur). Tests: `tests/test_phase2_zatca_sale.py::test_partial_refund_credits_one_unit_and_marks_partial_refunded`, `::test_successive_partial_refunds_complete_to_refunded`, `::test_partial_refund_rejects_over_quantity`. **Out of scope (separate findings):** refund-to-original-tender is F-004 (PAY-10); exchange is deferred (no test named it).
- Violated: POS-07 (P0) *"supporting partial and line-level refunds and exchanges"*; IB transaction-state `partial_refunded`.
- Manifests: `refund_transaction` takes only the txn id, clones the entire original, restores **all** stock, hard-sets `status="refunded"`; a cashier cannot return 1 of 5 units — they refund the whole invoice and re-ring, distorting sales/VAT/stock.
- Evidence: `backend/routers/pos.py:695-799` (no line/qty params), `models/transactions.py:23` (no `partial_refunded`); frontend renders the whole invoice as one refund button `POSTerminal.tsx:497-525`. Searched repo for `partial`/`exchange`/line-refund params → spec/tests only.
- Severity: **MAJOR** (P0) · Confidence: HIGH
- Fix: Add `lines:[{product_id,quantity}]` (+ optional exchange); credit/restore only selected lines; set `partial_refunded` when a balance remains.
- Catch forever: pytest — refund 1 of 3 units → credit-note total = 1 unit, stock +1, original status `partial_refunded`.

**F-008 — ✅ DONE — No Z-report / X-report endpoint or printable** · `MARKET_GAP` / `DESIGN_GAP`
- **Fixed (per-shift Z/X-report endpoint + always-Arabic printable):** new `GET /api/v1/reports/zreport?shift_id=` (`routers/features.py`, client-scoped via `get_user_role`) aggregates one shift's transactions (linked by `Transactions.shift_id`) into a structured report — **sales by tender** built from the real captured `payment_tenders` rows (F-001), not labels (legacy tender-less sales fall back to `payment_method`); gross/net sales; refunds (credit-note rows) + VAT reversed; VAT collected; discounts; voids (forward-compat for F-013); and a **cash-drawer reconciliation computed against cash tenders only** (`opening + cash_sales − cash_refunds`), so non-cash sales no longer inflate expected cash. Run against the open shift (omit `shift_id`) it returns an **X-report** (`report_type:"X"`, no counted cash yet); against a closed shift it is the **Z-report** (`"Z"`, with `counted_cash`/`variance`/`reconciliation`). A second endpoint `GET /api/v1/reports/zreport/document` renders the **always-Arabic** (RTL, Arabic-Indic digits, SAR) PRN-05 printable via `PDFInvoiceService.generate_zreport_html` — a management document explicitly marked *"ليس فاتورة ضريبية"* (not a tax invoice, no QR/stamp). Frontend: `getZReport`/`printZReport` in `api.ts`; `ShiftManagement.tsx` now **emits the Z-report on close** (auto-opens the printable from the close response id), plus an X-Report button on the active shift card, a per-history-row Z-report button, and a reprint-last-Z button; i18n keys (`z_report`/`x_report`/`print_z_report`/`print_last_z_report`) added to all four locales (ar/en/hi/ur). Tests: `tests/test_phase4_pos.py::test_zreport_groups_by_tender_and_reconciles_variance`, `::test_zreport_scopes_to_owner_and_404s_unknown_shift`. **Out of scope (separate findings):** the cash-blind math in `close_shift`'s own `expected_cash` (F-009 — the Z-report computes its own cash recon correctly but does not rewrite `close_shift`); refund-by-original-tender breakdown needs refund-to-origin (F-004 — refunds are treated as cash-out for drawer recon); the F-016 current/history field-mismatch in `ShiftManagement.tsx` still hides those reads (the close-flow Z-report works regardless); pay-in/out/cash-drop entries (FIN-04); the Reports-page Z-report panel (RPT-06 view in `ReportsAnalytics.tsx`) is not added — the shift-close path is the primary surface per IB §5.H.
- Violated: RPT-06 (P0) *"Z-report/X-report: tenders, VAT, discounts, voids, refunds, cash variance, payouts"*; PRN-05 (P0) printable.
- Manifests: `close_shift` returns a flat `{opening,closing,expected,difference}` only — no tender/VAT/void/refund breakdown, no printable, no mid-shift X-report. The highest-value reporting gap.
- Evidence: `backend/services/production.py:598-610`; repo grep `zreport|z-report|z_report|xreport|by_tender|tender` → spec files only; `ReportsAnalytics.tsx` no match.
- Severity: **MAJOR** (P0) · Confidence: HIGH
- Fix: `GET /reports/zreport?shift_id=` aggregating the shift's txns by tender/VAT/discount/void/refund + variance, plus an always-Arabic 80mm/A4 printable invoked on close.
- Catch forever: pytest — open shift, ring cash+card+refund, close → Z-report groups by tender and variance reconciles.

**F-009 — Shift `expected_cash` is cash-blind (counts card/split sales as drawer cash)** · `SPEC_DIVERGENCE`
- Violated: POS-09 (P0 `[market]`) drawer reconciliation; OPS-02 atomicity holds but the math is wrong.
- Manifests: `close_shift` computes `expected_cash = opening_cash + total_sales`, and `_apply_sale_to_open_shift` adds the **full invoice total** (incl. card/transfer/split) to `total_sales`; so expected cash is overstated by every non-cash sale → variance is always wrong when any non-cash sale occurs.
- Evidence: `backend/services/production.py:581`; `backend/routers/pos.py:231` called with `total_amount` at `:417`.
- Severity: MAJOR · Confidence: HIGH
- Fix: Reconcile the drawer against cash-tender legs only, not gross sales.
- Catch forever: pytest — ring 1 cash + 1 card sale, assert `expected_cash == opening + cash_portion_only`.

**F-010 — No hold/recall (park) of sales** · `MISSING_TRANSITION` / `MARKET_GAP`
- Violated: POS-10 (P1 `[market]`) *"Park/hold & recall … multiple concurrent open tickets"*; IB `held` state.
- Evidence: `pos.py` no hold/recall/park endpoints; `POSTerminal.tsx:69` cart is in-memory React state with no Hold button; `transactions.py:23` no usable held flow.
- Severity: MAJOR · Confidence: HIGH
- Fix: `POST /pos/hold` / `GET /pos/held` / `POST /pos/recall/{id}` persisting cart as a `held` transaction.
- Catch forever: pytest — hold a cart → lists under held; recall restores items and clears held.

**F-011 — No weighted / open-price items** · `MARKET_GAP`
- Violated: POS-11 (P1 `[market]`) weighted & open-price.
- Evidence: `pos.py:41` (`quantity:int`); `POSTerminal.tsx:192-200` (±1 stepper); price from product `:307`. Blocks grocery/butcher verticals.
- Severity: MINOR · Confidence: HIGH
- Fix: Allow fractional `quantity` (weight) and a per-line price override on `CartItem`.
- Catch forever: pytest — line qty 0.45 + custom price → subtotal = price × 0.45.

**F-012 — No tips capture** · `MARKET_GAP`
- Violated: POS-13 (P2 `[market]`) tips per tender, reportable.
- Evidence: no tip field in `CreateTransactionRequest` (`pos.py:53-72`), no column on transactions, no UI.
- Severity: MINOR · Confidence: HIGH
- Fix: Add `tip_amount` to the request + a column; exclude from VAT base; surface in Z-report.

**F-013 — No audited void-line / void-sale; `pos.void`/`pos.price_override` permissions enforced nowhere** · `MISSING_SIDE_EFFECT` / `DEAD_END_UI`
- Violated: POS-08 (P1) *"void line, void sale (audited), price override (permissioned)"*; IB §3.2 permission keys.
- Manifests: cart removal is silent client-side state — no audited void, no `voided` status; price override doesn't exist; the keys `pos.void`/`pos.price_override` are referenced in the spec but defined/enforced nowhere (only `pos.refund` is enforced at `pos.py:693`).
- Evidence: `POSTerminal.tsx:202` (`removeFromCart`); repo grep `pos.void`/`pos.price_override` → none.
- Severity: MAJOR (fraud-control + SEC-07 tie) · Confidence: HIGH
- Fix: `POST /pos/transactions/{id}/void` (status `voided` + audit) gated by `require_permission("pos.void")`; price override gated by `pos.price_override`.
- Catch forever: pytest — void without `pos.void` → 403; with it → status `voided` + audit row.

**F-014 — Offline queue has no cap and syncs the entire backlog in one request** · `MISSING_SIDE_EFFECT`
- Violated: POS-12 (P0 `[market]`) *"offline cap … (≥500 queued sales; deterministic conflict handling)"*.
- Manifests: unbounded IndexedDB growth on a long outage; one giant sync payload. (Dedup-by-`offline_id` and same-atomic-path replay **do** work.)
- Evidence: `frontend/src/lib/offlineQueue.ts:54-71,117`; `backend/services/production.py:1127-1168` iterate full list, no cap; grep `500|cap|MAX` → none.
- Severity: MINOR · Confidence: HIGH
- Fix: Ring-buffer cap (≥500) on enqueue; chunk sync into server-side batches.
- Catch forever: pytest — enqueue 501 sales → queue capped / oldest evicted.

**F-015 — POSTerminal: no offline banner; products-load error masquerades as empty** · `DESIGN_GAP`
- Violated: UX-02 (P0) / IB §5.E offline + error states.
- Manifests: `isOnline()` exists but POSTerminal renders no connectivity indicator (offline notice only appears after a failed checkout); `loadProducts` swallows errors to `console.error` and shows the empty state — a fetch failure looks like "no products."
- Evidence: `POSTerminal.tsx:161-165,639`. (loading/empty/refund-permission states **do** exist.)
- Severity: MINOR · Confidence: HIGH
- Fix: Persistent offline badge + an error state distinct from empty when `loadProducts` throws.
- Catch forever: Playwright — mock products-fetch rejection → error state, not empty state.

**F-016 — ShiftManagement reads a response shape the endpoint doesn't return** · `SPEC_DIVERGENCE` (live bug)
- Violated: POS-09 / UX correctness.
- Manifests: frontend checks `currentRes.data.id` but `GET /shifts/current` returns `{status, shift:{...}}` → an open shift **never displays as active**; history maps `difference/sales_total/opened_at` but API returns `cash_difference/total_sales/start_time` → money columns blank.
- Evidence: `frontend/src/pages/ShiftManagement.tsx:54-55,218-224` vs `backend/services/production.py:632-644,672-677`.
- Severity: MAJOR · Confidence: HIGH
- Fix: Unwrap `res.data.shift`; map snake_case fields.
- Catch forever: component test with the real endpoint shape → "Active" badge + populated history.

### ZA — ZATCA compliance

**F-017 — ✅ DONE — B2B clearance vs B2C reporting is never routed; everything is reported, clearance unreachable on the sale path** · `STUB_TODO` (façade)
- **Fixed (ZA-06 routing):** `services/zatca_sale.py` now classifies each document `standard` (buyer VAT present **AND** total ≥ 1,000 SAR) vs `simplified` (B2C, and B2B < 1,000 SAR) via `classify_invoice_subtype`, stamps the UBL subtype marker (`0100000`/`0200000`), persists `invoice_subtype` on `zatca_documents` (new column + Alembic `f5a6b7c8d9e0`), and the decoupled reporting job derives `clearance=(subtype=="standard")` so standard invoices are **cleared** and simplified ones **reported**. Buyer VAT threads from the txn (`getattr(...,"customer_vat_number")`) on sale/offline/refund paths — F-018 supplies that field. Tests: `tests/test_phase2_zatca_sale.py::test_classify_invoice_subtype_routing`, `::test_b2b_invoice_is_classified_standard_and_cleared`, `::test_b2c_invoice_is_classified_simplified_and_reported`, `::test_b2b_below_threshold_is_reported_not_cleared`.
- Violated: ZA-06 (P0) *"B2B standard invoices cleared in real time; B2C simplified reported within 24h … do not route purely on buyer type"*.
- Manifests: a merchant selling to a VAT-registered business issues a "standard" invoice that ZATCA law requires be **cleared before it's valid** — instead it's reported (or sits pending), making it legally non-compliant for B2B.
- Evidence: sale + refund call `report_document_background(...)` → `report_document(... )` with **no `clearance` arg** → defaults `clearance=False` → `/invoices/reporting/single` (`backend/services/zatca_sale.py:279`); `invoice_type_code` hardcoded `"388"`/`"381"` (`zatca_sale.py:101`, `pos.py:768`); no 1,000-SAR threshold logic; clearance only reachable via manual `POST /zatca/invoices/{id}/report?clearance=true` (`zatca.py:382-424`). Searched `clearance|standard|simplified|1000|is_b2b|invoice_type_code=` → clearance only ever `False` outside the manual endpoint.
- Severity: **BLOCKER** (compliance) · Confidence: HIGH
- Fix: Compute invoice type from buyer-VAT-present **AND** total ≥ 1,000 SAR in `sign_transaction`, store on the doc, pass `clearance=(type=="standard")` through the report chain.
- Catch forever: pytest — B2B sale ≥ 1,000 SAR drives `submit_invoice(clearance=True)` → `status="cleared"`; B2C → `status="reported"`.

**F-018 — ✅ DONE — No buyer VAT captured or rendered → B2B standard invoices are structurally impossible** · `MISSING_SIDE_EFFECT`
- **Fixed (buyer VAT captured on the sale path + rendered into every buyer block):** `customers.vat_number` (CRM-01) and `transactions.customer_vat_number` are added (Alembic `b2c3d4e5f6a7`, chained from `a1b2c3d4e5f6`; `alembic upgrade head` clean on an empty DB). `CreateTransactionRequest` gains `customer_vat_number`; `create_transaction` resolves the buyer VAT from the explicit field **or** the selected customer's saved record (trusted, user-scoped) and stamps it onto the transaction — so a sale tagged only with `customer_id` for a VAT-registered customer routes to B2B clearance with no re-typing. The captured VAT threads into `sign_transaction` (already wired by F-017), the UBL buyer `cac:AccountingCustomerParty//cac:PartyTaxScheme/cbc:CompanyID` (emitted only when present), and the **always-Arabic** A4 PDF (`pdf_render.py`, Arabic + Latin), the HTML invoice (`production.py::generate_invoice_html`), and the credit-note path (inherits the original sale's buyer VAT). Customer triad schemas + `CustomerManagement.tsx` (form field + table column) + `api.ts` wrappers carry `vat_number`. Tests: `tests/test_phase2_zatca_sale.py::test_b2b_sale_captures_buyer_vat_into_xml_and_invoice`, `::test_buyer_vat_resolved_from_saved_customer_record`, `::test_b2c_sale_has_no_buyer_vat_block`, `::test_pdf_buyer_block_renders_vat_when_present`. **Also closes F-037** (same root — the customer VAT field + triad + form + buyer-block flow).
- Violated: ZA-06 / PRN-02 *"buyer block (B2B: name/VAT)"* / CRM-01 (P0) customer VAT number.
- Manifests: `buyer_vat` is hardcoded `""` on the sign call; `customers` model has no `vat_number`; `transactions` carries only `customer_name`. The UBL builder emits a buyer `PartyTaxScheme` only `if buyer_vat:` — never truthy. A4 PDF renders buyer name only.
- Evidence: `backend/services/zatca_sale.py:134`; `backend/routers/zatca.py:329`; `backend/models/customers.py` (no vat); `backend/models/transactions.py:27`; `backend/services/production.py:292`; `backend/services/pdf_render.py:102-105`. (Same root as **F-029**.)
- Severity: **MAJOR** · Confidence: HIGH
- Fix: Add `vat_number` to `customers` + `customer_vat_number` to `transactions`; thread into `sign_transaction`, UBL, PDF buyer block.
- Catch forever: pytest — a B2B sale produces XML with `cac:AccountingCustomerParty//cbc:CompanyID == <vat>` and the PDF shows it.

**F-019 — No ZATCA document-status dashboard or stuck-pending/failed alerting** · `MISSING_ENDPOINT` / `DESIGN_GAP`
- Violated: ZA-08 (P1) *"a dashboard of documents by status … with alerts on stuck pending/failed"*.
- Manifests: a merchant whose invoices are silently stuck at `pending` (unconfigured gateway) or `failed` (4xx) has no UI and no alert — discovers non-compliance only at audit.
- Evidence: no `frontend/src/**/*zatca*` page; `backend/routers/zatca.py:430` returns a flat list; grep `by.?status|status_counts|stuck|alert` → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: `GET /zatca/documents/summary` (counts by status) + a `ZatcaStatus.tsx` page + a notification when pending/failed > 0.
- Catch forever: pytest — endpoint returns status counts; a sale made unconfigured increments `pending`.

**F-020 — ✅ DONE — No retry/reconcile job for stuck `pending` documents; fail-closed is a dead end** · `MISSING_SIDE_EFFECT`
- **Fixed (reconcile sweep over the stuck backlog):** `services/zatca_sale.py::report_pending_documents(db, client_id)` selects every document whose status is `pending`/`failed` (in `icv` order) and resubmits each through the existing `report_document` — so the **same ZA-06 routing** is preserved (`standard` → clearance, `simplified` → reporting, derived from the stored `invoice_subtype`). It returns a `{processed, cleared, reported, pending, failed}` summary, runs inside the caller's transaction, and is idempotent (already cleared/reported docs aren't selected; an un-onboarded gateway just leaves them `pending` again). New client-scoped endpoint `POST /api/v1/zatca/documents/report-pending` (`routers/zatca.py`) gates on completed production onboarding (400 otherwise) and commits the batch once. This turns the previous single-shot, fail-closed-forever behavior into a recoverable backlog the operator can drain after onboarding. (Backend reconcile job only — the ZA-08 status **dashboard** that would surface a "Reconcile" button remains F-019.) Tests: `tests/test_phase2_zatca_sale.py::test_report_pending_sweep_resubmits_stuck_documents`, `::test_report_pending_clears_standard_b2b_documents`, `::test_report_pending_requires_onboarding`.
- Violated: ZA-06 (P0) *"background job, retry"* + ZA-08.
- Manifests: reporting fires once via `BackgroundTasks` at sale time. On a default (un-onboarded) install the doc → `pending` and is **never resubmitted**, even after onboarding completes, unless the operator manually hits the per-document endpoint for each one.
- Evidence: `backend/services/zatca_sale.py:254-282` (single-shot); `backend/routers/pos.py:434,776`; grep `retry.*pending|reconcile.*pending` → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: `POST /zatca/documents/report-pending` (or startup/cron sweep) batch-resubmitting all pending/failed docs once onboarded.
- Catch forever: pytest — pending docs unconfigured → onboard → run sweep → flip to reported/cleared.

**F-021 — Thermal receipt (PRN-01) is not Arabic; labels English/transliterated, glyphs dropped** · `SPEC_DIVERGENCE`
- Violated: L10N-06 (P0) *"All fiscal documents render in Arabic regardless of UI language"*; PRN-01 item `name_ar`.
- Manifests: the most-printed B2C document prints `"Invoice:"`/`"Subtotal:"`/`"TOTAL (SAR):"` in English and encodes `cp437`/`replace`, mangling Arabic names to `?`. (The A4 PDF and HTML invoice **are** genuinely always-Arabic; the QR TLV is correct.)
- Evidence: `backend/services/escpos.py:37,113-143`; docstring `:9-14` concedes it.
- Severity: MAJOR · Confidence: HIGH
- Fix: Render Arabic labels via raster/bitmap (`GS v 0`) or CP1256; use `name_ar`; keep QR as-is.
- Catch forever: pytest asserting the receipt byte stream contains Arabic glyphs (image/CP1256), not ASCII `"Invoice:"`.

**F-022 — `zatca_enabled` per-client flag is unused; ZATCA signs every sale unconditionally** · `STUB_TODO`
- Violated: ZA-09 (P1) *"Per-client `zatca_enabled` policy is explicit and intentional … and the UI reflects it"*.
- Manifests: `clients.zatca_enabled` exists and is set `False` on provisioning but never read; signing is de-facto always-on while a column + an agent toggle advertise an opt-in that does nothing.
- Evidence: `backend/models/clients.py:27`; `backend/routers/tenant.py:635,670` (set, never read); `pos.py` `require_feature` only gates email/sms receipts (`:957,987`); `AgentDashboard.tsx:130` toggle maps to no enforcement.
- Severity: MINOR · Confidence: HIGH
- Fix: Decide always-on (drop flag + toggle) or honor it (`require_feature("zatca")`); make the UI reflect the real policy.
- Catch forever: pytest asserting the chosen policy holds (always-signed, or flag-off → no `zatca_documents` row).

### MA / AG / CL / RSL — Tenancy, white-label, billing, reseller economics

**F-023 — MA-08 platform economics endpoint absent (MRR/churn/revenue-by-agent)** · `MARKET_GAP`
- Violated: MA-08 / RSL-08 / RPT-09 (P1) master economics.
- Evidence: `tenant.py` master routes stop at agents/slots/tax-rate (219-421); repo grep `economics` → docs only; `MasterDashboard.tsx` grep `MRR|churn|economics` → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: `GET /tenant/master/economics` aggregating `subscription_payments` + a KPI panel.
- Catch forever: pytest — endpoint 200 with `mrr/churn/by_agent` for master, 403 for agent/client.

**F-024 — MA-07 packages are slot-counts only; no feature-entitlement tier** · `MARKET_GAP`
- Violated: MA-07 (P1) package → feature-tier mapping.
- Evidence: `models/packages.py:10-16` (slots/prices only); `tenant.py:308-313` reads `client_slots` only; `client_features` set ad hoc unrelated to package (`tenant.py:646-655`).
- Severity: MINOR · Confidence: HIGH
- Fix: Add `features`/`feature_tier` to `Packages`; seed `client_features`/`agent_features` from it on provisioning.
- Catch forever: pytest — provision via a package with a feature set → resulting `client_features` match the tier.

**F-025 — AG-05 custom domain / AG-06 branded email / AG-07 branded printables all absent** · `MARKET_GAP`
- Violated: AG-05/06/07 (P1, table-stakes for Product B).
- Manifests: white-label is colors/logo/font/radius/lang only; clients can't be served under the agent's domain, provisioning email isn't agent-branded, printables aren't agent-branded.
- Evidence: `models/agents.py:1-28` (no domain/email fields); `BrandingResponse`/`BrandingUpdateRequest` carry colors/logo/font/radius/lang only (`tenant.py:79-88`, `features.py:432-449`); repo grep `custom_domain|email_template` → docs only. (`receipt_templates` exists but has no UI — see Orphan ledger.)
- Severity: MAJOR · Confidence: HIGH
- Fix: Add `custom_domain` + `email_template_id` to `Agents`, a domain-verify endpoint, and route provisioning/receipt rendering through agent templates.
- Catch forever: pytest — a request with the agent's `Host` resolves agent branding; provisioning email uses the agent template.

**F-026 — AG-03 feature gating real but only 3 keys enforced; the rest are cosmetic switches** · `PARTIAL_CRUD` / `STUB_TODO`
- Violated: AG-03 (P1) *"the toggle actually gates the capability server-side"*; IB §3.2 enumerated keys.
- Manifests: `require_feature` genuinely enforces only `email_receipts`, `sms_receipts`, `loyalty`; any other toggled feature (`restaurant`/`inventory`/`discounts`/`zatca`/`omnichannel`) is stored but never checked.
- Evidence: only `require_feature(` matches are `pos.py:957,987` + `production.py:688,736`; `tenant.py:711-760` accepts any `feature_name` string.
- Severity: MAJOR · Confidence: HIGH
- Fix: Constrain `feature_name` to an enum; add `require_feature(...)` to the routes each enumerated key governs.
- Catch forever: pytest — disable each enumerated feature → governed route returns 403.

**F-027 — CL-02 business_type (retail/restaurant/both) never captured or persisted** · `MARKET_GAP` / `MISSING_TRANSITION`
- Violated: CL-02 (P0) *"Client picks language and business type during first-login setup"* (drives POS mode).
- Evidence: no `business_type` on `Clients` (`models/clients.py`); not in `CreateClientRequest` (`tenant.py:90-98`); `ForceResetPassword.tsx:69-103` collects language + passwords only; repo grep `business_type` → docs only.
- Severity: MAJOR · Confidence: HIGH
- Fix: Add `business_type` to `Clients` + provisioning request + a force-reset radio; gate restaurant routes on it.
- Catch forever: pytest — provisioning persists `business_type`; force-reset can set it.

**F-028 — CL-06 dunning, CL-07 proration, CL-08 merchant invoice, CL-10 usage add-ons, CL-11 trial absent; CL-09 shallow** · `MARKET_GAP`
- Violated: CL-06..11 (P1); PRN-08/09 (subscription invoice / dunning).
- Manifests: `subscription_billing.py` does a single synchronous charge — no retry schedule, no `dunning` state, no reminder emails, no proration on plan change, no merchant-invoice PDF, no trial provisioning; CL-09 is a last-24-payments list with no downloadable invoices.
- Evidence: `backend/services/subscription_billing.py:41-86`; `update_client_subscription` overwrites fee with no proration (`tenant.py:944`); `models/clients.py:18-19` status comment lists only active/past_due/suspended; repo grep `dunning|prorat|trial` → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: Dunning job (scheduled retries → reminder → suspend), proration math on plan change, PRN-08 invoice renderer.
- Catch forever: pytest — a failed charge walks `past_due → (retry) → suspended`; a mid-cycle plan change emits a prorated adjustment.

**F-029 — RSL-01 commission/revenue-split ledger absent; no split computed on pay** · `MARKET_GAP` / `MISSING_SIDE_EFFECT`
- Violated: RSL-01..04 (P1) — the central Product-B gap.
- Manifests: `pay_client_subscription` writes only a `Subscription_payments` (gross fee) row; no `commission_ledger`, no master_cut/agent_net; `AgentDashboard.tsx:134` computes `sum(subscription_fee)` client-side (gross, no margin).
- Evidence: repo grep `commission` → docs only; no `commission_ledger.py`; `tenant.py:922-933`.
- Severity: MAJOR · Confidence: HIGH
- Fix: Add `commission_ledger`; on each pay compute the split from package wholesale vs client fee; add `/tenant/agent/revenue` + master rollup.
- Catch forever: pytest — a paid subscription writes one ledger row with `master_cut + agent_net == gross`.

**F-030 — RSL-05 impersonation, RSL-06 agent password-reset, RSL-07 merchant health, RSL-08 economics absent** · `MISSING_ENDPOINT` / `MARKET_GAP`
- Violated: RSL-05 (P1), **RSL-06 (P0)** agent resets a client's password, RSL-07/08 (P1).
- Manifests: no `/impersonate`; no agent-initiated password-reset endpoint (the only "reset" is the authenticated first-login `change-password` driven by `must_change_password` — not RSL-06); no merchant-health signals; economics absent (F-023).
- Evidence: repo grep `impersonat` → none; `routers/` grep `forgot|reset.password` → none; `AgentDashboard.tsx` grep `impersonate|log.?in.?as` → none.
- Severity: MAJOR (RSL-06 is P0) · Confidence: HIGH
- Fix: Audited scoped-token `POST /tenant/agent/clients/{id}/impersonate`; agent `POST …/reset-password` (new temp pwd); health fields on the clients response.
- Catch forever: pytest — impersonate yields a token scoped to that client + an audit row; non-owning agent → 403/404; agent reset-password sets `must_change_password`.

**F-031 — `features.py::get_user_role` defaults an unknown account to `master` (privilege divergence)** · `SPEC_DIVERGENCE` (security)
- Violated: SEC-02 (P0) least-privilege; IB §3.1 *"any authenticated account with no agent/client row … is a client scoped to itself — a self-registered user can never become master."*
- Manifests: `features.py:40` returns `role="master"` for an unknown account, **opposite** to `tenant.py:201-204` (defaults → `client`). `packages` CRUD is gated only by this check (`features.py:818-820`), so a self-registered user with no agent/client row could be treated as master for `/api/v1/packages/*`.
- Evidence: `backend/routers/features.py:28-40` vs `backend/routers/tenant.py:199-204`.
- Severity: MAJOR · Confidence: MEDIUM (exploitability depends on whether a non-admin account can exist with no agent/client row, e.g. `ALLOW_REGISTRATION=true`).
- Fix: Make `features.py::get_user_role` mirror `tenant.py` (unknown → client; master only when `User.role=='admin'`).
- Catch forever: pytest — a registered user with no agent/client row gets 403 from `GET /api/v1/packages/list`.

### INV — Inventory & catalog depth

**F-032 — Stock-transfer dialog posts to a non-existent endpoint (dead-end)** · `DEAD_END_UI`
- Violated: INV-05 (P1) stock transfers send/receive + audit; IB §5.I.
- Manifests: `BranchManagement.tsx` has a full Transfer Stock dialog that POSTs to `/api/v1/production/branches/transfer` — **no such route exists** → 404 on click. No `stock_transfers` model/state/audit.
- Evidence: `frontend/src/pages/BranchManagement.tsx:168-176`; backend grep `branches/transfer|def transfer` → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: Add `POST /production/branches/transfer` (atomic source−/dest+ on `product_branch_stock`) + a `stock_transfers` audit row.
- Catch forever: pytest — transfer N units → source−N/dest+N + a transfer record; plus a test asserting every frontend `apiCall.invoke` URL resolves to a backend route.

**F-033 — No product variants / matrix** · `MARKET_GAP`
- Violated: INV-04 (P1) variants, each a sellable SKU with own barcode/stock.
- Evidence: no `product_variants` model/triad/UI; repo grep `variant` → no variant feature; `ProductManagement.tsx` has no variants link.
- Severity: MAJOR · Confidence: HIGH
- Fix: `product_variants` triad + a matrix editor; POS resolves scans to variant SKUs.
- Catch forever: pytest — a 2-variant product exposes 2 scannable barcodes with independent stock decrement.

**F-034 — PO receive: no partial receipt, writes client-level qty (not branch ledger), overwrites cost (no moving-average COGS)** · `PARTIAL_CRUD` / `MISSING_SIDE_EFFECT`
- Violated: INV-07 (P0) *"receive (full/partial) into a branch, set cost, update COGS"*; INV-09 (P1) moving-average/FIFO.
- Manifests: receive increments `Products.quantity` (client-level), so stock never lands in the per-branch ledger the POS deducts from; it's all-or-nothing; cost is a flat overwrite → margin reports untrustworthy. (Idempotency guard is correct.)
- Evidence: `backend/routers/purchase_orders.py:277-295` (`Products.quantity + qty`, `cost_price=cost`, status→`received`); idempotent guard `:263-264`.
- Severity: MAJOR · Confidence: HIGH
- Fix: Receive into `product_branch_stock` for a chosen branch; support partial → `partially_received`; compute moving-average cost.
- Catch forever: pytest — receive 5 at C₁ then 5 at C₂ → branch +10, status partial→received once, cost = weighted average.

**F-035 — No reorder points / auto-PO; low-stock is a fixed threshold** · `MARKET_GAP`
- Violated: INV-08 (P1) reorder points per product/branch + auto-PO suggestion.
- Evidence: `features.py:279-322,391-425` (fixed `?threshold=`); repo grep `reorder` → none.
- Severity: MINOR · Confidence: HIGH
- Fix: Add `reorder_point` (+ per-branch) to products; alert/suggest-PO when on-hand ≤ reorder_point.

**F-036 — No stock counts / adjustments with reasons → variance** · `MARKET_GAP`
- Violated: INV-06 (P1) counts/adjustments (count/wastage/damage) → variance record.
- Evidence: no `stock_counts`/`stock_adjustments` model; only the **deprecated** `POST /inventory/deduct` (`features.py:350`, `deprecated=True`) mutates stock with no reason/variance/audit.
- Severity: MINOR · Confidence: HIGH
- Fix: `stock_counts`/`stock_adjustments` triad capturing reason + system vs counted → variance.

### CRM / PRC — Customers, loyalty, pricing

**F-037 — ✅ DONE (with F-018) — Customer record has no VAT number (blocks B2B clearance)** · `MISSING_SIDE_EFFECT`
- **Fixed with F-018:** `customers.vat_number` added to the model + triad schemas (`routers/customers.py`) + `CustomerManagement.tsx` form/table + `api.ts` `createCustomer`; it resolves onto the sale's `customer_vat_number` and flows into the invoice buyer block. See F-018 for the full description and tests.
- Violated: CRM-01 (P0) customer VAT number for B2B invoices. (Same root as F-018; tracked here for the CRM family.)
- Evidence: `backend/models/customers.py:6-19` (no `vat_number`); `CustomerManagement.tsx` no field. (`clients`/`suppliers` models DO have vat_number — only the customer is missing it.)
- Severity: MAJOR · Confidence: HIGH
- Fix: Add `vat_number` to `Customers` + triad + form; flow into the invoice buyer block.
- Catch forever: pytest — a B2B sale renders the customer VAT in the invoice/clearance payload.

**F-038 — No gift cards / store credit (and no gift-card tender)** · `MARKET_GAP`
- Violated: CRM-03 (P1) issue/redeem/balance/expiry; PRC-05 (P1) gift-card tender.
- Evidence: no `gift_cards`/`store_credit` model; repo grep → none.
- Severity: MINOR · Confidence: HIGH
- Fix: `gift_cards` triad (balance/expiry) + a gift-card tender path in `pos.py`.

**F-039 — No customer segments/tags/LTV; no SMS/WhatsApp marketing** · `MARKET_GAP`
- Violated: CRM-04 (P1) segments/tags/RFM; CRM-05 (P1) consent-aware campaigns.
- Evidence: `models/customers.py` no tags/segment; repo grep `campaign|whatsapp` → none.
- Severity: MINOR · Confidence: MEDIUM (searched `campaign`/`whatsapp`/segment terms; transactional SMS may exist but no campaign feature).
- Fix: Customer tags + computed LTV; a campaigns feature with consent gate (ties to SEC-05 PDPL).

**F-040 — Discount rules enforced only client-side; usage caps never applied** · `MISSING_SIDE_EFFECT`
- Violated: PRC-01 (P0) *"min-purchase, validity, usage caps, permissioned"*.
- Manifests: `discounts` triad is pure CRUD; POSTerminal computes %/flat client-side and sends a raw `discount_amount`; the backend never validates the discount, never checks `max_uses`, never increments `usage_count` — caps are unenforceable and the amount is client-trusted.
- Evidence: `backend/routers/discounts.py:93-331` (CRUD only); `backend/routers/pos.py:268` (`discount_amount` taken as given); `frontend/src/pages/POSTerminal.tsx:272-313`; grep `usage_count|max_uses` in pos.py → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: `POST /discounts/validate` (server-side type/min/validity/max_uses); increment `usage_count` atomically in the sale; gate manual amounts behind `pos.discount`.
- Catch forever: pytest — a `max_uses=1` discount is rejected on the 2nd sale; `usage_count` increments exactly once per applied sale.

**F-041 — No coupons/auto-promos, BOGO/bundle, price lists, scheduled pricing** · `MARKET_GAP`
- Violated: PRC-02/03/04 (P1), PRC-06 (P2).
- Evidence: no `promotions`/`coupons`/`price_lists` models; repo grep `coupon|price_list|bogo|bundle` → none.
- Severity: MINOR · Confidence: HIGH
- Fix: Promotions engine (time-window auto-apply, BOGO/qty-break) + price_lists keyed by customer/segment/branch.

### RPT / FIN — Reporting & finance

**F-042 — Reports: no payment-breakdown, margin/COGS, VAT, inventory, refund/discount, economics; no PDF export** · `MARKET_GAP`
- Violated: RPT-03 (P0), RPT-04/05/07/08/09 (P1), RPT-10 (P1) *"CSV + PDF for every report"*.
- Manifests: only three report endpoints exist (`sales-summary`, `top-products`, `export-csv`); `ReportsAnalytics.tsx` has no panels for the rest and no PDF export (reports are CSV-only; PDF exists only for invoices). Margin is also blocked by F-034 (no real valuation).
- Evidence: backend `/reports/` grep → exactly `features.py:517,581,644`; `ReportsAnalytics.tsx` grep `payment-breakdown|margin|vat|economics|jspdf|PDF` → none.
- Severity: MAJOR · Confidence: HIGH
- Fix: Add `/reports/payment-breakdown|margin|vat|inventory|refunds|discounts|economics` + PDF render for each.
- Catch forever: pytest — payment-breakdown sums tenders to total revenue; VAT report groups output VAT by rate.

**F-043 — No accounting/journal (GL) export; no Zoho/QB/Odoo; no AP** · `MARKET_GAP`
- Violated: FIN-02 (P1) GL/journal CSV; FIN-03/05 (P2).
- Manifests: `bulk_export` dumps raw entity CSVs only — not a journal with sales/VAT/COGS/payment lines; no integrations; no payable ledger.
- Evidence: `backend/routers/production.py:880-963` (entity dump only); repo grep `journal|general_ledger|zoho|quickbooks|odoo|accounts_payable` → none.
- Severity: MINOR (FIN-02 P1, rest P2) · Confidence: HIGH
- Fix: GL/journal CSV endpoint (debit/credit for sales/VAT/COGS/payments by period).
- Catch forever: pytest — journal export balances (Σdebits = Σcredits).

**F-044 — FIN-01 expenses lack attachment + client-side revenue view; FIN-04 cash management not tied to shift** · `PARTIAL_CRUD`
- Violated: FIN-01 (P1) attachment + revenue-vs-expense; FIN-04 (P1) drawer movements/payouts/petty-cash tie to shift.
- Manifests: `Expenses` has no `attachment` field; revenue-vs-expense is computed in the browser over `getTransactions(1,1000)` (won't scale, double-counts refunds); no pay-in/pay-out/cash-drop entries scoped to a shift.
- Evidence: `backend/models/expenses.py:6-17` (no attachment, no shift_id); `frontend/src/pages/ExpenseTracking.tsx:68-74`; shift router has no pay-in/out route (`production.py:518-680`).
- Severity: MINOR · Confidence: MEDIUM (did not exhaustively read the shift service).
- Fix: `attachment_url` on expenses (reuse storage); server-side revenue-vs-expense excluding refunds; drawer-movement entries scoped to the open shift, folded into Z/X close.

### RST / OMN — Vision verticals (entirely absent)

**F-045 — Restaurant operations vertical entirely absent** · `MARKET_GAP`
- Violated: RST-01..10 (RST-01/02/03/05/06 are P0), HW-06 (P1), PRN-06 (P1). Half the "unified retail + restaurant" promise.
- Manifests: a restaurant client cannot map a floor, open a table, fire a KOT, attach modifiers, or run dine-in/takeaway/delivery. POSTerminal is retail-only; there is **no `business_type` discriminator** anywhere, so the terminal cannot switch into restaurant mode.
- Evidence: no `restaurant.py`/`tables.py`/`kds.py`/`modifiers.py` router; no tables/order_ticket/modifier/combo/prep_station model; no `FloorMap.tsx`/`KDS.tsx`; grep `restaurant|order_ticket|prep_station|modifier|combo|aggregator|kds|kot|floor|seat|course|business_type|dine.?in|takeaway` → only docs + false positives (`Math.floor`, `combobox.tsx`, "log aggregators" comment, "receipt delivery").
- Severity: **BLOCKER** for any restaurant client (5 P0s) · Confidence: HIGH
- Fix: Add `business_type` to the client model; stand up the first restaurant slice (tables + floor map + KOT routing) behind `require_feature("restaurant")`.
- Catch forever: a parity test asserting a restaurant client gets a `/api/v1/restaurant/tables` route (today 404).

**F-046 — Omnichannel (Salla/Zid/channel orders) entirely absent** · `MARKET_GAP`
- Violated: OMN-01..05 (P1/P2).
- Evidence: grep `salla|zid|channel_order|omnichannel|click.and.collect` → docs only; `integrations.py` is CSV bulk-import + search only.
- Severity: MAJOR (P1 differentiator family) · Confidence: HIGH
- Fix: `channel_orders` model + a Salla webhook-ingest endpoint as the first connector; decrement the shared branch stock.
- Catch forever: contract test — a sample Salla order webhook materializes a transaction + decrements stock.

### HW — Hardware

**F-047 — Customer display never receives `name_ar` or business name; HW-07 scale & HW-08 label printer absent** · `DEAD_END_UI` / `MARKET_GAP`
- Violated: HW-05 (P1) bilingual/branded display; HW-07 (P2) scale; HW-08 (P2) label printer.
- Manifests: `CustomerDisplay.tsx` reads `item.name_ar` + `display.businessName`, but the POS writer emits only `{name, quantity, price}` and a hardcoded `'POS System'` header → items render English-only, header unbranded (breaks RTL + white-label on the second screen). Scale & label printer have no code.
- Evidence: writer `POSTerminal.tsx:348-361`; reader `CustomerDisplay.tsx:85,104`; grep `scale|weigh` / `label.?print|zebra` → only false positives. (The display BroadcastChannel/localStorage channel **is** wired — HW-05 core works.)
- Severity: MINOR · Confidence: HIGH
- Fix: Include `name_ar` + branding name in the `pos-customer-display` payload.
- Catch forever: unit test of the display-sync payload asserting `name_ar`/`businessName` present when set.

### OPS / SEC / UX — Platform

**F-048 — OPS-05 report aggregators load all period transactions into memory (the real pagination gap)** · `MISSING_SIDE_EFFECT`
- Violated: OPS-05 (P0) *"server-side pagination on every list endpoint (no load-everything)"*.
- Manifests: report endpoints `select(Transactions)…` for the whole period and aggregate in Python with no cap → degrade/OOM at scale. (Triad list endpoints **are** paginated — see Verified-complete; this is the actual violation.)
- Evidence: `backend/routers/features.py:533-541` (sales-summary), `:597-605` (top-products), `:666`.
- Severity: MAJOR · Confidence: HIGH
- Fix: Push aggregation into SQL (`func.sum`/`group_by`) or window the query.
- Catch forever: pytest — seed 10k txns, assert the report issues a single aggregate query / returns under a row cap.

**F-049 — OPS-01 Alembic chain exists but is off by default and `create_all` always runs (drift still hand-patched)** · `SPEC_DIVERGENCE` (spec was too pessimistic; real residual gap)
- Violated: OPS-01 (P0) *"schema via versioned migrations, not runtime ALTER"*.
- Manifests: there **are** 8 chained Alembic revisions, but they run only when `RUN_MIGRATIONS_ON_BOOT=true` (off by default), `create_all` runs unconditionally every boot, and the baseline revision wraps `create_all` + a hand-maintained `_DRIFTED_COLUMNS` ALTER list — so production still relies on runtime create + manual drift patching.
- Evidence: `backend/services/migrations.py:48,49-60`; `backend/main.py:85-86`; `backend/services/database.py:40`; `backend/alembic/versions/e4f5a6b7c8d9_*.py:1-15`.
- Severity: MINOR (downgrade from the spec's "Critical"; correct IB §4.18 / CLAUDE.md) · Confidence: HIGH
- Fix: Make `create_all` conditional on `not RUN_MIGRATIONS_ON_BOOT`; default migrations on for prod.
- Catch forever: CI — `alembic upgrade head` on an empty DB yields an empty autogenerate diff.

**F-050 — SEC-05 PDPL entirely absent (consent, data-subject export/delete)** · `MARKET_GAP`
- Violated: SEC-05 (P1) consent capture + export/delete + residency awareness.
- Manifests: blocks compliant CRM-05 marketing; no consent field, no export/delete-me endpoint.
- Evidence: repo grep `pdpl|consent|data-subject|erasure|gdpr` → 0 application hits.
- Severity: MINOR · Confidence: HIGH
- Fix: `marketing_consent` on customers + `GET /me/data-export` + `DELETE /me/data` (tombstone PII).
- Catch forever: pytest — export returns all customer-linked rows; delete tombstones PII.

**F-051 — UX-02: no offline state in any back-office page; permission-denied has no in-page state; errors collapse into the empty state** · `DESIGN_GAP`
- Violated: UX-02 (P0) *"every page defines loading/empty/error/permission/offline"* + the §5 universal offline-banner rule.
- Manifests: only POSTerminal references offline; ProductManagement/CustomerManagement/ReportsAnalytics/AuditLog/Notifications/ShiftManagement render no offline banner; granular RBAC has only route-level gating (no in-page "you lack permission"); several pages `catch {}` and toast/swallow so a 500 looks like an empty result.
- Evidence: grep `offline|navigator.onLine|OfflineBanner` across `frontend/src/pages` → only `POSTerminal.tsx`; `ReportsAnalytics.tsx:153-189` (`// silently handle error`); `Notifications.tsx:34` (`catch { setNotifications([]) }`); `ProtectedRoute.tsx:47-49` (route-level only).
- Severity: MAJOR · Confidence: HIGH
- Fix: Shared `useOnlineStatus()` + `<OfflineBanner/>` in the back-office layout; a shared error-card distinct from empty; an in-page permission state.
- Catch forever: Playwright — render with `navigator.onLine=false` → banner; mock 500 → error UI (not empty UI).

**F-052 — UX-08: notifications synthesized per-request (not persisted), mark-read is a no-op, and the list never renders (field mismatch)** · `STUB_TODO` (live bug)
- Violated: UX-08 (P1) *"Notification center … persisted"* (ZATCA-failed/subscription/KDS types).
- Manifests: no `notifications` model; `/notifications/list` fabricates items each call from low-stock + last-5 transactions (only `low_stock`/`transaction` types); `mark-read` returns success but persists nothing (read-state is a lie across reloads). Compounding bug: backend returns `{items, unread_count}` but the frontend reads `data?.notifications` → the page **always shows empty** regardless of synthesized alerts.
- Evidence: no `notifications` model; `backend/routers/features.py:710-766,769-774`; `frontend/src/pages/Notifications.tsx:33` vs `api.ts:364-370`.
- Severity: MAJOR · Confidence: HIGH
- Fix: Persisted `notifications` table + real read-state; map `items` in `getNotifications()`.
- Catch forever: pytest/Playwright — a low-stock product appears in the page list; mark-read survives a refetch.

**F-053 — PRN-05 Z-report, PRN-07 barcode/shelf label, PRN-08 subscription invoice, PRN-09 dunning notice absent** · `MARKET_GAP`
- Violated: PRN-05 & PRN-09 (P0), PRN-07 & PRN-08 (P1).
- Evidence: grep `z.?report|shelf|barcode.?label|subscription.?invoice|dunning` across `pdf_render.py`/`escpos.py`/routers/`frontend/src` → 0 application hits. (PRN-05 = the RPT-06 / F-008 fiscal-close gap; PRN-08/09 tie to CL billing F-028.)
- Severity: MAJOR (PRN-05/09 P0) · Confidence: HIGH
- Fix: Build the four on the existing `pdf_render.py`/`escpos.py` rails.
- Catch forever: golden-render tests (Z-report has tender breakdown + variance; subscription invoice has seller/buyer/VAT blocks).

**F-054 — Orphaned MGX scaffolding still mounted/routed (AI Hub, object storage, Stripe Checkout, blog, OAuth callback, duplicate integrations.py)** · `ORPHAN_CODE`
- Violated: IB §8 orphan ledger (verdict requested for each).
- Manifests: dead surface + maintenance/confusion; an unauthenticated `/all` or unused endpoint widens the attack/audit surface. See the verdict table in §4.
- Evidence: per-item below in §4 (each verified by a `frontend/src` caller grep returning 0).
- Severity: MINOR · Confidence: HIGH
- Fix: Remove AI Hub, blog, OAuth callback, `integrations.py`, and (decide) Stripe Checkout + object storage; **wire** `receipt_templates` as the AG-07 editor.
- Catch forever: CI lint flagging any backend router with no `api.ts`/frontend caller.

---

## 3. Low-confidence / needs human confirmation

- **L-01 — ZATCA canonicalization vs official SDK (§7).** TLV/hash/stamp are bespoke and internally self-verifying, but the hash is over the **raw serialized XML** (`zatca_sale.py:147`), not a canonicalized (C14N) UBL. Conformance to ZATCA's exact canonicalization is **unverified and a likely real gap**; confirming needs the official ZATCA SDK sample vectors (not in-repo). Searched `canonical|c14n|official|sample` → no canonicalization step. (Confidence the gap exists: MEDIUM.)
- **L-02 — `_next_icv` concurrency.** ICV is `MAX(icv)+1` per client (`zatca_sale.py:85-92`) with no row lock; under concurrent sales + refunds a collision is conceivable but not confirmed exploitable within the single sale transaction. Needs a concurrency test.
- **L-03 — F-031 exploitability.** The `features.py` master-default is unambiguously wrong vs `tenant.py`, but whether a real account can reach it depends on account state (e.g. a self-registered user with `ALLOW_REGISTRATION=true` and no agent/client row). Verify at runtime.
- **L-04 — FIN-04 / pay-in-out.** Confirmed no pay-in/out/cash-drop route on the shift path, but the shift *service* was not read in full; a drawer-movement path could theoretically live elsewhere (low risk — no route surfaces it).
- **L-05 — L10N-01 shipped-screen strings.** The i18n *map* is balanced (147 identical keys × 4 locales — HIGH confidence), but several pages hardcode English/inline-ternary strings (`ProductManagement.tsx`, `Notifications.tsx:149`), so "every shipped string localized" is not fully met. Not exhaustively scanned across all 30 pages (MEDIUM).
- **L-06 — CRM-04 segments.** The segment/tag grep hit ~50 files on substring noise; judged none a real customer-segment feature but did not open all 50.
- **L-07 — OPS-03 backups/DR.** Out of static-trace scope; assumed absent per IB §4.18 (doc-only) — confirm operationally.

---

## 4. Verified-complete (mapped to real code — auditable both ways)

**ZATCA crypto core (genuinely strong — refutes "façade" suspicions):**
- ZA-02 **real ECDSA stamp** (not a placeholder): `backend/services/zatca.py:243-253` (`ec.ECDSA(Prehashed(SHA256))` over the invoice-hash digest), `verify_stamp` `:256-268`; the old HMAC stub (`production.py:157-181`) is **not** on the sale path. Test `tests/test_zatca.py:126`.
- ZA-03 **TLV QR all 8 tags** incl. hash (6), ECDSA stamp (7), EGS public key (8) with BER lengths: `zatca.py:284-332`; onto txn `zatca_sale.py:151-181`.
- ZA-04 **hash chain** per-client monotonic ICV + PIH advance in-transaction: `zatca_sale.py:85-92,146,179`; seed `zatca.py:86`.
- ZA-10 **integrity walk** verifies each `previous_hash` + re-verifies every stamp, reports first break: `zatca.py:459-517`.
- ZA-05 retention ≥6y: `zatca_sale.py:38-40,174`. ZA-01 onboarding (CSR→compliance→production CSID) + AES-256-GCM secrets: `zatca.py:118-140,153-271`. ZA-07 env selection + ZA-06 fail-closed-to-`pending`: `zatca.py:63-112`, `zatca_sale.py:204-251` (tests `test_phase2_zatca_sale.py:251,291`).
- PRN-02 A4 invoice + HTML invoice **genuinely always-Arabic** (Amiri + reshaper + bidi): `backend/services/pdf_render.py:30-258`, `pos.py:823-858`. PRN-03 credit-note (381) chained with `BillingReference`: `pos.py:763-770`, `production.py:257-262`.

**POS / sale:**
- OPS-02 **atomic sale** — counter + txn + inventory + loyalty + shift + ZATCA sign in one commit, rolls back wholly on any raise: `pos.py:428` (live), `:592` (offline).
- POS-05 offline dedup + same atomic path on replay: `offlineQueue.ts`, `pos.py:524-533`. POS-06 barcode (scanner + camera `BarcodeDetector`) + search: `POSTerminal.tsx:208-270`. POS-02 split validated to total + breakdown persisted (as a **label** only — see F-001): `pos.py:312-329`. CL-04 pay records + advances, 402-on-decline before any write: `tenant.py:876-941`.

**Tenancy / security:**
- MA-01/02/04/05 agent provisioning, **atomic guarded slot decrement** (cannot oversell), refill, master-only global VAT: `tenant.py:281-351,354-386,390-421,595-608`. CL-01/05 merchant own-login + `must_change_password`, suspend paths: `tenant.py:610-620,679-708,981-1086`. AG-01/02/04 logo (MIME/size validated) + branding persist/apply: `tenant.py:517-556,473-496`.
- SEC-01 access **+ refresh** tokens + revocation + logout (durable `revoked_tokens`): `core/auth.py:52-69`, `routers/auth.py:81-179`, `services/token_revocation.py:54-61`. SEC-04 AES-256-GCM secrets: `zatca.py:116-140`. **SEC-07 audit completeness via middleware** over all `/api/v1` mutations + auth failures, out-of-band, redacted (refutes "partial"): `middlewares/audit.py:74-100`. SEC-08 rate-limit/validation/CORS (env-gated): `middlewares/production.py:85-125,328-355`, `core/cors.py:8-53`. SEC-02 triad scoping + admin-gated `/all`: `services/clients.py`, `clients.py:148` (caveat F-031). SEC-03 deny-wins RBAC + master bypass: `dependencies/permissions.py`.

**Localization / ops / hardware / inventory:**
- L10N-01..06: i18n map balanced (147 keys × ar/en/hi/ur), Arabic-Indic digits + SAR, RTL, optional Hijri, agent-default + user-override: `lib/i18n.ts`, `lib/format.ts:20-92`, `core/formatting.py:15-27`, `BrandingContext.tsx:23-31,160`.
- OPS-04 Sentry/health/structured-logs, OPS-08 email/SMS/ZATCA graceful degradation, **triad server-side pagination** (refutes OPS-05 blanket suspicion): `core/observability.py:24-60`, `core/email.py:46-59`, `core/sms.py:29-61`, `routers/products.py:103-135`, `services/products.py:56-101`. `/analytics/forecast` is a **real** moving-average aggregate, not a stub: `services/production.py:1052-1097`.
- HW-01 ESC/POS thermal (WebUSB) + embedded QR: `escpos.py:22-150`, `thermalPrint.ts:39-64`. HW-02 scanner (HID + camera): `POSTerminal.tsx:225-268`. HW-05 customer-display channel wired (payload gap F-047): `POSTerminal.tsx:346-365`, `CustomerDisplay.tsx:31-65`.
- INV-01/02/03 catalog + multi-branch stock (atomic deduct/restore): `features.py:91-322`, `services/branch_stock.py:53-94`. INV-11 bulk import (validated): `integrations.py:52-91`. INV-07 PO idempotency: `purchase_orders.py:263-264`. CRM-02 loyalty accrual/redemption atomic + feature-gated: `services/loyalty.py:71-177`, `pos.py:270-411`. RPT-01/02 + CSV: `features.py:517-689`.

### Orphan-ledger verdicts (§8)

| Item | Verdict | Evidence (file:line) — searched `frontend/src` for callers |
|---|---|---|
| **AI Hub** (`routers/aihub.py`, `services/aihub.py`) | **DEAD — remove** | grep `aihub\|genText\|generateText` in `frontend/src` → 0. MGX scaffolding. |
| **Object storage** (`routers/storage.py`) | **DEAD now / wire later** | grep `/storage\|upload-url\|presigned\|buckets` → 0; logos use local disk (`main.py:147-149`). Adopt for AG-07 exports or remove. |
| **Stripe Checkout** (`routers/payment.py`) | **DEAD — fold into PAY-07 or remove** | grep `/payments/checkout\|createCheckout` → 0 (subscription uses `tenant.py` Connect). (= F-006) |
| **Blog** (`pages/blog/*`, `blog-routes.tsx`, `lib/blog.ts`) | **DEAD — remove** | `App.tsx` never imports blog routes; only `lib/blog.ts` self-references. |
| **OAuth callback** (`AuthCallback.tsx`/`AuthError.tsx`, `/auth/callback`,`/auth/error`) | **DEAD — remove** | Routes registered (`App.tsx:81-82`) but unreachable: `AuthCallback` reads a `#token=` hash (`atomsClient.ts:184-190`); the local email/password flow never redirects there. |
| **Duplicate bulk/search/webhook/email** (`integrations.py` vs `production.py`) | **`integrations.py` DEAD — consolidate** | Frontend calls **no** `/api/v1/integrations/*` (grep 0); only `/production/webhooks/*` used (`WebhookManagement.tsx:106,190`). Both `/search` impls unwired (`production.py:969` has 0 UI callers too). |
| **receipt_templates** (model + triad) | **WIRE-UP (gap, not dead)** | grep `receipt_template` in `frontend/src` → 0 UI; auto-mounted triad. Wire as the AG-07/PRN branding editor. |

---

## 5. Parity scorecard (P0 table-stakes built vs total, per family)

| Family | KSA-leader parity — one line | P0 built / total |
|---|---|---|
| **PAY** | **Façade.** Tenders are labels; no Mada/Apple Pay/STC/BNPL, no terminal capture, no PCI tender model. The #1 gap. | 0 / 7 |
| **RST** | **Greenfield.** No tables/KDS/modifiers/order-tickets/business_type. A restaurant client cannot operate. | 0 / 5 |
| **ZA** | **Strong crypto core**, but B2B clearance is a non-functional façade, no buyer VAT, no status/alerts/retry. | 9 / 10 (ZA-06 fails) |
| **POS** | Solid atomic retail core + offline + ZATCA; **refund whole-invoice only, no Z-report, no hold, no void, no terminal.** | ~6 / 10 |
| **INV** | Catalog + multi-branch + PO-receive built; **no variants, transfers dead-end, PO not branch-aware, no COGS.** | ~3 / 4 |
| **RPT** | Sales summary + top products; **no payment-breakdown (P0), no Z-report (P0), no margin/VAT/economics, no PDF.** | 0 / 2 |
| **CL** | Provision + atomic slot + pay/suspend built; **no business_type (P0), dunning, proration, merchant invoice, trial.** | ~3 / 4 |
| **AG** | Colors/logo/font built + real feature-gate engine; **no custom domain, branded email, branded printables; most toggles cosmetic.** | 3 / 4 |
| **RSL** | Subscription payments recorded; **no commission ledger, no agent password-reset (P0), no impersonation/health/economics.** | 0 / 1 |
| **MA** | Agents/slots/global-VAT/packages built; **no platform economics, packages don't gate features.** | 6 / 6 (MA-08 is P1) |
| **CRM** | Customers + loyalty built; **no customer VAT (P0, blocks B2B), no gift cards/segments/marketing.** | 1 / 2 |
| **PRC** | %/flat discounts exist but client-side-only & caps unenforced; **no coupons/BOGO/price-lists.** | 0 / 1 |
| **OMN** | Entirely absent (Salla/Zid/channel orders). | n/a (P1 family) |
| **FIN** | Expenses + revenue view; **no GL/journal export, no integrations, cash not tied to shift.** | n/a (all P1/P2) |
| **HW** | Thermal + scanner + display channel built; **no terminal (P0), kitchen, scale, label printer; display payload gap.** | 2 / 3 |
| **SEC** | bcrypt/JWT/refresh/revocation/RBAC/audit/AES-256/CORS all built; **PDPL absent; one role-default divergence.** | ~6 / 6 (+1 divergence) |
| **OPS** | Atomic sale, observability, degradation, Alembic chain, triad pagination built; **reports load-everything, migrations off-by-default.** | ~6 / 7 |
| **L10N** | Built end-to-end (4 locales balanced, RTL, Arabic-Indic, Hijri, override). | 5 / 5 |
| **UX** | Design system + role nav + loading/empty built; **no offline/in-page-permission states, notifications a stub.** | ~5 / 7 |
| **PRN** | Receipt/A4/credit-note/quotation built (A4+HTML Arabic; **thermal not Arabic**); **no Z-report/label/sub-invoice/dunning.** | ~4 / 6 |

---

## 6. Finish — counts & top findings

- **Total confirmed findings:** 54 (`F-001`..`F-054`) + 7 low-confidence (`L-01`..`L-07`).
- **By severity:** **BLOCKER 5** (F-001, F-002, F-005 [HW-03], F-017, F-045) · **MAJOR ~28** · **MINOR ~21** · INFO 0.
- **P0 table-stakes not fully built:** ~27 (see scorecard) — concentrated in **PAY (7), RST (5), POS (4), RPT (2), PRN (2)**, plus ZA-06, RSL-06, CRM-01, INV-07, HW-03, OPS-05, UX-02, PRC-01.

**Top BLOCKER / MAJOR to triage first:**
1. **F-001/F-002/F-005** — payments are a façade; no Saudi tenders, no terminal capture, no PCI tender model. *(PAY table-stake #1.)*
2. **F-017/F-018/F-020** — ZATCA B2B clearance never routed + no buyer VAT + no retry-pending. *Legally blocking for B2B sales.*
3. **F-045** — restaurant vertical entirely absent (5 P0s); no `business_type` discriminator anywhere.
4. **F-007** — refund whole-invoice only (no partial/line/exchange).
5. **F-008/F-053** — no Z-report endpoint or printable (fiscal day-close).
6. **F-029/F-028/F-025** — reseller depth: no commission ledger, no dunning/proration/merchant-invoice, no custom domain/branded email.
7. **F-009/F-016/F-032/F-052/F-040** — live bugs/dead-ends: cash-blind shift math, shift screen field mismatch, stock-transfer 404 dead-end, notifications never render, client-trusted discount amounts.

**Traceability (closed findings → SRS ID → deterministic test):**
- F-017 → ZA-06 → `tests/test_phase2_zatca_sale.py::test_classify_invoice_subtype_routing` (+ `_b2b_/_b2c_` cases).
- F-018 / F-037 → ZA-06 / CRM-01 / PRN-02 → `tests/test_phase2_zatca_sale.py::test_b2b_sale_captures_buyer_vat_into_xml_and_invoice`, `::test_buyer_vat_resolved_from_saved_customer_record`, `::test_b2c_sale_has_no_buyer_vat_block`, `::test_pdf_buyer_block_renders_vat_when_present`.
- F-001 → PAY-01/PAY-05 → `tests/test_phase2_payments.py::test_card_decline_blocks_sale_and_persists_nothing`, `::test_card_approve_captures_approval_on_tender`.
- F-002 → PAY-01..04/PAY-06 → `tests/test_phase2_payments.py::test_tender_type_enum_includes_saudi_tenders`, `::test_charge_endpoint_declines_then_approves`.
- F-003 → PAY-09 → `tests/test_phase2_payments.py::test_payment_tenders_schema_carries_proof_but_no_pan`.
- F-020 → ZA-06 (retry) / ZA-08 → `tests/test_phase2_zatca_sale.py::test_report_pending_sweep_resubmits_stuck_documents`, `::test_report_pending_clears_standard_b2b_documents`, `::test_report_pending_requires_onboarding`.
- F-007 → POS-07 (partial/line refund) → `tests/test_phase2_zatca_sale.py::test_partial_refund_credits_one_unit_and_marks_partial_refunded`, `::test_successive_partial_refunds_complete_to_refunded`, `::test_partial_refund_rejects_over_quantity`.
- F-008 → RPT-06 / PRN-05 (Z/X-report + cash variance) → `tests/test_phase4_pos.py::test_zreport_groups_by_tender_and_reconciles_variance`, `::test_zreport_scopes_to_owner_and_404s_unknown_shift`.

> **Reminder to the operator:** this is a *prioritized backlog of suspicions for human review and test-promotion, not a release gate.* Each finding ships with a "make it catchable forever" test idea — promote those into `pytest`/Playwright as findings are closed (Prompt 3 closes one per session, building to the `INTENDED_BEHAVIOR.md` design + a deterministic test). Several spec "suspected-absent" items were **refuted** (Alembic chain, audit middleware, triad pagination, i18n parity) — fold those corrections back into `INTENDED_BEHAVIOR.md` §4.18/4.17 and `CLAUDE.md`.
