# DOMAIN_STATUS.md — Hardening Rollup

**Purpose.** One-page index over `INTENDED_BEHAVIOR.md`. The system is divided into the **19 SRS feature codes** (`srs.md` §3.1–3.19). We harden them **one at a time**: each code runs the loop **audit → fix functionality (+test) → fix design → verify → commit + tick**. "Done" = behavior matches `INTENDED_BEHAVIOR.md` and design matches `design_handoff_cloud_pos`, verified end-to-end.

**Statuses** (rollup; the authoritative per-requirement status lives in `INTENDED_BEHAVIOR.md` §4): `built` · `shallow` · `absent` · `mixed`.
**Func/Design columns** reflect the *documented* state; `(stale?)` marks codes where recent commits likely moved reality ahead of the doc — reconciled during that code's audit.

## Tracks (work order — dependency-first)

| Track | Codes | Rationale |
|---|---|---|
| **1 · Foundation** | SEC, OPS | Auth, tenancy, RBAC, audit, migrations — everything rides on it |
| **2 · Platform** | MA, AG, CL, RSL | Master/agent/client + reseller economics; white-label gaps |
| **3 · Selling** | POS, PRC | Core terminal + pricing/promotions |
| **4 · Money** | PAY, ZA, FIN | Payments, ZATCA-on-sale, accounting — biggest known gaps |
| **5 · Catalog & Customers** | INV, CRM | Inventory depth, loyalty/gift cards |
| **6 · Verticals** | RST, OMN | Restaurant ops, omnichannel |
| **7 · Polish** | RPT, L10N, HW, UX/PRN | Reporting, localization, hardware, design system |

## Status matrix

| Code | Track | Func | Design | Key open items (from INTENDED_BEHAVIOR.md §4) | Done |
|---|---|---|---|---|---|
| **SEC** | 1 | mixed *(audited 06-13)* | n/a | ✅ **F-SEC-1 FIXED** (staff now owner-scoped across all merchant routers); **F-SEC-2** PDPL export/erasure absent; F-SEC-3 no idle-timeout. Isolation/audit/secrets verified OK | ◧ |
| **OPS** | 1 | shallow `(stale?)` | n/a | Migrations OPS-01 (alembic/ now exists — verify); pagination OPS-05 partial; backups/DR absent | ☐ |
| **MA** | 2 | shallow | shallow | Economics/MRR absent; ZATCA-env config shallow | ☐ |
| **AG** | 2 | shallow | shallow | Custom domain/branded email/printables/app absent; payment settings shallow; funnel shallow | ☐ |
| **CL** | 2 | shallow | shallow | Dunning/proration/merchant-invoice/usage/trial absent; billing history shallow | ☐ |
| **RSL** | 2 | shallow `(stale?)` | shallow | Revenue split not computed; impersonation/health/economics absent (commission.py exists — verify) | ☐ |
| **POS** | 3 | shallow | shallow | Payment is a label not terminal capture (→PAY); refund whole-invoice only; hold/recall, weighted, tips, void absent | ☐ |
| **PRC** | 3 | shallow | built | Coupons/auto-promos, BOGO/bundle, price lists, scheduled pricing absent | ☐ |
| **PAY** | 4 | absent `(stale?)` | shallow | No Mada/Apple Pay/STC Pay/BNPL/terminal capture; payment.py orphaned (Moyasar façade F-001..003 in flight — verify) | ☐ |
| **ZA** | 4 | built | n/a | B2B clearance-vs-B2C-reporting split shallow/unverified; status dashboard + stuck-doc alerts (ZA-08) absent; per-client gating unused | ☐ |
| **FIN** | 4 | shallow `(stale?)` | built | Journal/GL export (now exists — verify), accounting integrations, AP absent | ☐ |
| **INV** | 5 | shallow `(stale?)` | built | Variants (router exists — verify), stock transfers, counts/adjustments, reorder points, COGS/valuation absent | ☐ |
| **CRM** | 5 | shallow `(stale?)` | built | Gift cards/store credit (router exists — verify), segments/tags/LTV, marketing campaigns absent | ☐ |
| **RST** | 6 | absent `(stale?)` | absent | Tables/KDS/modifiers/order-tickets (F-055..062 done @ 73ecd5f — reconcile doc) | ☐ |
| **OMN** | 6 | absent `(stale?)` | absent | Channel orders, aggregator (routers exist — verify) | ☐ |
| **RPT** | 7 | built `(stale)` | built | Doc says shallow; F-068..072 @ ea36bcc added VAT/margin/inventory/refunds-voids/discounts + PDF — reconcile doc; Z/X report | ☐ |
| **L10N** | 7 | built | built | Verify no locale object missing keys hidden by English fallback | ☐ |
| **HW** | 7 | shallow | n/a | Payment terminal, cash-drawer kick, kitchen printer/KDS, scale, label printer absent | ☐ |
| **UX/PRN** | 7 | built | built | Z-report, KOT, label, subscription-invoice, dunning printables absent; notification center shallow (in-memory) | ☐ |

