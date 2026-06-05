# INTENDED_BEHAVIOR.md — Vision Model of Intended Behavior & Design (v2.0)

**Purpose.** This file is the ground-truth model of *what the running system is supposed to do and look like* — measured against the **market-parity vision** in `srs.md` v2.0 (a unified retail + restaurant, Saudi-real-payments, ZATCA-compliant, white-label POS that a merchant or reseller would choose over **Foodics / Rewaa / Marn**). It is the notion of "complete" that the AI completeness review (`prompts.md` → Prompt 2 → `COMPLETENESS_REVIEW.md`) checks the code against. It is **distinct from `srs.md`**: the SRS states *requirements + why the market expects them* (IDs like `PAY-05`, `RST-06`); this file traces them to **concrete, checkable behavior and design** across `frontend page → src/lib/api.ts → atomsClient.ts → router → service → model/DB → side effects`, AND specifies **every page, dashboard, and printable**.

**Vision over code.** This model describes the *intended* product, which is deliberately ahead of the current code. Each section carries a **Market expectation vs SRS vs code** line giving the honest current status — `built` / `shallow` / `absent` / `orphaned` — so the gap between vision and reality is explicit. Those gaps are exactly what the review must surface. Facts derived from convention rather than explicit code are marked `(inferred)`.

**Global fiscal invariant.** Receipts, tax invoices, credit notes, and quotations are **always rendered in Arabic (RTL) with Arabic-Indic digits per ZATCA, regardless of the user's UI language** (SRS L10N-06, §7). Repeated in every relevant section.

**Status legend.** `built` = traced end-to-end in code · `shallow` = exists but below the market bar (a label, a stub, happy-path-only) · `absent` = no implementation found · `orphaned` = code exists with no reachable caller/UI. Priorities `P0/P1/P2` are inherited from `srs.md`.

---

## Table of contents

