# POS-SaaS — Master Revamp Plan

_Principal-architect synthesis of `scenarios.md`, `comment_in_scenarios.md`, `FRONTEND_DESIGN_REVIEW.md`, `FRONTEND_DEEP_REVIEW.md`, `BACKEND_FRONTEND_PARITY.md`, and `app.md`, cross-checked against the live codebase (38 routers · 58 models · 61 services · 79 migrations · ~99 frontend page files). Date: 2026-06-28 · Branch `main`._

> **How to read this document.** It is organized by the ten requested deliverables, but the operative artifact is **§9 (Roadmap)** and **§10 (Module Master Plan)**. Everything before that is the evidence base. Where the source documents conflict, the conflict is named and resolved rather than averaged.

---

## 0. The one reframe that governs everything

The source documents disagree on how "done" this system is, and the disagreement is the most important fact in this plan.

- `comment_in_scenarios.md` says the **specification** is **92–96% complete**.
- `BACKEND_FRONTEND_PARITY.md` says **378 of 433 backend routes** are consumed and "every frontend call targets a real backend endpoint."
- `FRONTEND_DESIGN_REVIEW.md` and `FRONTEND_DEEP_REVIEW.md` describe a frontend that is **token-correct but inconsistent, and in several places dishonest** (fabricated state, swallowed errors, ~283 strings English for non-English users).

These are not contradictory once you separate three axes:

| Axis | Maturity | Evidence |
|---|---|---|
| **Backend fiscal/transaction core** (sale_core, ZATCA, dunning, tenancy, RBAC, offline) | **~90%** — genuinely strong, enterprise-grade | `app.md` §3/§7/§8, parity audit headline |
| **Backend↔Frontend wiring** (does the UI reach what exists) | **~85%** — 15 real gaps, all "missing UI not wrong path" | parity audit §A–C |
| **Product completeness & trustworthiness** (lifecycle, reporting, admin, honesty, i18n, business-type adaptation) | **~60–70%** — the long tail that separates "demo" from "GA" | comment_in_scenarios §1–21, deep review C1/C2/H1–H6 |

**The synthesized verdict: the platform is ~70–75% of the way to a defensible first-customer GA, not 92–96%.** The 92–96% figure is accurate _about the spec's coverage of the core POS transaction_ and misleading _about the system as a sellable multi-tenant product_. The remaining 25–30% is unglamorous — lifecycle management, financial reporting, the business-type spine, and frontend integrity — but it is exactly the part an enterprise buyer evaluates.

The gaps sort into **four cost/risk classes**, and conflating them is the main planning error to avoid:

1. **Wiring gaps** — backend ready, UI missing. _Cheap, high value, low risk._ (MFA, forgot-password, sessions, SMS receipts, ZATCA integrity, zone edit, variant stock, notifications send.)
2. **Integrity/honesty defects** — UI exists but misrepresents state. _Cheap, high risk._ (Fabricated feature switches, fake session row, error→empty masquerade, contrast/height bugs, i18n backfill.)
3. **The business-type spine** — a backend field (`business_type ∈ retail/restaurant/both`) that no longer drives navigation, dashboard, onboarding, or guards. _Medium cost, cross-cutting, highest conceptual leverage._
4. **Genuinely missing capability** — backend **and** frontend absent. _Expensive, must be scoped hard._ (Subscription lifecycle, financial reports, stocktake, merchant/staff lifecycle, attendance, customer groups/store credit.)

Phase ordering in §9 follows directly: do class 2 and class 1 first (they are mostly free and de-risk trust), build the class-3 spine next (it reshapes everything after it), and stage class-4 by revenue impact.

---

## 1. Executive Assessment

### 1.1 Maturity by domain (honest percentages)