## Log

- `2026-06-13` — Rollup created from INTENDED_BEHAVIOR.md §4 status lines. Several codes flagged `(stale?)` where commits (RPT/RST clusters, alembic, new routers) likely moved ahead of the doc.
- `2026-06-13` — **SEC audited.** Better than doc's "shallow" on isolation: triads filter `user_id == current_user.id`, `/all` endpoints are master-only (clients/agents provisioned `role="user"`), audit middleware records all auth'd mutations + 401/403, ZATCA secrets AES-256-GCM. Findings:
  - **F-SEC-1 (P1, tenancy correctness)** — `get_tenant_scope` (staff→owner mapping) wired into only **3 source routers** (customers, products, product_variants). The other ~37 scope by the caller's raw `user_id`, so a **staff/cashier login sees its own empty tenant** (no catalog/customers/sales) instead of the merchant's. The seam exists; it was never propagated. Fix: thread `scope.owner_user_id` through every triad.
  - **F-SEC-2 (P1, compliance)** — PDPL data-subject **export + erasure** absent; only a marketing-consent field exists. Saudi PDPL requires both.
  - **F-SEC-3 (P2)** — no idle/session-timeout policy (only JWT `exp`).
- `2026-06-13` — **F-SEC-1 FIXED.** Threaded the `get_tenant_scope` / new `get_owner_id` (dependencies/tenancy.py) seam through every merchant-owned router so a staff/cashier login operates within the *owning* merchant's tenant instead of an empty private one. Touched 18 routers: 13 uniform CRUD triads → `scope.owner_user_id` (branches, categories, discounts, expenses, loyalty_points, loyalty_programs, purchase_orders, quotations, receipt_templates, shifts, suppliers, staff_members, transactions); gift_cards + pos + features + production → `owner_id`. **Actor refs preserved** (RBAC `has_permission`, void `Audit_logs`, per-login metering/session/agent-branding/packages — never owner-swapped). New end-to-end test `tests/test_phase1_staff_scope_endpoints.py` (cashier sees catalog, rings a sale owned by the merchant, stays tenant-isolated). Suite: **426 passed**, 1 pre-existing unrelated failure (`test_payment.py::test_orphaned_stripe_checkout_endpoint_is_removed` — fails identically on clean tree). **Deferred (F-SEC-1b):** per-cashier *attribution* — shifts/sales are now owner-scoped (shared till); separating which cashier rang what needs a `cashier_id` column + Z-report-by-cashier.
  - **Verified OK:** SEC-01 (bcrypt+JWT+refresh-type-check+revocation+suspended-block), SEC-04 (AES-256-GCM secrets), SEC-07 (audit coverage), SEC-08 (env-gated rate-limit/CORS). SEC-06 (PCI) moot until PAY — middleware already redacts card_number/cvv.