1. [Two-products framing](#1-two-products-framing)
2. [Market-expected behavior baseline](#2-market-expected-behavior-baseline)
3. [Global model](#3-global-model) — [3.1 Actors](#31-actors--roles) · [3.2 Scope matrix](#32-permission--scope-matrix) · [3.3 State machines](#33-state-machine-catalog) · [3.4 Invariants](#34-cross-cutting-invariants)
4. [Per-feature sections](#4-per-feature-sections) — MA · AG · CL · POS · RST · PAY · INV · CRM · PRC · RPT · FIN · OMN · ZA · RSL · L10N · HW · SEC · OPS · UX/PRN
5. [Page & dashboard design specs](#5-page--dashboard-design-specs)
6. [Printable specs](#6-printable-specs)
7. [End-to-end journeys](#7-end-to-end-journeys)
8. [Orphaned / unwired scaffolding ledger](#8-orphaned--unwired-scaffolding-ledger)
9. [Completeness-review usage note](#9-completeness-review-usage-note)
10. [Summary](#10-summary)

---

## 1. Two-products framing

This codebase is **two products sharing one database**, each judged against a different competitor set and each with its own completion bar. A reviewer must hold both bars.

| | **Product A — the POS** | **Product B — the white-label SaaS platform** |
|---|---|---|
| **Who touches it** | Cashier, server, merchant owner, end customer | Agent (reseller), Master (operator) |
| **Judged against** | Foodics (restaurant), Rewaa (retail), Marn, Geidea, Square/Loyverse | White-label POS programs, Stripe-Billing-class tooling |
| **"Complete" means** | A Saudi merchant runs their shop/restaurant on it all day, takes Mada/Apple Pay, never loses a sale offline, and every invoice is a real ZATCA-Arabic document | A reseller brands it to their own domain, onboards merchants, bills them with dunning, and sees their margin; the operator sees platform economics |
| **Current weight in code** | Strong fiscal core + offline; **thin on payments depth, restaurant, refund granularity, reporting depth** | Strong tenancy + slots + basic branding; **thin on billing depth, revenue-split, white-label depth** |

The SRS market layer (§2.2) and §2 below make the *expectations* explicit so "complete" is not the code's current shape but the market's.

---

## 2. Market-expected behavior baseline

The conceptual core: a market expectation → the **behavior it obligates** → its current status. `table-stake` = the product is not market-credible without it; `differentiator` = competitive edge. (Mirrors `srs.md` §2.2; status from the code survey.)

### Cashier (retail) / Server (restaurant)
| Expectation | Implied intended behavior | Kind | Status | IDs |
|---|---|---|---|---|
| Charge via an integrated **Mada/Apple Pay terminal** | Push total to terminal, capture approval/RRN/network onto the invoice; decline blocks the sale | table-stake | **absent** (only generic `payment_method` cash/card/bank) | PAY-01,05 |
| Sub-second, **offline-proof** checkout | Local commit, idempotent queue + auto-sync | table-stake | **built** (IndexedDB + `/production/offline/sync`) | POS-05,12 |
| **Park/hold** & recall; multiple open tickets/tables | `held`/`open` ticket states; multi-ticket | table-stake | **absent** | POS-10, RST-03 |
| Variants, modifiers, combos, weighted/open-price | Line items carry variant/modifier/combo/weight/sale-price | table-stake | **absent** (flat products only) | INV-04, RST-05, POS-11 |
| **Partial & line-level** refunds, exchanges | Each a ZATCA credit note; restore exact lines/stock | table-stake | **shallow** (whole-invoice refund only) | POS-07,13 |

### Merchant owner
| Expectation | Implied behavior | Kind | Status | IDs |
|---|---|---|---|---|
| See **profit**, not just revenue | COGS & margin per item/category; dead-stock/reorder | table-stake | **absent** (revenue-only reports) | RPT-04, INV-09 |
| **Z-report** at close | Structured fiscal close: tenders, VAT, voids, refunds, variance | table-stake | **shallow** (cash count only, no Z-report) | RPT-06, POS-09 |
| Accounting handoff | Journal/GL export; Zoho/QB/Odoo sync | expected | **absent** (CSV bulk export only) | FIN-02,03 |
| Sell online (Salla/Zid) + aggregators | Shared catalog/stock; online/aggregator orders on POS | differentiator | **absent** | OMN-*, RST-08 |
| Gift cards / store credit / promotions | Issue/redeem; BOGO/coupons/price lists | expected | **absent** (only %/flat discounts) | PRC-* |

### Agent / reseller
| Expectation | Implied behavior | Kind | Status | IDs |
|---|---|---|---|---|
| **Deep** white-label | Custom domain, branded email, branded printables, branded app | table-stake (for B) | **shallow** (colors/logo/font only) | AG-05..09 |
| Real billing | Dunning, proration, plan change, merchant invoices | table-stake (for B) | **shallow** (manual suspend; fixed 30/365 advance) | CL-06..10 |
| Know their **margin** | Commission/revenue-split ledger | table-stake (for B) | **absent** (payments recorded, split not computed) | RSL-01..04 |
| Support merchants | Impersonate / "log in as"; reset password | expected | **shallow** (password reset path exists; no impersonation) | RSL-05,06 |
| Self-service growth | Branded funnel that provisions a trial client | differentiator | **shallow** (public landing pages exist; trial-provision not wired) | AG-10, CL-11 |

### Master / operator
| Expectation | Implied behavior | Kind | Status | IDs |
|---|---|---|---|---|
| Operate SaaS safely | Isolation, audit, backups/DR, metering, rate-limit, observability, **migrations** | table-stake (for B) | **partial** (audit/rate-limit/Sentry env-gated; **no Alembic migrations**, **no DR**) | SEC-*, OPS-* |
| Enterprise compliance | PDPL, PCI-scope minimization, ZATCA evidence | expected | **absent/implicit** | SEC-05..08 |
| Platform economics | MRR, churn, active merchants, agent revenue rollup | expected | **absent** | RSL-08, RPT-09 |

### End customer
| Expectation | Implied behavior | Kind | Status | IDs |
|---|---|---|---|---|
| Valid **ZATCA Arabic invoice + QR**, email/SMS | Arabic fiscal invoice, TLV QR, delivery | table-stake | **built** | ZA-02,03, POS-04 |
| Pay how Saudis pay | Mada, Apple Pay, STC Pay, **BNPL**, cash | table-stake | **absent** beyond cash/card | PAY-01..04 |
| See order/total on a screen | Live customer-facing display | expected | **shallow** (`/customer-display` via localStorage; verify wiring) | UX-07 |

> **The five biggest market gaps** (drive the backlog): (1) Saudi payments + terminal; (2) restaurant mode entirely; (3) partial/line refunds; (4) Z-report + profit/COGS reporting; (5) reseller depth (commission ledger, dunning, custom domain).

---

## 3. Global model

### 3.1 Actors & roles
Roles are **derived per request from DB membership, never read from the JWT** (`backend/routers/tenant.py::get_user_role`; `backend/dependencies/tenancy.py::get_tenant_scope`).

| Actor | Meant to do | How derived |
|---|---|---|
| **master** | Platform owner: manage agents/packages, global VAT + ZATCA env, view platform economics, monitor health. | Seeded `users.role=="admin"` with **no** agents/clients row. Seeded from `ADMIN_EMAIL`/`ADMIN_PASSWORD`. |
| **agent** | White-label reseller: brand (incl. domain/email), entitle features per client, provision/suspend clients vs slots, set fees, collect subscriptions, see margin. | Linked to an `agents` row. |
| **client** (merchant) | Run the POS (retail and/or restaurant): sell, refund, manage catalog/customers/staff/reports, pay own subscription. | Linked to a `clients` row. Carries `business_type` ∈ {retail, restaurant, both} (CL-02). |
| **staff_member** | Sub-user under a client (cashier/server/manager). Inherits the client's tenant scope; gated by granular permissions. | Resolved to the owning client's `owner_user_id` `(inferred)`. |
| **public** | Agent public funnel/landing, `/health`, customer-facing display, deliberate `/all` + `/api/config`. | No token. |

**Least-privilege default:** any authenticated account with no agent/client row and `role != "admin"` is a **client scoped to itself** — a self-registered user can never become master.

### 3.2 Permission / scope matrix
**Entity CRUD triad** (`routers/`+`services/`+`models/<entity>.py`) for: products, product_variants*, categories, customers, discounts, promotions*, gift_cards*, expenses, suppliers, purchase_orders, stock_transfers*, stock_counts*, staff_members, shifts, transactions, payment_tenders*, agents, clients, agent_features, client_features, packages, quotations, receipt_templates, webhooks, audit_logs, loyalty_programs, loyalty_points, api_usage, permissions, branches, tables*, order_tickets*, modifiers*, kds_tickets*, terminals*, commission_ledger*, channel_orders*, notifications*. (`*` = vision entity, may be absent today.)

| Route shape | Auth | Scope | Notes |
|---|---|---|---|
| `GET/POST/PUT/DELETE /api/v1/entities/<e>` & `/<e>/{id}` | required | service filters on `user_id`/owning tenant | Ownership enforced in the service layer. |
| `GET /api/v1/entities/<e>/all` | `get_admin_user` (master) in most triads | no user filter | Deliberately cross-user; treat unauthenticated `/all` as intentional only where a sibling does the same. |
| `POST/PUT/DELETE /api/v1/entities/<e>/batch` | required | per-item ownership | Bulk. |

**Hand-written routers** (real logic): `tenant.py`, `pos.py`, `zatca.py`, `payment.py`, `production.py`, `features.py`, `purchase_orders.py` (+`/receive`), `integrations.py`, `settings.py`, `user.py`, `auth.py`, `health.py`, and (vision) `restaurant.py`, `payments_terminal.py`, `commission.py`, `omnichannel.py`.

**Granular RBAC** (`dependencies/permissions.py`): grant-by-default, **explicit-deny-wins, master bypasses**. Keys gate routes via `require_permission("<key>")` (e.g. `pos.refund`, `pos.void`, `pos.price_override`, `reports.view`, `products.edit`); frontend reads `GET /auth/me/permissions` to hide/disable controls.

**Feature entitlement** (`dependencies/features.py`): enabled-by-default; a `client_features` row `is_enabled=false` disables a capability; `require_feature("<name>")` → 403. Keys: `email_receipts`, `sms_receipts`, `loyalty`, and (vision) `restaurant`, `inventory`, `discounts`, `zatca`, `omnichannel`. Agent defaults in `agent_features`.

### 3.3 State-machine catalog
| Entity | States | Transitions (trigger → actor) |
|---|---|---|
| **agent** | active / inactive | create (master)→active; toggle (master) |
| **package slots** | total / used | create-agent sets total; client-create `used+1` guarded `used<total`; refill raises total |
| **client** | active / suspended | create→active; toggle / suspend-overdue / dunning-exhausted / gateway-failure-webhook→suspended; pay / recovery-webhook→active. Suspended blocked at auth (403) |
| **subscription** | active / past_due / **dunning** / suspended | pay→active + advance billing; charge-fail→past_due→(retry schedule)→dunning→suspended; recovery→active. **(dunning = vision; today: active/past_due/suspended)** |
| **user password** | normal / must_change_password | provision temp pwd→must_change; change-password clears it |
| **JWT token** | valid / revoked | issue on login/register; logout blocklists `jti` |
| **transaction** | completed / **held** / refunded / **partial_refunded** / credit_note / synced-offline | sale→completed; hold→held (vision); refund (full/partial)→refunded/partial_refunded + credit_note row |
| **order_ticket** (restaurant) | open / held / fired / settled / void | open table→open; fire→KDS; settle→ZATCA invoice; **(entirely vision)** |
| **shift** | open / closed | open (float)→open; pay-in/out/drop; close (count)→Z-report→closed |
| **purchase_order** | draft / ordered / partially_received / received | create; receive (full/partial)→stock; idempotent |
| **stock_transfer** | draft / sent / received | create→sent; receive→stock moved **(vision)** |
| **ZATCA onboarding** | not-onboarded / csr-generated / compliance-csid / production-csid (onboarded) | csr→compliance→production |
| **ZATCA document** | signed / reported / cleared / failed / pending | signed in sale; B2C→reporting, B2B→clearance; fail-closed→pending; terminal 4xx→failed |
| **payment tender** | authorized / captured / declined / refunded | terminal/gateway auth→capture; decline blocks sale; refund routes to original tender **(vision)** |
| **gift card** | issued / active / redeemed / expired | issue→active; redeem decrements; expiry **(vision)** |

### 3.4 Cross-cutting invariants
- **Tenancy ownership scoping.** Every read/write filters on the caller's tenant. Agent≠other agents; client≠other clients. `/all` is the deliberate admin-gated exception.
- **No hardcoded brand.** Agent logo/colors/font/radius (and domain/email/printables, vision) applied via CSS variables (`BrandingContext.applyBranding`); clients never see the platform brand. Never edit `index.html` (`%VITE_*%` placeholders).
- **All fiscal docs Arabic.** Tax invoice, credit note, and quotation render RTL/Arabic with Arabic-Indic digits regardless of UI language.
- **Server-stamped IDs/timestamps.** Invoice numbers (`INV-<client:04d>-<counter:06d>`), credit-note numbers, counters, ICV, hashes, timestamps — assigned server-side, never trusted from the client.
- **Atomic sale.** A POS sale commits the transaction row, invoice-counter increment, inventory deduction, **payment-tender capture** (vision), loyalty movement, shift accumulation, and ZATCA sign/hash-chain **in one DB transaction**; any failure rolls the whole sale back — no counter consumed, no unsigned fiscal record, no captured-but-unrecorded payment.
- **Slot-accounting integrity.** Client provisioning decrements the agent's slot via a guarded atomic UPDATE; concurrent creates cannot oversell.
- **Global tax inheritance.** Master's global VAT (MA-05) is authoritative; per-request `vat_rate` is only a fallback; agents/clients cannot override.
- **PCI scope minimization** (vision). Card PANs are entered on the terminal/gateway only; we store tokens/last-4/network, never the PAN.
- **Every integration degrades, never crashes.** Gateway/terminal/ZATCA/SMTP/Twilio/storage unset → logged/queued fallback; the originating request still succeeds (except where a real payment decline must block a sale).
- **Audit trail.** Authenticated mutations recorded to `audit_logs` out-of-band in an isolated session that never rolls back the request.

## 4. Per-feature sections

### 4.1 (MA) Master / Agent Management — `routers/tenant.py`, `pages/MasterDashboard.tsx`, `PackageManagement.tsx` (MA-01..09)
**Purpose:** Master creates and governs agents, slot allowances, packages, global VAT/ZATCA env, and sees platform economics.
**Market vs SRS vs code:** market expects a clean operator console with economics; SRS adds packages (MA-07), economics (MA-08), ZATCA env (MA-09); **code:** agent CRUD + slots + global tax `built`; package CRUD `built` (`/api/v1/packages/*`); **economics/MRR `absent`**; ZATCA-env config `shallow`.
**Actors:** master only; every endpoint re-checks `get_user_role=="master"` → 403 otherwise.
**Entities & states:** `agents` (active/inactive, `package_type`=total slots, `used_slots`); `packages`; `system_settings` (global VAT).
**Primary flow:** `/master` → `GET /tenant/master/agents` (used/remaining) → "Add Agent" `POST /tenant/master/agents` (creates login + agents row, one-time temp password) → "Add Slots" `POST …/slots` → "Set Tax Rate" `PUT …/tax-rate` → toggle `POST …/toggle`. Packages via `/api/v1/packages/*`. Economics (MA-08) → `GET /tenant/master/economics` **(vision endpoint)**.
**Alternate:** non-master→403; not-found→404; `slots<=0`→floored to 1; tax outside 0–100→400; duplicate email→409.
**Side effects:** agent login row; one-time temp password (never stored plaintext).
**Cross-deps:** slot pool→CL provisioning; global VAT→POS & ZATCA totals; economics←RSL commission ledger.
**Completion criteria:** MA-01 one-step agent+login ✓; MA-02/03 slot decrement + used/remaining ✓; MA-04 refill ✓; MA-05 global VAT uninoverridable ✓; **MA-07 package→entitlement mapping** (verify tiers gate features); **MA-08 economics dashboard** (absent — finding); MA-09 ZATCA env config (verify).
**Open questions/gaps:** no computed MRR/churn/revenue-by-agent (MA-08) — **gap**. Package→feature-entitlement link `(inferred)` — verify a package actually unlocks a feature tier.

### 4.2 (AG) White-Labeling & Feature Entitlement — `routers/tenant.py`, `features.py::/branding/update`, `pages/BrandingEditor.tsx`, `AgentDashboard.tsx`, `contexts/BrandingContext.tsx` (AG-01..10)
**Purpose:** Agent customizes brand (logo/colors/font/radius — and domain/email/printables, vision) and entitles features per client.
**Market vs SRS vs code:** market expects deep white-label (domain, email, app); SRS adds AG-05 custom domain, AG-06 branded email, AG-07 branded printables, AG-08 branded app, AG-09 payment settings, AG-10 funnel; **code:** colors/logo/font/radius/default-language `built`; **domain/email/printables/app `absent`**; payment settings `shallow` (Stripe account id field exists); funnel `shallow` (landing pages exist, not provisioning).
**Actors:** agent (own branding/clients); clients consume read-only branding.
**Entities & states:** `agents` (logo_url, colors, font, radius, default_language, stripe_account_id, **custom_domain*, email_template_id***); `client_features`.
**Primary flow:** `GET /tenant/agent/branding` → logo `POST /tenant/agent/logo` (PNG/JPEG/WebP/SVG ≤2 MB) → colors/font/radius/lang `PUT /api/v1/branding/update` → per-client feature toggle `POST /tenant/agent/clients/{id}/features` → on client login `GET /tenant/client/branding` injects CSS vars + `dir`/`lang`. **Vision:** custom domain `POST /tenant/agent/domain` (verify DNS/cert); email templates `PUT /tenant/agent/email-templates`; payment account `PUT /tenant/agent/payment-account`.
**Alternate:** non-agent→403; bad MIME→400; >2 MB→413; empty→400; toggling unowned client→404; branding missing→defaults (`#3B82F6`/`Inter`/`8px`).
**Side effects:** logo to disk/storage; branding reflected for every client.
**Cross-deps:** `default_language`→L10N-05; feature flags gate POS receipt delivery, loyalty, restaurant, etc.
**Completion criteria:** AG-01/02/04 brand persists + applied, no hardcoded brand ✓; AG-03 toggle actually gates server-side ✓ (`require_feature`); **AG-05 custom domain serves merchant login + funnel** (absent — finding); **AG-06 branded transactional email** (absent — finding); **AG-07 branded printables** (absent — finding); AG-09 agent gateway connect (verify beyond Stripe).
**Open questions/gaps:** verify every agent-facing toggle maps 1:1 to an enforced `require_feature` key (no cosmetic switch). Custom domain + branded email are table-stakes for Product B and currently absent.

### 4.3 (CL) Client Onboarding, Subscription & Billing — `routers/tenant.py`, `pages/AgentDashboard.tsx`, `ClientDashboard.tsx`, `ForceResetPassword.tsx` (CL-01..11)
**Purpose:** Agent provisions merchants vs slots and runs their billing (fee, cycle, dunning, proration, invoices); client pays; non-payment suspends.
**Market vs SRS vs code:** market expects real subscription billing; SRS adds CL-06 dunning, CL-07 proration, CL-08 merchant invoice, CL-09 billing history, CL-10 usage add-ons, CL-11 trial; **code:** provision + slot decrement + first-login reset + pay + suspend `built`; **dunning/proration/merchant-invoice/usage/trial `absent`**; billing history `shallow` (last 24 payments listed).
**Actors:** agent (provision/suspend/set-fee for own clients); client (view/pay own).
**Entities & states:** `clients` (is_active, subscription_fee, billing_cycle, subscription_status active/past_due/**dunning**/suspended, next_billing_date, language_preference, **business_type***, invoice_counter); `subscription_payments`; **`commission_ledger*`**.
**Primary flow:** "Add Client" `POST /tenant/agent/clients` (atomic slot decrement, merchant's own login `must_change_password`, branded email, language/business_type) → first login `/force-reset` (change pwd + pick language + **business type CL-02**) → agent sets fee/cycle `PUT …/subscription` → client `GET /tenant/client/subscription` + pay `POST …/subscription/pay` (agent gateway; record payment; advance billing; **write commission ledger RSL-01**) → non-payment `POST …/suspend-overdue` or gateway webhook → suspended. **Vision:** dunning job retries + reminders before suspend; proration on plan change; merchant subscription invoice (PRN-08).
**Alternate:** no free slot→409 ("upgrade your package"); duplicate email→409; fee≤0→400; card decline→402 + billing NOT advanced; suspended login→403; recovery→active.
**Side effects:** slot decrement; provisioning email (or fallback); gateway charge (or `manual`); ledger row; **commission split row (vision)**.
**Cross-deps:** consumes slot pool (MA); language/business_type→L10N/POS mode; suspension→auth invariant; pay→RSL.
**Completion criteria:** CL-01 merchant's own login + atomic slot ✓; CL-02 first-login language **+ business_type** (business_type `absent` — finding); CL-04 pay records + advances, decline 402 ✓; CL-05 suspension blocks at auth ✓; **CL-06 dunning** (absent); **CL-07 proration** (absent); **CL-08 merchant invoice** (absent).
**Open questions/gaps:** `next_billing_date` advances fixed 30/365 days, not calendar months `(inferred)`. CL-02 currently picks language only; **business_type selection drives retail/restaurant POS mode** and must be added.

### 4.4 (POS) POS Terminal — Core / Retail — `routers/pos.py`, `features.py`, `pages/POSTerminal.tsx`, `lib/offlineQueue.ts`, `lib/thermalPrint.ts` (POS-01..14)
**Purpose:** Ring a sale, take (split, Saudi-real) payment, produce a ZATCA Arabic invoice, deduct inventory, accrue/redeem loyalty, accumulate into the shift, deliver the receipt; refund (partial/line) via credit note; hold/recall; work offline.
**Market vs SRS vs code:** market expects terminal payments, hold/recall, partial refund, weighted items, tips; SRS adds POS-09 shift, POS-10 hold, POS-11 weighted/open-price, POS-12 offline cap, POS-13 tips; **code:** atomic sale + split-by-label + ZATCA + inventory + loyalty + shift + offline `built`; **payment is a label not a terminal capture (see PAY)**; **refund whole-invoice only** `shallow`; **hold/recall, weighted, tips, void `absent`**.
**Actors:** client/staff (`get_client_for_user`); refund gated `require_permission("pos.refund")`; void `pos.void`; price override `pos.price_override`; email/SMS gated by features.
**Entities & states:** `transactions` (completed/held/refunded/partial_refunded/credit_note), `products.quantity`, `product_branch_stock`, `payment_tenders*`, `shifts`, `loyalty_points`, `zatca_documents`.
**Primary flow (one atomic txn):** cart → "Pay" `POST /pos/transaction` {items, payments[] split, customer_id, redeem_points, branch_id, discount, tips*}: ① subtotal; loyalty redemption pre-VAT discount; ② VAT@effective global rate; ③ **validate split sums to total ±0.01; for card tenders capture terminal approval (PAY-05)**; ④ counter++, assign `INV-<client>-<counter>`, timestamp; ⑤ insert txn; deduct inventory (branch ledger if `branch_id` else client-level; insufficient & `!allow_negative_stock`→400 rollback); ⑥ accrue loyalty; ⑦ accumulate shift; ⑧ ZATCA sign (UBL→hash→ECDSA→PIH advance→`zatca_documents` signed→TLV QR onto txn); ⑨ commit; ⑩ post-commit background: Fatoora report/clear, `sale.completed` webhook, low-stock alert. Response: `zatca_qr` (TLV), `zatca_qr_base64` (PNG), loyalty + tender outcome → **always-Arabic** receipt; offers print (`/escpos`), PDF (`/pdf`), HTML (`/invoice`), email/SMS.
**Alternate:** not client→403; split mismatch→400; insufficient stock→400 rollback; **terminal decline→sale blocked, nothing persists**; refund of credit-note/already-refunded→400; offline→IndexedDB + auto-sync `/production/offline/sync` (dedup `offline_id`); barcode via camera `BarcodeDetector` or scanner/SKU; ZATCA sign failure→whole sale rolls back; **hold→`held`, recall resumes (vision)**.
**Side effects:** inventory, counter, ZATCA QR/stamp+chain, `zatca_documents`, **payment tender capture**, loyalty, shift, webhooks, low-stock email.
**Refund (POS-07/13):** `POST /pos/transactions/{id}/refund` — **must support full, partial, and line-level** + exchange; type-381 credit note referencing the original; restore inventory (branch-aware); net the shift; **refund the original tender (PAY-10)**; original→refunded/partial_refunded.
**Completion criteria:** atomic sale rolls back wholly on any failure ✓ (POS-01, ZA-04); split tenders validated ✓ but **must be real captures not labels** (PAY); Arabic invoice + QR ✓ (POS-03); email/SMS gated ✓ (POS-04); offline idempotent ✓ (POS-05/12); barcode camera+name ✓ (POS-06); **partial/line refund** (shallow — finding POS-07); **shift open/close + Z-report** (see RPT-06/POS-09); **hold/recall** (absent POS-10); **weighted/open-price** (absent POS-11); **tips** (absent POS-13).
**Open questions/gaps:** ZATCA signs **every** sale regardless of `zatca_enabled` — confirm always-on vs per-client (ZA-09). Payment "split" records method labels but no gateway/terminal capture — the single biggest POS gap (PAY).

### 4.5 (RST) Restaurant Operations — `routers/restaurant.py*`, `pages/POSTerminal.tsx` (restaurant mode)*, `FloorMap.tsx*`, `KDS.tsx*` (RST-01..10) — **ENTIRELY VISION**
**Purpose:** Run a restaurant: floor/tables, order types, courses, modifiers/combos, KDS/KOT, aggregators, recipe depletion, service charge.
**Market vs SRS vs code:** Foodics-class table-stakes; **code: absent** (no tables/KDS/modifiers/order-tickets anywhere).
**Actors:** server/cashier/kitchen; gated by `require_feature("restaurant")` and `business_type ∈ {restaurant, both}`.
**Entities & states:** `tables`/`floor_zones` (free/occupied/bill-printed), `order_tickets` (open/held/fired/settled/void, course_state), `modifiers`/`modifier_groups`/`combos`, `kds_tickets`/`prep_stations`, `channel_orders` (aggregators).
**Primary flow:** pick floor/table → open ticket → add items (with required/optional modifiers, combos) by course → **fire to KDS/kitchen printer per station** → bump/recall → print non-fiscal **check** (PRN: طلب) → settle (→ ZATCA invoice via the POS atomic path) → free table. Transfer table, merge/split bill (by seat/amount/item).
**Alternate:** takeaway/delivery order types skip table; aggregator order ingests to KDS + reconciles to sale/stock (RST-08) — **via Deliverect-class middleware or a Delivery Hero POS-partner integration, NOT direct aggregator APIs (none are public)**; recipe depletion deducts BOM components on settle (RST-09); service charge as a non-VAT line (RST-10, ZATCA-correct).
**Side effects:** KDS fire, kitchen print, table state, stock (incl. recipe BOM), channel reconciliation.
**Completion criteria:** floor map + table states (RST-01); order types drive flow (RST-02); courses/transfer/split (RST-03,07); modifiers/combos priced (RST-05); **KDS/KOT fire+bump** (RST-06); check-before-pay then fiscal invoice on settle (RST-04); aggregator ingest (RST-08). **All absent today → a large coherent backlog.**
**Open questions/gaps:** entire vertical is greenfield — needs schema (tables/tickets/modifiers/KDS), a restaurant POS mode toggled by `business_type`, a real-time channel (WS/SSE) for KDS, and PRN-06 KOT printable.

### 4.6 (PAY) Payments (Saudi-real) — `routers/payment.py`, `payments_terminal.py*`, `services/payment.py`, gateway adapters* (PAY-01..10) — **MOSTLY VISION**
**Purpose:** Accept how Saudis pay — Mada, Apple Pay, STC Pay, BNPL, cash, split — via integrated terminals and Saudi gateways, capturing real approvals; never store PANs.
**Market vs SRS vs code:** table-stake #1; **code:** `payment.py` Stripe Checkout exists but is **orphaned** (no caller); subscription uses Stripe Connect (`tenant.py`); POS records `payment_method`/`payment_breakdown` **labels only**. **No Mada, Apple Pay, STC Pay, BNPL, or terminal capture.**
**Actors:** client/staff at checkout; agent configures the gateway/terminal.
**Entities & states:** `payment_tenders` (type, amount, network, approval_code, rrn, gateway_ref, last4, token; authorized/captured/declined/refunded); `payment_accounts` (owner, gateway, credentials_enc); `terminals` (client/branch, type, serial, status).
**Primary flow:** at "Pay" the cashier picks tender(s); for a card/Mada tender the POS calls `POST /payments/terminal/charge` {terminal_id, amount} → terminal prompts customer → returns approval/RRN/network (or decline) → tender row captured → included in the atomic sale; for wallet/BNPL/online, hosted checkout / payment link (PAY-07). Settlement report `GET /payments/settlement` reconciles per-tender vs acquirer (PAY-08).
**Alternate:** terminal/gateway unconfigured→sandbox/simulation or clear error; decline→**sale blocked**; partial approval→re-prompt; refund→original tender (PAY-10).
**Side effects:** tender capture onto the invoice; settlement records; **no PAN stored** (PAY-09/SEC-06).
**Completion criteria:** Mada first-class with network+RRN on invoice (PAY-01); Apple Pay/STC Pay (PAY-02); BNPL Tabby/Tamara (PAY-03); split across all (PAY-04); **terminal push+capture** (PAY-05); pluggable Saudi gateways (PAY-06); payment links/hosted checkout (PAY-07); settlement reporting (PAY-08); PCI-scope-minimized (PAY-09); refund-to-origin (PAY-10). **All largely absent → core backlog.**
**Open questions/gaps:** market research resolves the provider split — **online** (payment links, subscriptions, BNPL) → **Moyasar first** (SAMA-licensed, best KSA docs, Mada/Apple Pay/STC Pay), with Tap/HyperPay/PayTabs behind the abstraction; **in-store terminal/SoftPOS** → **Geidea (Android SDK)** — the online gateways do **not** do in-store capture, so PAY-05 and PAY-06 are two integrations. **SoftPOS is Android-only in KSA**; Tap-to-Pay on iPhone is not yet launched there (roadmap). Today's "split payment" must be reclassified from "built" to a **façade** until a real capture exists.

### 4.7 (INV) Inventory & Catalog Depth — `routers/features.py` (`/products/*`), triads, `services/branch_stock.py`, `purchase_orders.py` (INV-01..11)
**Purpose:** Catalog + multi-branch stock + variants + transfers + counts + purchase orders + COGS/valuation + reorder.
**Market vs SRS vs code:** Rewaa-class depth; **code:** products (name_ar/barcode/cost/qty/vat), categories, multi-branch stock, PO receive, low-stock, bulk import `built`; **variants, stock transfers, stock counts/adjustments, reorder points, COGS/valuation `absent`**.
**Actors:** client/staff; product edits gated `products.edit`.
**Entities & states:** `products`, `product_variants*`, `categories`, `product_branch_stock`, `purchase_orders` (draft/ordered/partially_received/received), `suppliers`, `stock_transfers*`, `stock_counts*`, `stock_adjustments*`.
**Primary flow:** catalog CRUD (`/products/list|create|{id}|low-stock` + triad); branch stock allocate `PUT /pos/branches/{id}/stock`; PO create→`POST /entities/purchase_orders/{id}/receive` (full/partial, set cost, +stock, COGS). **Vision:** variants (each a sellable SKU/barcode/stock); transfers (send/receive between branches); counts/adjustments with reasons→variance; reorder points→low-stock + auto-PO suggestion; COGS (moving average/FIFO)→margin.
**Alternate:** PO already received→400 idempotent; bad `items_json`→empty; insufficient on transfer→400.
**Side effects:** product/branch quantity, cost_price, COGS, variance records.
**Completion criteria:** catalog CRUD + search/filter + low-stock ✓ (INV-01,02,03); PO receive once, COGS (INV-07 ✓ partial — verify COGS feeds margin); **variants (INV-04 absent)**; **transfers (INV-05 absent)**; **counts/adjustments (INV-06 absent)**; **reorder (INV-08 absent)**; **COGS/valuation (INV-09 absent)**; bulk import ✓ (INV-11).
**Open questions/gaps:** PO receive increments **client-level** quantity, not a branch ledger — confirm multi-branch receiving intent. Variants are a retail table-stake currently missing.

### 4.8 (CRM) Customers, Loyalty & Marketing — `services/loyalty.py`, triads, `production.py` (`/loyalty/*`), `pages/CustomerManagement.tsx`, `LoyaltyProgram.tsx` (CRM-01..06)
**Purpose:** Customers (with VAT for B2B), loyalty, gift cards/store credit, segments/LTV, SMS/WhatsApp marketing.
**Market vs SRS vs code:** **code:** customer CRUD + loyalty accrual/redeem (feature-gated) + manual point adjust `built`; **gift cards/store credit, segments/tags/LTV, marketing campaigns `absent`**.
**Actors:** client/staff; loyalty gated `require_feature("loyalty")`.
**Entities & states:** `customers` (+`vat_number*` for B2B), `loyalty_programs` (points_per_sar, redemption_rate, min_redemption), `loyalty_points` (balance/earned/redeemed), `gift_cards*`/`store_credit*`.
**Primary flow:** configure program; on a sale with `customer_id` accrue `floor(total*points_per_sar)`; `redeem_points` → pre-VAT discount bounded by subtotal — both inside the sale txn. Manual adjust (add/deduct + reason). **Vision:** issue/redeem gift cards (as a tender PRC-05); segments/tags + RFM-lite; consent-aware SMS/WhatsApp campaigns (PDPL).
**Alternate:** redeem without `customer_id`→400; no active program→accrual skipped, sale proceeds.
**Completion criteria:** accrual/redemption atomic + feature-gated ✓ (CRM-02); customer VAT for B2B invoices (verify CRM-01 vat_number); **gift cards/store credit (CRM-03 absent)**; **segments/LTV (CRM-04 absent)**; **marketing (CRM-05 absent)**.
**Open questions/gaps:** customer `vat_number` needed to drive ZATCA B2B clearance (ZA-06) — verify it exists and flows into the invoice buyer block.

### 4.9 (PRC) Pricing & Promotions — triads + POS validation, `pages/DiscountManagement.tsx` (PRC-01..06)
**Purpose:** Discounts, coupons/auto-promos, BOGO/bundles, segment/branch pricing, gift cards, scheduled pricing.
**Market vs SRS vs code:** **code:** %/flat discounts with min_purchase, usage caps `built`; **coupons/auto-promos, BOGO/bundle, price lists, scheduled pricing `absent`**.
**Entities & states:** `discounts` (percentage/fixed, value, min_purchase, usage_count, max_uses, is_active), `promotions*`, `coupons*`, `price_lists*`.
**Primary flow:** define discount → validated at POS (type, min_purchase, caps) → applied pre-VAT. **Vision:** coupon code entry at POS; time-window auto-promotions; BOGO/quantity-break/bundle; customer-/segment-/branch-specific price lists; gift-card redemption tender.
**Completion criteria:** %/flat discounts apply at sale ✓ (PRC-01); **coupons/auto-promos (PRC-02 absent)**; **BOGO/bundle (PRC-03 absent)**; **price lists (PRC-04 absent)**; gift cards (PRC-05, with CRM-03).
**Open questions/gaps:** verify discount permission gating (`pos.discount`/price_override) and that usage_count increments atomically with the sale.

### 4.10 (RPT) Reporting & Analytics — `routers/features.py` (`/reports/*`), `production.py` (`/analytics/forecast`), `pages/ReportsAnalytics.tsx` (RPT-01..10)
**Purpose:** Sales/period KPIs, top products, payment-method breakdown, **profit/COGS/margin**, VAT report, **Z/X reports**, inventory reports, refund/discount reports, agent/master economics, CSV+PDF export.
**Market vs SRS vs code:** **code:** sales summary, top products, CSV export, forecast stub `built/shallow`; **payment-method breakdown, margin/COGS, VAT report, Z/X report, inventory reports, refund/discount reports, economics `absent`**.
**Actors:** client/agent (own); master (economics).
**Primary flow:** `GET /reports/sales-summary?period=`, `/top-products?limit=`, `/export-csv`. **Vision:** `/reports/payment-breakdown` (RPT-03), `/reports/margin` (COGS, RPT-04), `/reports/vat` (RPT-05), `/reports/zreport?shift_id=` (RPT-06 → PRN-05), `/reports/inventory` (RPT-07), `/reports/refunds`+`/discounts` (RPT-08), `/reports/economics` (RPT-09); every report CSV **+ PDF** (RPT-10).
**Completion criteria:** sales summary + top products + CSV ✓ (RPT-01,02); **payment breakdown (RPT-03 absent)**; **margin/COGS (RPT-04 absent)**; **VAT report (RPT-05 absent)**; **Z/X report (RPT-06 absent — table-stake)**; PDF export (RPT-10 — invoices have PDF; reports CSV-only).
**Open questions/gaps:** forecast may be a thin stub — verify real aggregates. Z-report is a fiscal table-stake and is the highest-value reporting gap.

### 4.11 (FIN) Accounting & Finance — `routers/expenses.py` (triad), `integrations.py` (bulk export), `pages/ExpenseTracking.tsx` (FIN-01..05)
**Purpose:** Expenses, journal/GL export, accounting integrations (Zoho/QB/Odoo), cash management, AP basics.
**Market vs SRS vs code:** **code:** expense CRUD + revenue-vs-expense view `built`; bulk CSV export `built`; **journal/GL export, accounting integrations, AP `absent`**.
**Primary flow:** expense CRUD; cash movements tie to shift (FIN-04, with POS-09). **Vision:** `/fin/journal-export` (GL CSV: sales/VAT/COGS/payments); push to Zoho/QB/Odoo (FIN-03).
**Completion criteria:** expenses scoped to owner ✓ (FIN-01); **journal export (FIN-02 absent)**; **integrations (FIN-03 absent)**; cash mgmt ties to shift (FIN-04, verify with POS-09).

### 4.12 (OMN) Omnichannel — `routers/omnichannel.py*`, `channel_orders*` (OMN-01..05) — **VISION**
**Purpose:** Salla/Zid catalog+stock sync; online & aggregator orders on the back-office/POS decrementing shared stock; unified customer/loyalty; click-and-collect.
**Market vs SRS vs code:** differentiator; **code: absent.**
**Primary flow:** connect Salla/Zid → catalog+stock sync → import online orders → appear in back-office (and POS/KDS for restaurant) → **same stock pool** decremented. Aggregators feed via RST-08.
**Completion criteria:** Salla (OMN-01), Zid (OMN-02), shared-stock decrement (OMN-03), unified customer/loyalty (OMN-04), C&C (OMN-05). **All absent.**

### 4.13 (ZA) ZATCA Compliance — `services/zatca.py`, `zatca_sale.py`, `production.py::ZATCAService`, `routers/zatca.py`, `models/zatca_credentials.py`, `zatca_documents.py` (ZA-01..10) — **STRONGEST AREA**
**Purpose:** Real Phase-2 cryptographic stamping, hash-chained sequencing, TLV QR, **B2B clearance vs B2C reporting**, 6-year retention, operational visibility.
**Market vs SRS vs code:** **code:** EC key+CSR, AES-256-GCM secrets, real ECDSA stamp, PIH/ICV chain, TLV QR (tags 1–8), `zatca_documents` retention, onboarding endpoints, integrity walk `built`; **B2B clearance-vs-B2C-reporting split `shallow/unverified`**; **status dashboard + stuck-doc alerts (ZA-08) `absent`**; per-client `zatca_enabled` gating `unused`.
**Actors:** client (own credentials/documents); onboarding operator-driven.
**Entities & states:** `zatca_credentials` (private_key_enc, csr, compliance/production CSID+secret, pih, onboarded, environment); `zatca_documents` (icv, invoice_hash, previous_hash, stamp, signed_xml, status signed/reported/cleared/failed/pending, retention_until).
**Primary flow:** onboard `csr→compliance-csid→production-csid`; per sale `zatca_sale.sign_transaction` (UBL 388/381 + PIH → hash → ECDSA → advance PIH → `zatca_documents` signed → TLV QR onto txn); **route by invoice type: standard(B2B)→clearance (real-time, store cleared XML); simplified(B2C, and B2B < 1,000 SAR)→reporting within 24h** (background, retry on 5xx); integrity `GET /zatca/integrity`. **Validate hash/QR-TLV/stamp against ZATCA's official SDK.**
**Alternate:** gateway/onboarding unset→sign locally, report fails-closed to `pending`; terminal 4xx→`failed`; manual sign idempotent; missing key→400; missing VAT→placeholder.
**Completion criteria:** CSR/onboarding (ZA-01) ✓ endpoints; real ECDSA stamp (ZA-02) ✓; TLV QR (ZA-03) ✓; sequential+chained (ZA-04) ✓; ≥6y retention (ZA-05) ✓; **clearance/reporting routing (ZA-06)** — verify the standard/simplified split actually drives clearance vs reporting; sandbox/sim (ZA-07) ✓; **status dashboard + alerts (ZA-08 absent)**; **`zatca_enabled` policy intentional (ZA-09)**; integrity (ZA-10) ✓.
**Open questions/gaps (BIG):** crypto is real+local, but **live Fatoora reporting only runs after operator onboarding** — default install sits at `pending`. ZA-08 demands this be **visible + alertable**. ZA-06 B2B clearance vs B2C reporting must be confirmed as actually routed (not all-reporting). `zatca_enabled` per-client flag is unused — decide always-on vs optional (ZA-09).

### 4.14 (RSL) Reseller Platform Economics — `routers/commission.py*`, `tenant.py`, `pages/AgentDashboard.tsx`, `MasterDashboard.tsx` (RSL-01..08) — **MOSTLY VISION**
**Purpose:** Commission/revenue-split ledger; agent & master revenue reports; impersonation; merchant health; platform economics.
**Market vs SRS vs code:** table-stake for Product B; **code:** subscription payments recorded `built`; **split not computed**; **impersonation, health view, economics `absent`**; password reset `shallow`.
**Entities & states:** `subscription_payments`, `commission_ledger*` (subscription_payment_id, agent_id, gross, master_cut, agent_net).
**Primary flow:** on each subscription pay (CL-04) write a `commission_ledger` row (gross, master_cut per package wholesale, agent_net) → agent revenue report `GET /tenant/agent/revenue` (collected, master-owed, net, by client/period) → master `GET /tenant/master/economics` (owed-by-agent, MRR, churn, agent leaderboard). Impersonation `POST /tenant/agent/clients/{id}/impersonate` (audited, scoped token). Merchant health on agent dashboard.
**Completion criteria:** **commission ledger (RSL-01 absent — finding)**; agent/master revenue reports (RSL-02,03 absent); **impersonation (RSL-05 absent)**; password reset (RSL-06 — verify); health (RSL-07 absent); economics (RSL-08 absent).
**Open questions/gaps:** SRS 2.1's "commission due to Master" has **no computed split** today — the central Product-B gap.

### 4.15 (L10N) Multi-Language & Localization — `lib/i18n.ts`, `format.ts`, `core/formatting.py`, `contexts/BrandingContext.tsx` (L10N-01..06) — **BUILT**
**Purpose:** ar/en/hi/ur UI, RTL for ar/ur, locale numbers/dates, agent-default + client-override, Arabic-only fiscal docs.
**Market vs SRS vs code:** **code:** built; verify completeness.
**Primary flow:** `LanguageProvider`/`useLanguage()` → `t(key)`, `setLanguage`, `isRTL`; switching updates `localStorage`, `dir`/`lang`, re-renders; Arabic-Indic digits for ar/ur; Gregorian (Hijri optional); on login apply agent `default_language` unless user already chose.
**Completion criteria:** four locales, **every key present in each** (L10N-01 — verify no missing key hidden by English fallback); RTL ar/ur (L10N-02) ✓; Arabic-Indic digits + SAR (L10N-03) ✓; Gregorian + optional Hijri (L10N-04) ✓; agent default + override (L10N-05) ✓; **all fiscal docs Arabic (L10N-06)** ✓.
**Open questions/gaps:** confirm no locale object is missing keys present in others (silent fallback hides it).

### 4.16 (HW) Hardware — `lib/thermalPrint.ts`, `services/escpos.py`, `payments_terminal.py*` (HW-01..08)
**Purpose:** Thermal printer, scanner, **payment terminal**, cash drawer, customer display, kitchen printer/KDS, scale, label printer.
**Market vs SRS vs code:** **code:** ESC/POS thermal print (WebUSB) + camera/scanner barcode + customer display `built`; **payment terminal, cash-drawer kick, kitchen printer/KDS, scale, label printer `absent`**.
**Completion criteria:** thermal+QR (HW-01) ✓; scanner (HW-02) ✓; **terminal (HW-03 absent → PAY-05)**; drawer kick (HW-04 — verify ESC/POS pulse); customer display (HW-05) ✓; **kitchen printer/KDS (HW-06 absent → RST-06)**; scale (HW-07 absent); label printer (HW-08 absent → PRN-07).

### 4.17 (SEC) Security, Privacy & Compliance — `core/auth.py`, `security.py`, `dependencies/*`, `services/audit.py`, middlewares (SEC-01..08)
**Purpose:** Auth/session, tenant isolation, granular RBAC, encrypted secrets, **PDPL**, **PCI-scope minimization**, audit completeness, rate-limit/validation/CORS.
**Market vs SRS vs code:** **code:** bcrypt + JWT access/refresh + revocation + RBAC + audit + AES-256 ZATCA secrets + env-gated rate-limit/CORS `built`; **PDPL (consent/export/delete), PCI-scope policy, session-timeout policy `absent/implicit`**.
**Completion criteria:** auth+revocation (SEC-01) ✓; **tenant isolation (SEC-02)** — verify across every triad, not assumed; granular RBAC deny-wins (SEC-03) ✓; secrets encrypted (SEC-04) ✓; **PDPL (SEC-05 absent)**; **PCI minimization (SEC-06)** — currently moot (no real card handling) but must hold once PAY lands; **audit completeness (SEC-07)** — verify coverage of all mutations; rate-limit/validation/CORS (SEC-08) ✓ env-gated.
**Open questions/gaps:** PDPL consent for marketing (CRM-05) and data-subject export/delete are absent. Audit completeness historically "partial" — verify.

### 4.18 (OPS) Operations & Reliability — `main.py`, middlewares, `core/database.py`, `routers/production.py`, `health.py`, `api_usage.py` (OPS-01..08)
**Purpose:** Migrations, atomicity, backups/DR, observability, pagination, search, metering, graceful degradation.
**Market vs SRS vs code:** **code:** atomic sale, Sentry/health/metering/rate-limit env-gated, global search `built`; **Alembic migrations `absent` (runtime create/ALTER)**; **backups/DR `absent`**; **server-side pagination `partial`** (`/products/list` paginates; `/all` + many triad lists load everything).
**Completion criteria:** **migrations (OPS-01 absent — Critical)**; sale atomicity (OPS-02) ✓; **backups/DR (OPS-03 absent)**; observability (OPS-04) ✓ env-gated; **pagination everywhere (OPS-05 partial)**; global search (OPS-06) ✓; metering/rate-plans (OPS-07) ✓ partial; graceful degradation (OPS-08) ✓.
**Open questions/gaps:** migrations and pagination are explicitly known-incomplete in the SRS addendum; both are real findings.

### 4.19 (UX/PRN) Design System & Printables — `components/*`, `contexts/BrandingContext.tsx`, `services/pdf_render.py`, `escpos.py`, `production.py::PDFInvoiceService` (UX-01..08, PRN-01..09)
**Purpose:** One brand-tokened, RTL-correct design system; every page renders all states; customer display; notification center; the full printable set.
**Market vs SRS vs code:** **code:** design system via brand tokens + shadcn `built`; thermal receipt, A4 invoice, credit note, quotation (Arabic) `built`; **Z-report, KOT, label, subscription-invoice, dunning printables `absent`**; notification center `shallow` (in-memory).
**Completion criteria:** design system + RTL + brand tokens (UX-01) ✓; **every page defines loading/empty/error/permission/offline states (UX-02)** — audit per §5; touch POS + responsive (UX-03) ✓ partial; role nav (UX-04) ✓; customer display (UX-07) ✓ (verify wiring); **persisted notifications (UX-08 shallow)**; printables per §6 (PRN-01..04 ✓; PRN-05/06/07/08 absent).
**Open questions/gaps:** notification persistence (in-memory today). Per-page state coverage is the main DESIGN_GAP surface — see §5.

## 5. Page & dashboard design specs

Every screen below specifies **Goal · Layout · Key components · States · Actions→endpoints · Design intent**. Universal rules: RTL-mirrored for ar/ur; brand tokens only (no hardcoded color); every screen renders **loading / empty / error / permission-denied / offline**; an offline banner + queued-count appears whenever the network is down; all money is SAR with locale digits. A screen missing any of these states is a `DESIGN_GAP`.

### 5.A Public & Auth

**Login (`Index.tsx`, `/login`, public).** Goal: authenticate. Layout: centered card on a branded split background; agent brand if served under a custom domain (AG-05). Components: email/password, login/register toggle (register hidden when `ALLOW_REGISTRATION=false`), language switcher, "forgot password" (vision). States: submitting (spinner), error (inline 401), locked/suspended (403 message). Actions: `POST /auth/login` → fetch `/tenant/role` → route by role; register `POST /auth/register`. Intent: minimal, fast, brand-forward; Arabic default in KSA.

**Force-Reset (`ForceResetPassword.tsx`, `/force-reset`, authenticated first-login).** Goal: clear `must_change_password`, pick language, **pick business type (CL-02: retail/restaurant/both)**. Layout: single guided card, stepper. Components: new/confirm password (strength), language radio, **business-type radio (vision)**. States: validating, mismatch error. Actions: `POST /users/change-password` (+ language + business_type persist). Intent: one-time, unskippable; business_type drives POS mode.

**Agent Landing / Funnel (`AgentLandingPage.tsx`, `/d/:agentId`, public).** Goal: market the agent's brand + convert a trial (AG-10/CL-11). Layout: hero (agent logo/colors), feature list, pricing tiers, trial CTA. Components: pricing cards, signup form. States: loading branding, agent-not-found, submitting. Actions: `GET /tenant/agent/{id}/public`; **trial signup `POST /tenant/agent/{id}/trial` (vision — must provision a trial client)**. Intent: fully branded; no platform brand. **Gap:** trial-provision not wired.

**Customer Display (`CustomerDisplay.tsx`, `/customer-display`, public/second-screen).** Goal: show live cart/total to the shopper (UX-07). Layout: large RTL list + bold total; paid confirmation screen. Components: line items (bilingual), subtotal/VAT/total, "thank you" + QR on paid. States: idle (welcome), active cart, paid. Actions: listens to `BroadcastChannel`/localStorage `pos-customer-display` from POSTerminal. Intent: glanceable from across a counter. **Verify** the POS→display channel is wired.

### 5.B Master

**Master Dashboard (`MasterDashboard.tsx`, `/master`).** Goal: govern agents + see platform economics. Layout: KPI row (agents, active clients, **MRR, churn** [vision]) → agents table (used/remaining slots, status, revenue) → actions. Components: "Add Agent" dialog (company/email/phone/package), credentials modal (one-time temp password), add-slots dialog, **global VAT dialog**, agent toggle, **economics panel (vision)**. States: loading, empty (no agents), error, 403-non-master. Actions: `GET /tenant/master/agents`; `POST /tenant/master/agents`; `…/slots`; `…/toggle`; `PUT …/tax-rate`; **`GET /tenant/master/economics` (vision)**. Intent: operator cockpit; economics must be first-class. **Gap:** MRR/churn/revenue-by-agent.

**Package Management (`PackageManagement.tsx`, `/packages`, master).** Goal: define packages + entitlements. Layout: package grid + editor. Components: package card (slots, wholesale, suggested retail, **feature-tier (vision)**), create/edit/delete. States: loading/empty/error. Actions: `/api/v1/packages/*`. Intent: pricing control; **verify** package→entitlement (MA-07).

**Admin Settings / Env Editor (`api/settings.ts` consumer page, `/admin/settings`, master).** Goal: read/edit backend+frontend env config. Layout: grouped key/value table with descriptions. Components: edit/add/delete per key, "requires restart" banner. States: loading/error/saving. Actions: `GET/PUT/POST/DELETE /admin/settings/...`. Intent: powerful + guarded; confirm destructive edits. (This page is **live but undocumented** historically — now first-class.)

**Global ZATCA Settings (master, MA-09 — vision).** Goal: set gateway creds + env (sandbox/sim/prod). Layout: form + status. Components: env selector, gateway credentials (write-only), document-status summary (ZA-08). Actions: `PUT /tenant/master/zatca-env`, `GET /zatca/status`. **Gap:** mostly absent.

### 5.C Agent

**Agent Dashboard (`AgentDashboard.tsx`, `/agent`).** Goal: provision/manage clients + see margin. Layout: KPI row (total clients, remaining slots, monthly revenue, **net margin** [vision]) → clients table (status, subscription, **health** [vision]) → actions. Components: "Add Client" dialog (name/email/fee/cycle/language/**business_type**/features), credentials modal, client toggle/suspend, per-client feature dialog, **"log in as" (impersonation, vision)**, **revenue panel (vision)**. States: loading/empty/error/slot-exhausted (CTA "upgrade package"). Actions: `GET/POST /tenant/agent/clients`; `…/toggle`; `…/features`; `PUT …/subscription`; `…/suspend-overdue`; **`…/impersonate`, `GET /tenant/agent/revenue` (vision)**. Intent: reseller control center; margin + health are table-stakes. **Gaps:** impersonation, revenue/commission, health.

**Branding Editor (`BrandingEditor.tsx`, `/branding`, agent).** Goal: white-label depth. Layout: live-preview split (form left, device preview right). Components: logo upload (preview), color pickers, font, button-radius, default language, **custom domain + DNS status (vision)**, **email-template editor (vision)**, **printable header/footer (vision)**. States: uploading, >2 MB (413), bad MIME (400), saving. Actions: `POST /tenant/agent/logo`; `PUT /api/v1/branding/update`; **`POST /tenant/agent/domain`, `PUT /tenant/agent/email-templates` (vision)**. Intent: WYSIWYG; no platform brand ever. **Gaps:** domain, email, printable branding.

### 5.D Client back-office

**Client Dashboard (`ClientDashboard.tsx`, `/client`).** Goal: business at-a-glance + subscription. Layout: KPI cards (today sales, txns, total sales, product count) → quick actions (POS, products, reports, staff) → subscription panel → recent transactions. Components: stat cards, pay-now, payment history, recent-txn table. States: loading/empty/error/suspended. Actions: `GET /tenant/client/dashboard`, `/tenant/client/subscription`, `POST …/subscription/pay`. Intent: owner's morning glance; one tap to POS.

**Subscription / Billing (part of ClientDashboard; vision page).** Goal: view plan, pay, see invoices. Components: plan, next billing, status badge, pay (gateway), **billing history with downloadable invoices (CL-09, PRN-08)**, **dunning notice (vision)**. Actions: `GET /tenant/client/subscription`, `POST …/pay`. **Gaps:** merchant invoices, dunning UI.

### 5.E POS

**POS Terminal — Retail mode (`POSTerminal.tsx`, `/pos`).** Goal: ring a sale fast. Layout (tablet, touch): left = product grid/categories + search + scan; right = cart + totals + **tender panel**; sticky "Pay". Components: barcode (camera `BarcodeDetector` + scanner), search, category nav, quick-keys (POS-14), cart lines (qty/discount/void/note/price-override [permissioned]), customer attach (loyalty), branch selector, **discount/coupon**, **hold/recall (POS-10, vision)**, **tender panel: cash/Mada/Apple Pay/STC Pay/BNPL/split + terminal capture (PAY)**, refund mode (full/partial/line). States: loading catalog, empty cart, **offline (banner + queued count)**, payment processing, **terminal declined (blocks)**, insufficient stock. Actions: `POST /pos/transaction`; `POST /payments/terminal/charge` (vision); `/transactions/{id}/refund|invoice|pdf|escpos|email|sms`; offline `/production/offline/sync`. Intent: thumb-reachable Pay; sub-second; never blocks on network. **Gaps:** real tender capture, hold/recall, partial refund UI, weighted/open-price, tips.

**POS Terminal — Restaurant mode (`/pos` when business_type∈{restaurant,both}; vision).** Goal: table service. Layout: starts at **floor map**; opening a table → order screen (menu with modifier dialogs, course tabs). Components: table picker, order-type switch (dine-in/takeaway/delivery), modifier/combo dialogs, course grouping, **fire-to-kitchen**, print check, transfer/merge/split bill, settle→tender panel. States: table free/occupied/bill-printed, ticket open/held/fired/settled, offline. Actions: `restaurant.py*` ticket endpoints; KDS fire; settle→`POST /pos/transaction`. Intent: Foodics-grade service flow. **Entirely vision.**

**Floor Map (`FloorMap.tsx`, vision).** Goal: see/seat tables. Layout: zone tabs + table tiles colored by state + occupancy/elapsed. Components: table tiles, new-order, transfer. Actions: `GET/PUT /restaurant/tables`. **Vision.**

**Kitchen Display (`KDS.tsx`, vision).** Goal: kitchen sees live orders. Layout: column-per-station ticket lanes, timers, bump/recall. Components: order cards (items+modifiers+course), all-day counts, bump. States: real-time (WS/SSE), stale-alert. Actions: `GET /kds/tickets` (stream), `POST /kds/{id}/bump`. **Vision.**

### 5.F Catalog & Inventory

**Product Management (`ProductManagement.tsx`, `/products`, agent+client).** Goal: catalog CRUD. Layout: toolbar (search/category/低-stock filter) → paginated table → add/edit dialog. Components: row (name ar/en, barcode, price, cost, qty, VAT, active), **variants link (vision)**, image. States: loading/empty/error; permission (`products.edit`). Actions: `/api/v1/products/*` + triad; pagination server-side (OPS-05). Intent: dense, scannable, bulk-friendly.

**Variants (vision).** Per-product variant matrix (size/color → SKU/barcode/price/stock). Actions: `product_variants*` triad. **Absent.**

**Category Management (`CategoryManagement.tsx`, `/categories`).** Hierarchical categories (name, parent, icon, sort). States: loading/empty/error. Actions: triad. Intent: drives POS grid.

**Inventory — Stock counts & transfers (vision).** Goal: counts/adjustments (reasons→variance) and inter-branch transfers (send/receive). Layout: per-branch on-hand + count session + transfer wizard. Actions: `stock_counts*`, `stock_transfers*`. **Absent** (BranchManagement has a transfer dialog — verify backend or it's a dead-end).

**Suppliers & Purchase Orders (`SupplierManagement.tsx`, `/suppliers`).** Goal: vendors + inbound stock/COGS. Layout: suppliers list + PO list/editor. Components: supplier CRUD, PO (supplier, items, cost, status), **receive (full/partial)**. States: PO draft/ordered/received; already-received→disabled. Actions: triads + `POST /entities/purchase_orders/{id}/receive`. Intent: receiving updates stock+COGS exactly once.

### 5.G Customers, Loyalty, Promotions

**Customer Management (`CustomerManagement.tsx`, `/customers`).** CRUD (name/phone/email/**vat_number** for B2B/notes), purchase history, visit count. States: loading/empty/error. Actions: triad. Intent: fast lookup at POS; VAT enables B2B clearance.

**Loyalty Program (`LoyaltyProgram.tsx`, `/loyalty`, client).** Config (points_per_sar, redemption_rate, min) + customer balances + history + manual adjust (reason). Feature-gated (`loyalty`). States: loading/empty/disabled-feature. Actions: `loyalty_programs` triad, `/production/loyalty/*`. Intent: simple, transparent ledger.

**Marketing (vision).** Consent-aware SMS/WhatsApp campaigns (CRM-05, PDPL). **Absent.**

**Discounts / Promotions (`DiscountManagement.tsx`, `/discounts`).** Discount codes (%/flat, min_purchase, max_uses, validity, active); **coupons/BOGO/price lists (vision)**. States: loading/empty/error. Actions: triad; validated at POS. Intent: clear rules; permissioned at POS.

**Gift Cards (vision).** Issue/redeem/balance/expiry (CRM-03/PRC-05). **Absent.**

### 5.H Reports & Shifts

**Reports & Analytics (`ReportsAnalytics.tsx`, `/reports`, agent+client).** Goal: KPIs + exports. Layout: period selector → KPI cards (revenue, txns, avg order) → sales chart → top-products table → export. Components: **payment-breakdown, margin/COGS, VAT, refund/discount panels (vision)**, **Z-report view (vision)**, CSV **+ PDF** export. States: loading/empty/error; ≤2 s (NFR). Actions: `/reports/*`; vision `/reports/payment-breakdown|margin|vat|zreport|economics`. Intent: profit-first, not revenue-only. **Gaps:** breakdown, margin, VAT, Z-report.

**Shift Management (`ShiftManagement.tsx`, `/shifts`, client).** Goal: drawer lifecycle. Layout: current shift card + open/close + history. Components: open (float), **pay-in/out, cash-drop (vision)**, close (counted cash → expected/variance), **Z-report print (PRN-05, vision)**, history. States: open/closed/none. Actions: `/production/shifts/open|close|current|history`. Intent: reconcile honestly; close must emit a Z-report. **Gap:** Z-report, pay-in/out.

### 5.I Org & People

**Branch Management (`BranchManagement.tsx`, `/branches`, client).** Branches CRUD (name/address/manager/phone/is_main) + per-branch inventory + **transfer (verify backend)**. States: loading/empty/error. Actions: triad + `/pos/branches/{id}/stock`. Intent: isolate per-branch stock.

**Staff & Permissions (`StaffManagement.tsx`, `/staff`, agent+client).** Staff CRUD (name/email/phone/role/active) + **granular permission matrix (refunds/reports/voids/price-override/product-edit)**. States: loading/empty/error. Actions: `staff_members` triad, `permissions` triad, `/auth/me/permissions`. Intent: explicit-deny removes capability + hides UI. **Verify:** staff independent login provisioning (`inferred`).

### 5.J Documents, Integrations, Account

**Quotation Management (`QuotationManagement.tsx`, `/quotations`).** Create quote (items/valid_until/notes) → **always-Arabic non-fiscal document** (عرض سعر, marked "غير ضريبية"). States: loading/empty/error. Actions: triad + `GET /entities/quotations/{id}/document`. Intent: visually distinct from a tax invoice.

**Webhook Management (`WebhookManagement.tsx`, `/webhooks`).** Endpoints (url/events/secret/active) + delivery log. Actions: triad; HMAC-signed dispatch on `sale.completed`/`refund.created`. States: loading/empty/error.

**Audit Log (`AuditLog.tsx`, `/audit`).** Filterable activity (action/date/user/ip/entity/changes-redacted) + **export (vision)**. Actions: `audit_logs` triad. Intent: immutable-ish trail; verify mutation coverage (SEC-07).

**Notifications (`Notifications.tsx`, `/notifications`).** Feed (low-stock, **ZATCA-failed, subscription, KDS** [vision]) + mark-read. **Must be persisted (UX-08)** — currently in-memory. Actions: `/notifications/list|mark-read`.

**User Profile (`UserProfile.tsx`, `/profile`).** Profile (name), change password, preferences (notifications, theme, language). Actions: `/users/profile`, `/users/change-password`. States: saving/error.

**Settings (vision, per-client).** Business profile (VAT number, address, logo for printables), tax class defaults, receipt template (`receipt_templates` — backend exists, **no UI today → dead-end to wire, PRN/AG-07**), ZATCA onboarding status, payment/terminal setup (PAY), feature status. Intent: the merchant's control panel. **Largely absent.**

## 6. Printable specs

**Global printable invariant:** every **fiscal** document (receipt, tax invoice, credit note, quotation) renders in **Arabic, RTL, Arabic-Indic digits, SAR**, regardless of UI language (L10N-06). Branded header/footer per agent/client (AG-07). Fiscal docs carry the ZATCA TLV QR + cryptographic stamp; non-fiscal docs are clearly marked non-tax.

| PRN | Document | Size/medium | Status | Required sections (in order) |
|---|---|---|---|---|
| PRN-01 | **Thermal receipt** | 80mm ESC/POS (WebUSB/BT/net) | **built** (`escpos.py`, `thermalPrint.ts`) | branded header (logo/name/VAT) · invoice no + datetime · cashier/shift · line items (name_ar, qty, price, total) · subtotal/discount/VAT/total · **tender breakdown incl. network/RRN (vision)** · ZATCA TLV QR · footer (return policy/thanks) |
| PRN-02 | **A4 tax invoice** | A4 PDF + print (`pdf_render.py`, Amiri font; Latin fallback) | **built** | seller block (name/VAT/address) · **buyer block (B2B: name/VAT)** · invoice no/UUID/ICV · datetime · items table · subtotal/discount/VAT-by-rate/total · ZATCA QR + stamp · standard-vs-simplified marker |
| PRN-03 | **Credit note (381)** | A4 + thermal | **built (whole-invoice); partial vision** | "إشعار دائن" · reference to original invoice no · reason · negative/returned lines · VAT reversal · QR + stamp |
| PRN-04 | **Quotation / عرض سعر** | A4 PDF (always Arabic) | **built** | header "عرض سعر — غير ضريبية / not a tax invoice" · customer · items/totals · valid_until · notes · NO QR/stamp |
| PRN-05 | **Z-report / X-report** | 80mm + A4 | **absent** | branch/shift/staff · open/close times · **sales by tender (cash/Mada/card/wallet/BNPL/loyalty)** · VAT collected · discounts · voids · refunds · pay-in/out · expected vs counted cash · variance |
| PRN-06 | **Kitchen ticket (KOT)** | 80mm per station | **absent** | order/table no · order type · time · items + **modifiers** by course · station routing · NO prices |
| PRN-07 | **Barcode / shelf label** | label printer | **absent** | product name_ar · price (SAR) · barcode · (variant) |
| PRN-08 | **Subscription invoice** (agent→client) | A4 PDF | **absent** | agent (seller) block · client (buyer) block · period · fee · VAT (if agent VAT-registered) · payment status · branded |
| PRN-09 | **Dunning notice** | email/PDF | **absent** | overdue amount · grace deadline · pay link · branded · Arabic |

## 7. End-to-end journeys

1. **Master → agent onboarding (MA-01/02):** `/master` → create agent (package→slot pool) → agent login + `agents` row → one-time temp password → agent signs in → forced reset.
2. **Agent white-labels + provisions (AG-01..09, CL-01, L10N-05):** upload logo + colors/font + **custom domain + branded email (vision)** → toggle per-client features → "Add Client" (atomic slot, merchant's own login, **business_type**, branded email) → client logs in, forced reset + language + business_type → sees agent brand + only enabled features.
3. **Restaurant dine-in sale (RST + PAY + ZA, vision):** floor map → open table → add items + modifiers by course → fire to KDS → print check → settle: **Mada terminal tap (capture approval) + split with cash** → atomic sale → **ZATCA simplified invoice (Arabic + QR) → reported to Fatoora** → table freed.
4. **Retail sale (POS + PAY + INV + ZA):** scan items → apply coupon → **Apple Pay tender (captured)** → atomic: VAT@global, counter++, deduct **shared** stock, loyalty, shift, ZATCA sign+QR → Arabic receipt → print/PDF/email.
5. **B2B standard invoice (ZA-06):** select customer with VAT number → **standard** invoice → **cleared by Fatoora in real time** → Arabic A4 invoice emailed.
6. **Partial/line refund (POS-07/13 + PAY-10):** select original → choose returned lines → type-381 credit note referencing it → **refund to original tender** → stock restored (branch-aware) → shift netted → original → partial_refunded.
7. **Shift close → Z-report (POS-09/RPT-06):** open (float) → sales accumulate → close (count) → expected vs counted variance → **Z-report printed (PRN-05)**.
8. **Offline sale (POS-05):** offline → enqueue (IndexedDB, `offline_id`) → reconnect → `/production/offline/sync` replays each through the atomic path, deduped → server assigns ZATCA QR.
9. **Subscription → economics (CL-04, RSL-01..08):** client pays via agent gateway → ledger row → **commission split computed (master_cut/agent_net)** → agent sees margin → master sees MRR/churn.
10. **Omnichannel (OMN, vision):** Salla order imported → decrements the **same stock pool** as POS → unified customer/loyalty.

## 8. Orphaned / unwired scaffolding ledger

Built code with no reachable caller/UI — the review must rule each **dead** (remove) or **intended** (wire up). Evidence from the code survey.

| Item | Files | Evidence | Verdict request |
|---|---|---|---|
| **AI Hub** | `routers/aihub.py`, `services/aihub.py` (gentxt/genimg/genvideo/genaudio/transcribe/analyzepdf) | No frontend caller anywhere | Almost certainly MGX scaffolding → **remove** unless a use is intended. |
| **Object storage / presigned URLs** | `routers/storage.py` (buckets/objects/upload-url/download-url) | No caller; logo upload uses local disk (`uploads/logos/`) | Decide: adopt for logos/exports (S3, AG-07) or **remove**. |
| **Stripe Checkout (generic)** | ~~`routers/payment.py` (`/payments/checkout`,`/status`)~~ | No caller; subscription uses `tenant.py` Connect path | **✅ REMOVED (F-006)** — deleted; `services/payment.py` kept for the Connect subscription path. PAY-07 links, if built, ride the Moyasar/Geidea gateway, not Stripe Checkout. |
| **Blog** | `pages/blog/*`, `blog-routes.tsx`, `components/blog/*` | `App.tsx` never imports blog routes | **Remove** unless a marketing blog is wanted. |
| **OAuth callback** | `/auth/callback`, `/auth/error` routes | Local-auth-only system | Leftover OIDC scaffolding → **remove**. |
| **Duplicate bulk/search/webhook/email** | `integrations.py` vs `production.py` | Two implementations of the same capability | Consolidate to one; the other is dead. |
| **Receipt templates (no UI)** | `receipt_templates` model + triad | Rich fields, **no editor page** | **Wire up** as the printable-branding editor (AG-07/PRN) — this is a *gap*, not dead code. |

## 9. Completeness-review usage note

For each item above, a reviewer (Prompt 2 → `COMPLETENESS_REVIEW.md`) verifies the code implements **every Primary-flow step, every state transition (§3.3), every side effect, every Completion criterion, every page-design element (§5), and every printable field (§6)** — tracing `frontend control → src/lib/api.ts → atomsClient.ts → router → service → model/DB → side effect`. Report anything not fully implemented — dead-end, missing handler, unwired call, missing transition/side-effect, partial CRUD, stub/TODO, **payment/ZATCA façade**, **missing restaurant mode**, **design-state gap**, **non-Arabic fiscal doc**, **absent market table-stake**, or divergence — as a finding citing the spec item, the **SRS ID + priority**, and a taxonomy label (incl. `MARKET_GAP`, `DESIGN_GAP`). Before reporting, **try to refute** (the triad + auto-discovery provide generic CRUD; many models use `extend_existing=True`; integrations may live under a different name). 

**Highest-value audit targets (the five market gaps + the operator gaps):** (1) **PAY** — Saudi tenders + terminal capture (today's "split" is a façade); (2) **RST** — restaurant mode existence (entirely absent); (3) **POS-07** — partial/line refunds; (4) **RPT-06/RPT-04** — Z-report + profit/COGS; (5) **RSL-01** — commission/revenue-split ledger; plus **ZA-06/08** clearance-vs-reporting + stuck-doc alerts, **OPS-01/05** migrations + pagination, **AG-05/06** custom domain + branded email, and the **orphan ledger** verdicts.

## 10. Summary

- **Scope documented:** 2-products framing · market-expected behavior baseline (5 actor groups) · global model (actors, scope matrix, **15-entity state-machine catalog**, 10 invariants) · **19 feature families** (MA, AG, CL, POS, RST, PAY, INV, CRM, PRC, RPT, FIN, OMN, ZA, RSL, L10N, HW, SEC, OPS, UX/PRN) · **~35 page/dashboard design specs** · **9 printable specs** · 10 end-to-end journeys · 7-item orphan ledger.
- **Bar:** parity with Foodics/Rewaa/Marn — the gap between this model and the code IS the backlog.
- **Strongest today:** ZATCA crypto core, offline-first sale atomicity, tenancy/RBAC, i18n/RTL, base fiscal printables.
- **Biggest gaps (drive Prompt 2):**
  1. **Saudi payments + integrated terminal (PAY)** — today's tenders are labels, not captures. *Table-stake #1.*
  2. **Restaurant mode (RST)** — floor/tables, KDS/KOT, modifiers/combos, aggregators — entirely absent.
  3. **Partial/line refunds (POS-07/13)** — only whole-invoice today.
  4. **Z-report + profit/COGS/margin reporting (RPT-04/06)** — fiscal day-close and profitability absent.
  5. **Reseller depth (RSL/CL/AG)** — commission/revenue-split ledger, dunning/proration, custom domain, branded email, impersonation — Product-B table-stakes absent.
  6. **ZATCA reporting reality (ZA-06/08)** — real local crypto, but live Fatoora reporting only after onboarding; B2B-clearance vs B2C-reporting routing + stuck-doc alerting must be confirmed.
  7. **Operator hardening (OPS-01/05, SEC-05)** — Alembic migrations, server-side pagination everywhere, PDPL.
  8. **Orphan ledger** — AI Hub, object storage, Stripe Checkout, blog, OAuth: confirm dead vs intended.
- **Product decisions baked in (see `srs.md` v2.0):** unified retail+restaurant · Saudi-real payments (hard requirement) · per-page/printable design here · parity-with-KSA-leaders bar.