| Domain | Complete | One-line state |
|---|---:|---|
| Multi-tenant model & isolation | 95% | `owner_user_id` boundary is disciplined and correct (issue #193). |
| Auth & security (backend) | 90% | MFA, throttling, sessions, security-stamp all exist; **UI for MFA/sessions/forgot-password missing**. |
| POS sale core | 92% | Atomic, penny-exact, ZATCA-in-commit. Touch-target & height bugs on the actual terminal screen. |
| ZATCA e-invoicing | 90% | Real crypto, hash chain, routing. Integrity check has no UI. |
| Restaurant/KDS | 85% | Strong floor/ticket/KDS/BOM; missing merge/split/transfer-table, printer routing, table timers. |
| Billing rails | 80% | Two-rail model + dunning solid; **no self-serve lifecycle** (upgrade/downgrade/pause/cancel/invoice history). |
| Inventory | 80% | Adjustments/transfers/PO/moving-avg done; **no guided stocktake, no vendor returns, no PO approval chain**. |
| CRM | 70% | Customers/loyalty/gift cards/PDPL done; **no groups, tiers, store credit, campaigns**. |
| Reporting & analytics | 55% | Operational KPIs + Z-report exist; **financial reports (P&L, COGS, margin, tax summary) absent**. |
| Frontend consistency/honesty | 60% | Atoms excellent, molecules fracture; several surfaces show false state. |
| i18n completeness | 70% | en/ar strong; **~283 strings English for hi/ur and tt()-fallback pages**. |
| Admin / observability surfacing | 40% | Metrics/health/search/bulk endpoints exist **backend-only**, no UI. |
| Business-type adaptation | 25% | Field exists; experience does not adapt. |

### 1.2 Major strengths (protect these — do not "refactor" them)

- **A genuinely correct multi-tenant core.** Tenant isolation on `owner_user_id`, advisory `client_id`, suspend-cascade at the auth layer. This is the hardest thing to retrofit and it is already right.
- **An authoritative, atomic sale core** with penny-exact Decimal money, conditional-UPDATE stock, ZATCA signing inside the commit, and clean rollback on any failure.
- **Real ZATCA Phase-2 cryptography** (secp256k1/CSR/CSID, XAdES, TLV QR, PIH chain) — not stubs.
- **A coherent design-token system** (petrol-teal + gold, `dxr-*`, `pill-*`, `StatTile`, `components/states/*`) with strong RTL/logical-prop hygiene.
- **Fail-closed security defaults** everywhere (webhook signatures, ZATCA submission, subscription charge, forced reset).

### 1.3 Major weaknesses

1. **The experience does not know what kind of business it is** (the `business_type` spine). Confirmed: `business_type` is absent from `DashboardLayout` and `ClientDashboard`. A restaurant and a retail shop get the identical 27-icon rail and the identical retail dashboard.
2. **The frontend lies in several load-bearing places** — fabricated feature toggles (`AgentDashboard:514`), a hardcoded fake session row (`UserProfile:210`), and ~8 list pages that render a load failure as "you have none."
3. **Non-English users get a partly-English app** — 144 missing hi/ur keys + ~139 `tt(…,'English')` fallbacks that exist in no map ≈ **283 strings**.
4. **Missing business-lifecycle management** across subscription, merchant, product, and staff.
5. **No financial reporting** — the single most-requested category for a POS buyer (P&L, COGS, gross margin, tax summary, inventory valuation).
6. **Design-system under-adoption** — five table voices, optional shared states, currency that bypasses `formatMoney`.

### 1.4 Highest-risk areas (ranked)

1. **Trust/correctness on money-and-entitlement surfaces.** Fabricated feature switches let an admin make entitlement decisions against fiction; swallowed errors hide outages as quiet zero-days. **Risk: silent wrong business decisions.**
2. **KDS single-worker constraint** (`G6`). The real-time kitchen path asserts single-worker without Redis — a horizontal-scaling landmine for the busiest restaurant moment. **Risk: silent KDS blackout at scale.**
3. **Agent-Moyasar fail-closed coupling.** If an agent never connects Moyasar, _all_ their merchants' charges 402 and dunning stalls. Correct by design, but operationally fragile without proactive surfacing. **Risk: silent revenue stall across a whole agent's book.**
4. **POS terminal usability under load** — sub-44px controls + height-chain bug where the TOTAL can scroll off the customer display. **Risk: mis-tap and invisible-total errors at the counter.**
5. **i18n trust** in ar/hi/ur markets — a Saudi-first product that shows English in checkout to Arabic-fallback locales undermines the core positioning.

### 1.5 Missing production-critical features

Forgot-password UI · MFA UI · session management UI · subscription lifecycle (upgrade/downgrade/cancel/invoice history) · financial reports · guided stocktake · merchant/staff lifecycle (suspend/archive/restore) · backup/restore runbook surfacing · maintenance mode · feature-flag admin · observability dashboards (the `/production/metrics`, `/health/detailed`, `/search` endpoints exist but are unsurfaced).

### 1.6 Architectural / scalability / UX concerns (summary; detail in §5–§6)

- **Architecture:** KDS in-process broker blocks multi-worker; no event bus / job queue beyond the hourly billing scheduler; observability endpoints exist but aren't surfaced; no documented backup/restore/DR runbook.
- **Scalability:** SQL-aggregated dashboards are good; but no caching layer, no read-replica strategy, and the KDS/SSE broker caps the restaurant tier at one worker.
- **UX:** shell demotes page identity to a greeting; 27-icon rail doesn't scale; mobile drawer is an icon guessing game; POS touch targets too small; no business-type adaptation.

---

## 2. Gap Analysis (grouped by domain)

Legend: **[BE]** backend gap · **[FE]** frontend/UI gap · **[BE+FE]** both · **[WIRE]** backend exists, only UI missing.

### Authentication & Account
- [WIRE] MFA enroll/activate/status/challenge UI (`/auth/mfa/*`) — parity #1.
- [WIRE] Active-session list & revoke UI (`/auth/sessions*`) — parity #2.
- [WIRE] Self-service forgot/reset-password UI (`/auth/password/*`) — parity #3.
- [WIRE] Profile name/email/phone editing (`GET/PUT /users/profile`) — parity #4.
- [FE] De-fake `UserProfile` "Current Session" row — deep review M.

### POS / Sale
- [FE] 44px touch targets on cart controls (remove/qty/weight) — H5.
- [FE] Height-chain fix so TOTAL/checkout pin and inner scroll works (POSTerminal + CustomerDisplay) — H2 + M.
- [WIRE] SMS receipt action (`/pos/transactions/{id}/sms`) — parity #6; flag is **already sold**.
- [FE] White-label contrast guard on `bg-brand text-white` checkout chrome — H1/M.
- [FE] Held-tickets modal → real `Dialog` (focus trap, Esc, aria) — deep review M.

### Inventory
- [BE+FE] **Guided stocktake**: start → freeze → barcode count → variance → approve (resumable draft).
- [BE+FE] Vendor returns / supplier credit notes.
- [BE+FE] PO approval chain (draft→submitted→approved→ordered→received).
- [WIRE] Per-branch **variant** stock view/edit (`/pos/branches/{id}/variant-stock`) — parity #5.
- [BE+FE] Branch-level pricing/tax/promotions; central purchasing.
- [FE] Inventory valuation & dead-stock/slow-mover views (depends on reports).

### Restaurant
- [BE+FE] Merge / split / transfer table; transfer waiter.
- [BE+FE] Kitchen printer routing to multiple stations; multiple kitchens.
- [FE] KDS wall-display type scale + 3-tier lateness color (amber middle) — design review #9.
- [WIRE] Zone rename/delete (`PUT/DELETE /restaurant/zones/{id}`) — parity #7.
- [BE+FE] Table timers, happy-hour pricing, delivery-driver assignment, course scheduling.
- [ARCH] Redis-backed KDS broker to lift the single-worker constraint.

### CRM
- [BE+FE] Customer groups, membership tiers, store credit, birthday rewards, blacklist, notes, purchase timeline, campaigns.

### Product
- [BE+FE] Duplicate/archive/restore product; bundles; brand/manufacturer; batch/expiry/serial/IMEI tracking; digital products.

### Billing / Subscription
- [BE+FE] Upgrade/downgrade with proration; pause/resume/cancel; billing history; invoice download (PDF — note `/production/invoice/pdf` exists unused); refund a subscription payment; replace payment method; upcoming-renewal preview.
- [FE] Proactively surface the agent-Moyasar-not-connected fail-closed state platform-wide (it already has a banner on one screen).

### Reporting & Analytics
- [BE+FE] Financial: P&L, gross margin, COGS, cash flow, tax summary, inventory valuation.
- [BE+FE] Operational: hourly/daily sales, branch comparison, employee performance, best sellers/slow movers/dead stock.
- [BE+FE] Analytics: CLV, cohort, repeat-purchase rate, peak hours, forecasting.
- [FE] Migrate `ReportsAnalytics` off its private 449-line locale map — design review #8/LOW.

### Administration / Observability
- [WIRE] Surface `/production/metrics`, `/health/detailed`, `/search`, `/api-usage/stats` — parity #10.
- [WIRE] ZATCA integrity-check UI (`GET /zatca/integrity`) — parity #13.
- [WIRE] Notifications compose/send (`/production/notifications/send`) — parity #8.
- [BE+FE] Feature-flag admin, maintenance mode, backup/restore surfacing, queue/job monitoring, error/API log viewers, tenant migration.
- [FE/decide] File-manager UI for `/storage/*` (#9), generic bulk import/export (#12), permission-grant RBAC admin (#11) — confirm intentional-backend-only before building.

### i18n / Accessibility
- [FE] Backfill 144 hi/ur keys + promote ~139 `tt()` fallbacks (≈283 strings) — C1/C2.
- [FE] Keyboard-only nav audit, screen-reader pass, high-contrast mode, font scaling, color-blind-safe KDS states.

### Operational workflows
- [BE+FE] Reopen closed shift; end-of-day checklist; month-end / year-end close; inventory reconciliation; emergency cash removal; documented DR + offline-recovery validation.

### Business-type spine (cross-cutting — see §4)
- [BE+FE] Type-driven feature seeding, navigation, dashboard, onboarding, route guards, and a guarded type-change flow.

---

## 3. Unified Feature Matrix

State: **E**=Exists/solid · **P**=Partial · **M**=Missing · **R**=Needs redesign/rework.

| Module | Backend | Frontend | State | Note |
|---|---|---|---|---|
| Tenancy & isolation | E | E | **E** | Reference-quality. |
| Auth core (JWT/refresh/stamp/throttle) | E | E | **E** | — |
| MFA | E | M | **P** | Wire UI. |
| Sessions mgmt | E | M | **P** | Wire UI; de-fake row. |
| Forgot-password | E | M | **P** | Wire UI. |
| Profile editing | E | P | **P** | Wire `/users/profile`. |
| POS sale core | E | E | **E** | Fix touch/height/contrast. |
| Split/tip/service/hold/refund/void | E | E | **E** | — |
| Offline POS | E | E | **E** | Add recovery-validation flow. |
| Receipts (print/email) | E | E | **E** | Wire **SMS** (flag already sold). |
| Catalog & variants | E | P | **P** | Variant branch stock UI; archive/duplicate. |
| Categories tree | E | E | **E** | — |
| Branches & multi-loc stock | E | P | **P** | Variant stock; branch pricing/tax. |
| Stock adjust/transfer/PO | E | E | **E** | Add stocktake + returns + approval chain. |
| Guided stocktake | M | M | **M** | New build. |
| Customers/PDPL | E | E | **E** | — |
| Loyalty / gift cards / discounts / promos | E | E | **E** | — |
| Customer groups/tiers/store-credit | M | M | **M** | New build. |
| Quotations / expenses | E | E | **E** | — |
| Restaurant floor/ticket/KDS/BOM | E | E | **E** | KDS scale; single-worker; zone edit. |
| Merge/split/transfer table | M | M | **M** | New build. |
| Omnichannel (Salla/aggregators) | E | E | **E** | — |
| ZATCA onboarding/sign/report | E | E | **E** | Surface integrity check. |
| Billing rails + dunning | E | P | **P** | Lifecycle mgmt missing. |
| Subscription lifecycle (up/down/cancel/history) | M/P | M | **M** | Highest billing gap. |
| Operational reports (Z/KPI) | E | E | **E** | — |
| Financial reports (P&L/COGS/margin/tax) | M | M | **M** | Highest reporting gap. |
| Webhooks / audit / API metering | E | E | **E** | — |
| Observability (metrics/health/search) | E | M | **P** | Surface UI. |
| Notifications | E | P | **P** | Add compose/send; channel prefs. |
| Admin (flags/maintenance/backup/jobs) | P | M | **M** | New build + surface. |
| i18n (en/ar) | E | E | **E** | — |
| i18n (hi/ur) | — | P | **P** | 283-string backfill. |
| Accessibility | — | P | **R** | Audit + a11y modes. |
| Shell / IA / navigation | — | P | **R** | Sectioned, type-aware, page-titled. |
| Design-system adoption | — | P | **R** | One table voice; shared states; formatMoney. |
| Business-type adaptation | P | M | **M** | The spine (§4). |

---

## 4. Workflow Review

Per-workflow verdict on `scenarios.md`. ✅ complete · 🟡 needs improvement · ❌ missing edge/UI/logic.

| § | Workflow | Verdict | Gaps to close |
|---|---|---|---|
| A1–A2 | Master login / economics | ✅ | MasterDashboard error-isolation (KPIs render `0` on failure); export CSV confirm present. |
| A3 | Create package | ✅ | Add archive-with-existing-agents messaging. |
| A4 | Provision/suspend agent | ✅ | Add suspend-cascade confirmation preview ("N merchants, M staff will be blocked"). |
| A5 | Global tax rate | ✅ | — |
| B1–B2 | Agent reset / connect Moyasar | 🟡 | Surface the fail-closed 402 state in **every** merchant billing view, not one banner. |
| B3 | Branding | 🟡 | Bundle the offered fonts (preview lies); contrast guard at color-pick; localize toasts; `secondary_color` unused. |
| B4 | Provision merchant | 🟡 | **No business-type-driven provisioning** (see §4.1). Quota-full path good. |
| B5 | Feature overrides | ❌ | `AgentDashboard:514` switches are **fabricated** — hydrate from real flags, key by client id. |
| B6–B7 | Buy slots / statements | ✅ | Statement PDF export. |
| C1–C2 | Self-serve signup / tour | 🟡 | Tour is not business-type-aware; onboarding steps hardcoded retail. |
| D1–D8 | Retail catalog/inventory | 🟡 | Variant branch stock UI; **guided stocktake** missing; PO approval chain; product archive/duplicate. Error→empty masquerade on Product/Category/Branch lists. |
| E1–E8 | CRM/loyalty/promo | 🟡 | Groups/tiers/store-credit/campaigns missing; Customer list swallows load errors; filter-chip contrast. |
| F0–F12 | Retail POS | 🟡 | Touch targets (H5), height chain (H2/M), contrast (H1), held-tickets dialog, SMS receipt; **reopen shift missing**. Core logic complete. |
| G1–G6 | Restaurant | 🟡 | Merge/split/transfer table, printer routing, table timers, KDS scale/lateness; **single-worker KDS** ops risk; zone edit/delete. |
| H1–H2 | Omnichannel | ✅ | Surface stuck-claim sweep status in UI. |
| I1–I5 | ZATCA | 🟡 | **Integrity-check UI missing** (backend ready); wizard partly English in hi/ur. |
| J1–J7 | Staff/security | 🟡 | **MFA UI, sessions UI, forgot-password UI all missing** though backend ready; staff **suspend/terminate/attendance/PIN** missing. |
| K1–K2 | Customer-facing | 🟡 | CustomerDisplay leaks platform name + height bug hides TOTAL. |
| L1–L5 | Ops/admin | 🟡 | Notifications send; observability surfacing; audit/webhooks solid. |
| M1–M4 | Billing | ❌ | **Lifecycle missing** (upgrade/downgrade/pause/cancel/history/invoice/replace-card/renewal-preview). Dunning/webhook solid. |
| N1–N4 | FE prefs | ✅ | — |
| O1–O6 | Composites | ✅ | All compose cleanly; O5 carries the single-worker caveat. |

### 4.1 The missing commercial workflows (must add)

These are expected in a commercial POS and absent or incomplete in `scenarios.md`:

1. **Business-type selection → dynamic experience** (the spine — detail below).
2. **Subscription lifecycle** (upgrade/downgrade/proration, pause/resume, cancel, billing & invoice history, replace card, renewal preview).
3. **Merchant lifecycle** (archive/restore, transfer to another agent, change owner, export, post-retention delete).
4. **Employee lifecycle** (suspend/terminate, attendance clock in/out, shift assignment, PIN login, payroll/leave export).
5. **Guided stocktake** (start/freeze/count/variance/approve, resumable).
6. **Month-end / year-end / reopen-shift / end-of-day checklist.**
7. **Disaster recovery & offline-recovery validation** (runbook + a "verify queue drained" UI affordance).
8. **Data import/export & audit/compliance exports** (regulatory audit export, consent history, retention policy).

### 4.2 The business-type spine (the single highest-leverage workflow)

Backend has `business_type ∈ {retail, restaurant, both}`; the experience ignores it. The complete workflow:

```
Provision merchant ─▶ choose type ─▶ server seeds type-appropriate features/menus/permissions
        └▶ Navigation, Dashboard, Onboarding, Reports, Route-guards all derive from type
Change type (Settings) ─▶ warning dialog ─▶ recompute nav/perms/dashboard/onboarding (no data deletion)
```

- **Retail** auto-enables Products/Categories/Inventory/Suppliers/PO/Customers/POS/Stock-reports; hides Floor/Tables/KDS/Recipes/Menu-builder/Reservations.
- **Restaurant** auto-enables Menu-builder/Floor/Tables/KDS/Recipes/Reservations/Waitlist/Courses/Table-POS; hides retail inventory dashboards/shortcuts.
- **Hybrid** shows both with a sale-mode switch (Retail / Table / Takeaway / Delivery).
- **Route guards** derive from type **before** per-merchant feature overrides.
- **Dashboards** reframe: Retail (Sales/Low-stock/Inventory-value/Best-sellers) vs Restaurant (Active-tables/Kitchen-queue/Reservations/Avg-ticket-time) vs Hybrid (both).

This one workflow touches navigation, onboarding, permissions, dashboards, and reports — which is why it is sequenced before the rest of the class-4 build.

---

## 5. Frontend Revamp Plan

Driven by both frontend reviews. Most of this is **migration and honesty, not redesign** — the token system is good.

### 5.1 Navigation & information architecture
- Replace the **27-item flat icon rail** with **sectioned groups** (Sell / Catalog / People / Setup) and **labels in the mobile drawer** (H6).
- Make the rail **business-type-aware** (§4.2) — hide irrelevant modules per type.
- **Promote page identity to H1**; demote the "Good morning, Zeyad" greeting to the dashboard home only.
- De-duplicate reused icons (`Receipt` for expenses+template, `Package` for packages+catalog).

### 5.2 Dashboard redesign
- **ClientDashboard fetches the profile and adapts to `business_type`** (currently does neither) — restaurant gets covers/tables/kitchen language.
- **Error honesty**: replace the all-zero fake dashboard on load failure (H4) with `ErrorState` + retry.
- Master/Agent dashboards: isolate KPI errors so a leaderboard failure doesn't render headline MRR as `0`.

### 5.3 Component standardization (finish the migrations already promised)
- **One table voice**: migrate Customer/Staff/Discount/Reports/dashboard-transactions onto `<DataTable>`/`.dxr-tbl`.
- **Adopt `components/states/*` everywhere** — kill bespoke `animate-pulse` blocks in Index/Notifications/MasterDashboard/AgentDashboard/POSTerminal/ClientDashboard.
- **Currency through `formatMoney*`** — eliminate `CountUp prefix="⃁ "`, raw deltas, select-option prices; dates through `formatDate`/`formatDateTime`.
- Migrate `ReportsAnalytics`'s 449-line private locale map into `lib/i18n.ts`.

### 5.4 Mobile / touch responsiveness
- POS cart controls → `h-11 w-11`, `inputMode="decimal"`, lucide icons + `aria-label` (H5).
- Height chain: `min-h-screen` → `h-screen`/`h-full` on CustomerDisplay + POSTerminal so totals pin and inner columns scroll (H2/M).
- Touch variants for `dxr-seg` tabs and tender buttons (currently ~28–36px).

### 5.5 Accessibility
- Backfill i18n (C1/C2, 283 strings) — the largest single user-visible defect.
- `rtl:rotate-180` on unmirrored chevrons/arrows; utilities-layer Arabic letter-spacing reset (LOW).
- Native `<input type=radio/checkbox>` → shadcn; held-tickets raw `div` → `Dialog`.
- KDS: 3-tier lateness with `AlertTriangle` + text (not color-only); wall-display type scale.
- Add high-contrast mode, font scaling, keyboard-nav audit, SR pass.

### 5.6 White-label correctness
- **Contrast guard**: anywhere `text-white` sits on `bg-brand`/tenant color (POSTerminal, Customer chips, AgentLandingPage CTAs, BrandingEditor preview) → `text-primary-foreground`, auto-flip + warn on pale brands (H1/M).
- **AgentLandingPage**: stop routing transient API errors to `NotFoundState "Distributor Not Found"` (a network blip tells a prospect the agent doesn't exist).
- **BrandingEditor**: bundle the offered fonts (or stop offering them); validate/normalize hex; mirror `readableForeground()` in the preview.

### 5.7 Truthful affordances (do not ship UI that lies)
- `AgentDashboard` feature switches → hydrate from real flags, key by client id (H3).
- `UserProfile` session row → wire to real `/auth/sessions` or relabel (M).
- `PackageManagement` `deactivate` button that calls `handleDelete` → fix to actually deactivate.
- `StoreSettings` save toast → result string + `catch` with error toast.

---

## 6. Backend Revamp Plan

The backend is the strong half; this is mostly **additive services + operational hardening**, not rework.

### 6.1 Missing services / APIs
- **Financial reporting service** (P&L, COGS roll-up from BOM, gross margin, tax summary, inventory valuation, cash flow) — SQL-aggregated, tenant-scoped, never load-all.
- **Subscription lifecycle service** (proration math on upgrade/downgrade, pause/resume/cancel state transitions, invoice PDF via existing `/production/invoice/pdf`, renewal preview).
- **Stocktake service** (sessioned count with stock freeze, variance computation, approval that posts adjustments atomically).
- **Lifecycle services** for merchant (archive/restore/transfer/export) and staff (suspend/terminate/attendance/PIN).
- **CRM extensions** (groups, tiers, store-credit ledger reusing the gift-card ledger pattern).
- **Restaurant**: merge/split/transfer-table transactional ops; multi-station printer routing.

### 6.2 Scalability & event architecture
- **Lift the KDS single-worker constraint**: make `kds_channel` pluggable with a **Redis pub/sub** backend so the restaurant tier scales horizontally (today boot asserts single-worker).
- **Introduce a job queue** (the hourly `billing_scheduler` is the only background worker today) for: webhook delivery retries, ZATCA reconcile, report materialization, notifications, exports. A real queue (RQ/Celery/Arq + Redis) replaces ad-hoc sweeps.
- **Event bus**: formalize the existing outbound webhook events (`product.created`, `shift.closed`, …) into an internal event stream other services subscribe to.

### 6.3 Performance & caching
- Add a **caching layer** (Redis) for brand resolution, feature entitlements, tax-rate resolution, and hot dashboard aggregates (with tenant-scoped invalidation on write).
- Define a **read-replica** posture for reporting queries so analytics never contends with the sale path.
- Audit hot-path indexes for the new financial-report queries before they ship.

### 6.4 Security, monitoring, logging, backup
- **Surface** the existing `/production/metrics`, `/health/detailed`, `/api-usage/stats`, Sentry, correlation IDs, structured JSON logging into an ops dashboard.
- **Backup/restore**: document and automate Postgres PITR; verify restore quarterly; surface a "last backup" health indicator.
- **Secret management** review for `MOYASAR_API_KEY`, agent `moyasar_secret_key_enc`, ZATCA private keys (already AES-256-GCM at rest — confirm rotation story).
- **DR runbook**: RPO/RTO targets, region-failover plan, offline-queue drain validation.

---

## 7. Backend–Frontend Parity Plan

Every confirmed parity mismatch, with desired state and priority. (All 15 are **missing UI**, not wrong-path bugs.)

| # | Mismatch | Current | Desired | Implementation | Priority |
|---|---|---|---|---|---|
| 6 | SMS receipt | flag sold, action missing | parity with email receipt | add `smsReceipt()` call + button next to Email | **Critical** (sold feature) |
| 3 | Forgot-password | only forced reset | self-serve flow | 2-screen flow on `/auth/password/*`, no-enumeration copy | **Critical** |
| 1 | MFA | no UI | enroll + challenge | wire `input-otp.tsx` (exists, unimported) to `/auth/mfa/*` + `/login/mfa` | **High** |
| 2 | Sessions | fake row | real list + revoke | `UserProfile` → `/auth/sessions*` | **High** |
| 4 | Profile edit | not wired | name/email/phone | `UserProfile` → `GET/PUT /users/profile` | **High** |
| 13 | ZATCA integrity | backend-only | audit UI | button + result view on `GET /zatca/integrity` | **High** |
| 5 | Variant branch stock | parent only | variant editable | extend branch-stock screen to `/variant-stock` | Medium |
| 7 | Zone edit/delete | create/list only | full CRUD | wire `PUT/DELETE /restaurant/zones/{id}` in `FloorMap` | Medium |
| 8 | Notifications send | list/read only | compose/send | add composer on `/production/notifications/send` | Medium |
| 10 | Observability | backend-only | ops dashboard | surface metrics/health/search/api-usage | Medium |
| 9 | `/storage/*` | unused | file manager? | **decide** intentional-backend-only first | Low |
| 11 | RBAC grant/revoke | partial overlap | admin UI? | **decide** vs existing staff-permissions | Low |
| 12 | generic bulk/PDF | unused | reuse for invoices/exports | adopt `/production/invoice/pdf` for billing-history | Low |
| 14 | `/payments/tender-types`,`charge` | static list | server-driven tenders? | **decide** — current static list works | Low |
| 15 | `/printers/resolve` | internal | n/a | leave backend-only | — |

---

## 8. Production Readiness Checklist

- [ ] **Security**: MFA UI shipped · forgot-password UI · session management · secret rotation documented · pen-test of tenant isolation on `owner_user_id` · ZATCA key handling reviewed.
- [ ] **Performance**: dashboard aggregates cached · reporting on read path isolated · POS p95 latency budget defined & measured · load test at target merchant concurrency.
- [ ] **Monitoring**: `/production/metrics` + `/health/detailed` surfaced · Sentry verified firing · alerting on dunning-stall, KDS-broker-down, ZATCA-submit-failure, agent-Moyasar-disconnected.
- [ ] **CI/CD**: migration safety gate (no destructive auto-migrations) · staged rollout · automated rollback path.
- [ ] **Testing**: sale-core property tests (tenders-sum-exact, stock-conditional-update) · ZATCA chain-integrity test · i18n-key-parity test (block builds when a locale is short of `en`) · the deep-review's **7-sweep frontend regression** as a checklist.
- [ ] **Documentation**: ops runbooks · API docs · onboarding guides per tier · the business-type behavior matrix.
- [ ] **Observability**: correlation IDs end-to-end · structured logs shipped to a store · slow-query log reviewed.
- [ ] **Disaster recovery**: Postgres PITR automated · **restore drill passed** · RPO/RTO documented · offline-queue-drain validation UI.
- [ ] **Compliance**: PDPL export/erase verified · ZATCA 6-year retention verified · consent history · data-retention policy · regulatory audit export.
- [ ] **Deployment**: KDS single-worker constraint resolved (Redis) **or** restaurant tenants pinned to single-worker deploys with a health warning.
- [ ] **Operations**: maintenance mode · feature-flag admin · backup health indicator · agent-Moyasar-connected pre-flight before first merchant charge.
- [ ] **Maintainability**: one table voice · shared states adopted · single i18n source · no fabricated-state UI remaining.

---

## 9. Prioritized Roadmap

Each task: **Priority** (Critical/High/Medium/Low) · **Complexity** (S/M/L) · **Dependencies** · **Impact**.

### Phase 1 — Critical Foundation (before beta)

_Theme: stop lying, finish wiring, build the spine. Mostly cheap, mostly high-trust._

| Task | Pri | Cx | Deps | Impact |
|---|---|---|---|---|
| i18n backfill (283 strings; add build-time key-parity gate) | Critical | M | — | Non-English markets become usable; Saudi-first credibility |
| Fix fabricated/false-state UI (agent switches H3, session row, deactivate-deletes, swallowed errors ×8, StoreSettings toast) | Critical | M | — | Removes wrong-decision risk; trust |
| Wire SMS receipt (#6) | Critical | S | — | Sold feature becomes real |
| Forgot-password UI (#3) | Critical | S | — | Table-stakes SaaS security |
| POS height-chain + 44px touch + contrast guard (H1/H2/H5) | Critical | M | — | The actual counter screen works |
| **Business-type spine** (seed → guards → nav → dashboard → onboarding → change-flow) | Critical | L | profile fetch on ClientDashboard | Reshapes the whole product; unblocks restaurant GA |
| MFA UI + session management (#1/#2) | High | M | — | Security expectations |
| Profile editing (#4) | High | S | — | Completes account surface |
| ClientDashboard business-type adaptation + error honesty (H4) | High | M | spine | First-impression surface tells the truth |

### Phase 2 — Production Readiness (before first customer)

_Theme: the buyer-evaluated long tail — reporting, billing lifecycle, ops._

| Task | Pri | Cx | Deps | Impact |
|---|---|---|---|---|
| Financial reports (P&L, COGS, margin, tax summary, inventory valuation) | Critical | L | reporting service, read-replica posture | #1 buyer-requested category |
| Subscription lifecycle (upgrade/downgrade/proration, pause/cancel, billing & invoice history, replace card, renewal preview) | Critical | L | invoice PDF endpoint | Revenue ops + churn handling |
| Guided stocktake (start/freeze/count/variance/approve) | High | L | — | Core retail operation |
| One table voice + shared-states adoption + formatMoney/date migration | High | M | — | Maintainability & polish |
| Surface observability + ZATCA integrity UI (#10/#13) | High | M | — | Operability + fiscal assurance |
| Reopen shift / month-end / end-of-day checklist | High | M | — | Daily operational reality |
| Backup/restore automation + DR runbook + restore drill | High | M | — | Cannot sell without this |
| KDS Redis broker (lift single-worker) | High | M | Redis | Restaurant scale-out |
| Shell IA: sectioned + type-aware nav, page-title H1, mobile labels (H6) | High | M | spine | Scales past 27 icons |
| Notifications compose/send + channel prefs (#8) | Medium | S | — | Completes ops surface |
| Merchant lifecycle (archive/restore/transfer/export) | Medium | M | — | Agent book management |
| Staff lifecycle (suspend/terminate/attendance/PIN) | Medium | M | — | Real workforce mgmt |
| Variant branch stock (#5), zone edit (#7) | Medium | S | — | Finish existing screens |

### Phase 3 — Enterprise Features (scaling)

| Task | Pri | Cx | Deps | Impact |
|---|---|---|---|---|
| Job queue + event bus (webhook retry, reconcile, report materialization) | High | L | Redis | Scalability & reliability |
| Caching layer (brand/features/tax/aggregates) | High | M | Redis | Performance |
| Multi-branch: branch pricing/tax/promotions, cross-branch reporting, central purchasing | Medium | L | reports | Multi-location chains |
| CRM: groups, tiers, store credit, campaigns, blacklist | Medium | L | — | Retention/marketing |
| Restaurant: merge/split/transfer table, printer routing, multi-kitchen, timers, happy-hour | Medium | L | — | Full-service restaurants |
| Product: archive/duplicate/bundles/batch/expiry/serial | Medium | M | — | Pharmacy/electronics verticals |
| Vendor returns + PO approval chain | Medium | M | — | Procurement governance |
| Admin: feature-flag console, maintenance mode, job/queue monitors, log viewers | Medium | M | observability | Operability |
| Accessibility program (a11y modes, SR/keyboard audit) | Medium | M | — | Compliance & inclusion |
| Compliance: consent history, retention policy, regulatory audit export | Medium | M | — | Enterprise procurement |

### Phase 4 — Nice-to-Have

| Task | Pri | Cx | Impact |
|---|---|---|---|
| AI: sales/inventory forecasting, smart reorder, dynamic pricing, assistant | Low | L | Differentiation |
| Advanced analytics: CLV, cohort, repeat-rate, funnels, peak hours, heatmaps | Low | L | Insight |
| Integrations: accounting/ERP, label printers, scales, more SMS/email providers | Low | M | Ecosystem |
| Productivity: global search UI, saved filters/reports, favorites, bulk ops, undo | Low | M | Power-user UX |
| Native mobile/tablet POS + warehouse scanner apps | Low | L | Mobility |

---

## 10. Final Master Plan (organized by module)

The single roadmap, merged across all source documents and organized by module rather than by review. Each module lists what to **fix**, **wire**, and **build**, in phase order.

### M1 · Identity, Auth & Account Security
- **Fix:** de-fake `UserProfile` session row.
- **Wire (P1):** forgot-password, MFA, sessions, profile editing.
- **Build (P3):** SR/keyboard a11y for auth; secret-rotation runbook.

### M2 · Tenancy, Branding & Onboarding
- **Fix (P1):** BrandingEditor font bundling, hex validation, contrast guard, localized toasts; AgentLandingPage transient-error → not "Distributor Not Found"; use `secondary_color`.
- **Build (P1):** **business-type spine** — type-driven seeding, guards, nav, dashboard, onboarding, and a guarded change-type flow (the keystone task).

### M3 · POS & Checkout
- **Fix (P1):** height chain, 44px touch targets, contrast, held-tickets `Dialog`, emoji→lucide, `window.alert`→toast.
- **Wire (P1):** SMS receipt.
- **Build (P2):** reopen shift, end-of-day checklist; offline-recovery validation affordance.

### M4 · Catalog & Inventory
- **Fix (P1):** error→empty masquerade on Product/Category/Branch lists.
- **Wire (P2):** variant branch stock.
- **Build:** guided stocktake (P2); vendor returns + PO approval chain (P3); product archive/duplicate/bundles/batch/expiry/serial (P3); branch pricing/tax + central purchasing (P3).

### M5 · CRM, Loyalty & Promotions
- **Fix (P1):** Customer list error honesty; filter-chip contrast; `lg:grid-cols-4` dangling column.
- **Build (P3):** customer groups, membership tiers, store credit, campaigns, blacklist, notes, purchase timeline, birthday rewards.

### M6 · Restaurant & KDS
- **Fix (P2):** KDS wall-display type scale + 3-tier lateness; status-as-pill tokens; native inputs→shadcn.
- **Wire (P2):** zone edit/delete.
- **Build:** Redis KDS broker (P2, lifts single-worker); merge/split/transfer table, printer routing, multi-kitchen, table timers, happy-hour, driver assignment (P3).

### M7 · ZATCA & Fiscal Compliance
- **Wire (P2):** integrity-check UI.
- **Build (P3):** regulatory audit export; verify 6-year retention; surface reconcile status.

### M8 · Billing & Subscription
- **Fix (P1):** surface agent-Moyasar-not-connected fail-closed state platform-wide.
- **Build (P2):** full subscription lifecycle — upgrade/downgrade + proration, pause/resume, cancel, billing & invoice history (PDF), replace card, renewal preview; merchant lifecycle (archive/restore/transfer/export).

### M9 · Reporting & Analytics
- **Fix (P2):** migrate `ReportsAnalytics` private locale map into i18n; one table voice.
- **Build (P2):** financial reports (P&L/COGS/margin/tax/inventory-valuation/cash-flow) + operational (hourly/daily/branch/employee/best-sellers/dead-stock).
- **Build (P4):** CLV/cohort/forecast/heatmaps.

### M10 · Platform Ops, Admin & Observability
- **Wire (P2):** observability dashboards (metrics/health/search/api-usage); notifications compose/send.
- **Build (P2):** backup/restore automation + DR runbook + restore drill.
- **Build (P3):** feature-flag console, maintenance mode, job/queue monitors, log viewers, tenant migration; job queue + event bus + caching layer.

### M11 · Design System & Frontend Platform (cross-cutting, runs through P1–P2)
- **i18n backfill** (283 strings) + build-time key-parity gate.
- **One table voice** (`DataTable`/`dxr-tbl`); **adopt `components/states/*` everywhere**; **currency/date through `formatMoney`/`formatDate`**.
- **Shell IA**: sectioned + type-aware nav, page-title H1, mobile labels.
- **White-label contrast guard**; **RTL icon mirroring** + Arabic letter-spacing reset.
- **Accessibility program**: high-contrast, font-scaling, color-blind-safe states, SR/keyboard audit.
- **Institutionalize the deep-review 7-sweep** as a pre-merge frontend regression checklist.

---

### Sequencing rationale (the through-line)

1. **Phase 1 buys trust cheaply.** Honesty fixes, i18n, and wiring gaps are mostly small/medium and remove the risks an evaluator notices first. The business-type spine is the one large P1 item because everything downstream (nav, dashboards, onboarding, reports) is shaped by it — building it late means rebuilding those surfaces.
2. **Phase 2 is what a buyer signs against** — financial reports, subscription lifecycle, backups, and operability. None are core-POS, all are GA blockers.
3. **Phase 3 unlocks scale and verticals** — queue/cache/event-bus for technical scale; CRM/restaurant/multi-branch depth for market reach.
4. **Phase 4 differentiates** once the foundation is trustworthy.

> **The discipline this plan enforces:** never ship UI that misrepresents state, never let a locale fall short of `en` without failing the build, and never add a class-4 capability before the class-2 honesty fix for the same surface. The backend earned its strength by being authoritative and fail-closed; the frontend reaches the same bar by being *truthful and adaptive*.
