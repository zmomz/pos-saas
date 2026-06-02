# Gap Analysis — Multi-Tenant POS vs. SRS v1.0

**Date:** 2026-06-02
**Scope:** `backend/` (FastAPI) + `frontend/` (React/TS) compared against `srs.md` (functional SRS §3 + production-readiness checklist + the "receipts/quotations always Arabic" rule).

> **▶ Phase A completed 2026-06-02** — see [§9 Phase A implementation log](#9-phase-a-implementation-log) for the full change list, file references, and the `backend/tests/` suite. Status cells touched by Phase A are marked **✅ (Phase A)** below.
>
> **▶ Phase B completed 2026-06-02** — ZATCA Phase-2 cryptography is now **real**: per-client EC secp256k1 keypair + PKCS#10 EGS CSR, a verifiable ECDSA-SHA256 cryptographic stamp (the HMAC placeholder is gone), AES-256-GCM secrets at rest, a per-client PIH hash chain, 6-year invoice retention, a sandbox/simulation/production toggle, and a Fatoora onboarding/reporting API client that fails closed (503) until a gateway is configured. See [§10 Phase B implementation log](#10-phase-b-implementation-log). The suite is now **27 tests, all passing**. Cells touched by Phase B are marked **✅ (Phase B)** / **🟡 (Phase B)** below.
>
> **▶ Phase C completed 2026-06-02** — the required product features are wired and enforced: master **agent provisioning** (creates a real login + temp password), **slot refill**, a master-set **global VAT rate** that agents/clients inherit and the POS applies authoritatively, **split/mixed payment breakdown**, an **always-Arabic invoice document** endpoint + **email receipts**, **automated low-stock alerts** on each sale, **per-client feature enforcement** with an agent runtime toggle, and an **audit-log middleware** that records every authenticated mutation. See [§11 Phase C implementation log](#11-phase-c-implementation-log). The suite is now **42 tests, all passing**. Cells touched by Phase C are marked **✅ (Phase C)** / **🟡 (Phase C)** below.
>
> **▶ Phase D completed 2026-06-02** — the Arabic-output rule and its polish are done: the **on-screen POS receipt is now forced Arabic** (RTL, Arabic-Indic numerals, SAR) regardless of UI language; a **quotation feature** (عرض سعر) exists end-to-end — a new entity triad plus an **always-Arabic, non-fiscal quotation document** endpoint and a frontend page; a central **Arabic-Indic digit formatter** (backend `core/formatting.py` + frontend `lib/format.ts`) renders amounts/dates natively in the always-Arabic documents; and the **agent default language** propagates to clients (set in the branding editor, inherited on client creation, applied on first client login). See [§12 Phase D implementation log](#12-phase-d-implementation-log). The suite is now **51 tests, all passing**. Cells touched by Phase D are marked **✅ (Phase D)** below.
>
> **▶ Phase E completed 2026-06-02** — mobile/offline & nice-to-haves. **Loyalty is now real and wired into the *atomic* sale**: points accrue on every customer sale and `redeem_points` redeems against the balance as an order discount, both committed in the same transaction as the sale + inventory (a rolled-back sale never moves the ledger). **Thermal/ESC-POS printing** exists — a backend byte builder (`services/escpos.py`) + `GET /pos/transactions/{id}/escpos` and a frontend WebUSB helper, with the canonical ZATCA QR embedded. **Offline POS** is in place — an IndexedDB queue + app-shell service worker on the frontend that buffers sales offline and replays them to the (idempotent) `/production/offline/sync` endpoint on reconnect. **Error tracking (Sentry)** is wired as a config-gated no-op (`core/observability.py`). See [§13 Phase E implementation log](#13-phase-e-implementation-log). The suite is now **63 tests, all passing**. Cells touched by Phase E are marked **✅ (Phase E)** / **🟡 (Phase E)** below. *The only genuinely out-of-scope item is the **native white-label RN/Flutter mobile app**, which is a separate codebase, not this FastAPI+React repo — see §13.*

## Legend
- ✅ **Implemented** — real working logic.
- 🟡 **Partial** — works but incomplete or not enforced.
- 🟠 **Stub / CRUD-only** — model/endpoint exists, but no real business logic; or logic exists but is **orphaned** (not wired into the request flow).
- 🔴 **Missing** — not present.

---

## 0. Executive summary

The codebase is a **broad but shallow** implementation: nearly every entity from the SRS has a model + CRUD router, and there is a surprising amount of "production" service code (`backend/services/production.py`, `backend/middlewares/production.py`, `backend/services/payment.py`). **The dominant problem is orphaned/un-wired logic** — substantial features are written but never connected to the request flow:

- **Stripe billing** (`services/payment.py`, ~420 lines) is fully written but **imported by no router**.
- **Webhook dispatch, low-stock email alerts, email sending** exist as methods in `services/production.py` but are **never called**.
- **Agent branding** is stored and fetched but **never applied** to the UI (no CSS variables) → white-labeling effectively doesn't work.
- **Permissions** table + grant/revoke exist but are **never checked** on any mutation.

Second theme: **the safety-critical paths are not safe** — POS sale and inventory deduction are two separate non-atomic HTTP calls (the frontend even fires inventory deduction without awaiting it), and ZATCA's cryptographic stamp is a placeholder HMAC.

**Overall readiness:** demo/MVP quality. Not production-ready, and **not ZATCA Phase-2 compliant** (a legal blocker in KSA).

---

## 1. Master / Agent management (SRS §3.1–3.2)

| ID | Requirement | Status | Evidence / Gap |
|----|-------------|--------|----------------|
| MA-01 | Master creates agent (company, email, phone, package) | ✅ **(Phase C)** | `POST /api/v1/tenant/master/agents` (`routers/tenant.py`) provisions a **real login account** (email + generated `temp_password`) **and** the linked `Agents` row, so the new agent can sign in immediately and resolves as an agent. Accepts `package_id` (→ `client_slots`) or explicit `slots`; rejects duplicate email (409). Tested in `tests/test_phase_c_master.py`. |
| MA-02 | Deduct one slot on client creation | ✅ Implemented | `routers/tenant.py` checks `used_slots` vs `package_type`, increments on create. |
| MA-03 | Master sees used vs remaining slots | ✅ Implemented | `tenant.py` `AgentStatsResponse` + `remaining_slots` calc. |
| MA-04 | Master refills/adds slots | ✅ **(Phase C)** | `POST /api/v1/tenant/master/agents/{id}/slots` adds N client slots to `package_type` (master-only, positive-int validated). Tested in `tests/test_phase_c_master.py`. |
| MA-05 | Master sets global tax rate; agents inherit, can't override | ✅ **(Phase C)** | New `system_settings` store + `services/system_settings.py`: `PUT /api/v1/tenant/master/tax-rate` (master) sets the global VAT; `GET /api/v1/tenant/tax-rate` returns the inherited rate. `routers/pos.py` resolves the **effective** rate via `get_effective_tax_rate` — the global rate **overrides** any per-request `vat_rate`, so agents/clients cannot override it. Tested (5% global applied to a sale) in `tests/test_phase_c_master.py`. |
| AG-01 | Agent uploads logo to cloud bucket | 🟡 Partial | `routers/storage.py` issues presigned upload URLs but requires external `OSS_SERVICE_URL`/`OSS_API_KEY` (an atoms-style OSS); not a self-hosted/S3 setup. `agents.logo_url` stores the result. |
| AG-02 | Agent sets primary/secondary color, radius, font | ✅ Implemented | Fields on `models/agents.py`; editor `BrandingEditor.tsx`; persisted via `PUT /api/v1/branding/update` (`routers/features.py:445`). |
| AG-03 | Agent toggles features per client | ✅ **(Phase C)** | `POST /api/v1/tenant/agent/clients/{client_id}/features` upserts a `client_features` flag at runtime (agent-scoped to their own clients). Enforced by `dependencies/features.require_feature` (default-on; a flag set to `False` 403s the gated route) — demonstrated on the POS email-receipt endpoint. Tested in `tests/test_phase_c_features.py`. |
| AG-04 | Client login dynamically loads agent theme | ✅ **(Phase A)** | New `frontend/src/contexts/BrandingContext.tsx` fetches agent/client branding on login and applies it at runtime: hex→HSL conversion sets `--primary`/`--ring`/`--accent`/`--radius` CSS variables, `font-family`, and exposes `logoUrl`. Cleared on logout. Wired in `App.tsx` (`<BrandingProvider>`). White-labeling now renders. |
| — | Revenue split / commission due to master | 🔴 Missing | `packages` has wholesale/retail price fields only; `MasterDashboard.tsx` shows a hardcoded `used_slots * 50` mock. No billing/commission tables or calc. |
| — | Row-level security (client own data; agent own clients) | ✅ Implemented | `user_id`/`agent_id` scoping in services + `tenant.py`. (Note: enforced in service layer, not via `X-Tenant-ID` header as SRS §5.5 suggests — header is unused.) |

---

## 2. Client onboarding & subscription (SRS §3.3) — billing

| ID | Requirement | Status | Evidence / Gap |
|----|-------------|--------|----------------|
| CL-01 | Create client → email login link + temp password | 🔴 Missing | `tenant.py` create-client makes a data row only; **no `User` login account, no email, no temp password** (provisioned clients can't log in — see prior migration note). `EmailService` (`services/production.py`) only logs. |
| CL-02 | Client picks language on first login | 🟡 Partial | Language switch exists (localStorage), but no first-login flow / no agent default seeding. |
| CL-03 | Agent sets subscription fee (monthly/yearly) | 🟡 Partial | `clients.subscription_fee` field set at create; no period (monthly/yearly) modeling, no enforcement. |
| CL-04 | Client pays via agent's Stripe/PayPal | 🟡 **(Phase A)** | `services/payment.py` is now exposed via `routers/payment.py` (`POST /api/v1/payments/checkout`, `GET /api/v1/payments/status/{id}`); returns 503 when `STRIPE_SECRET_KEY` is unset. Per-agent gateway credentials still not modeled. |
| CL-05 | Suspend client on non-payment | ✅ **(Phase A)** | `dependencies/auth.py::get_current_user` now queries `clients.is_active` and returns 403 for suspended clients. Tested in `tests/test_account_active.py`. |
| — | Automated recurring billing | 🔴 Missing | No scheduler/job queue (no Celery/APScheduler), no Stripe webhook handling. |

---

## 3. POS terminal (SRS §3.4)

| ID | Requirement | Status | Evidence / Gap |
|----|-------------|--------|----------------|
| POS-01 | Cart: items, qty, discounts, taxes | 🟡 Partial | `POSTerminal.tsx` cart + per-item discount; **VAT hardcoded 15%** (no per-product/global rate). |
| POS-02 | Multiple payment methods (cash/card/transfer/loyalty) | 🟡 **(Phase C)** | `create_transaction` accepts an optional `payments: [{method, amount}]` split breakdown, **validates the per-method amounts sum to the invoice total** (400 otherwise), stores it in the new `transactions.payment_breakdown` column, and derives `payment_method` (`"mixed"` when >1). Returned on the transaction + list responses. **(Phase E)** Loyalty accrual/redemption is now wired into this same pay flow — see the Loyalty row in §6. Tested in `tests/test_phase_c_pos.py`. |
| POS-03 | Print ZATCA invoice (thermal/A4) + QR | 🟡 **(Phase C)** | New `GET /api/v1/pos/transactions/{id}/invoice` renders the full **always-Arabic** ZATCA tax-invoice document (RTL, QR, totals) server-side, print-to-PDF ready in any browser. *(Still no thermal/ESC-POS path, and server-side PDF bytes need a headless renderer (WeasyPrint) in front of this HTML.)* Tested in `tests/test_phase_c_pos.py`. |
| POS-04 | Send invoice via email/SMS | 🟡 **(Phase C)** | `POST /api/v1/pos/transactions/{id}/email` sends a receipt via `EmailService` (gated by the per-client `email_receipts` feature flag). Still **stub-logs until SMTP is configured**, and no SMS path. Tested in `tests/test_phase_c_pos.py`. |
| POS-05 | Offline mode (mobile) + sync | 🟡 **(Phase E)** | Web offline path done: an **IndexedDB queue** (`frontend/src/lib/offlineQueue.ts`) buffers completed sales when `navigator.onLine` is false, an **app-shell service worker** (`frontend/public/sw.js`) keeps the POS loading with no network, and queued sales **auto-replay on reconnect** to `POST /api/v1/production/offline/sync`, which **dedupes on a client-generated `offline_id`** (idempotent — a replayed batch never double-posts). Tested in `tests/test_phase_e_offline.py`. *(Still no native mobile app; offline-synced sales get their fiscal QR only once they reach the server.)* |
| POS-06 | Product search by barcode (camera) / name | 🟡 Partial | Keyboard/"scanner-as-keyboard" barcode match; **no camera**; name search limited. |
| POS-07 | Return/refund with ZATCA credit note | 🟡 Partial | Refund creates a negative-amount transaction; **no formal credit-note doc, no link to original invoice**. |
| — | **Atomicity of sale + inventory** | ✅ **(Phase A)** | `routers/pos.py::create_transaction` now deducts stock in the **same DB transaction** as the sale (single commit) via `_deduct_inventory`. Insufficient stock raises 400 and rolls back the whole sale (counter not consumed) unless `allow_negative_stock=true`. Frontend fire-and-forget call removed; legacy `/inventory/deduct` marked deprecated. Tested in `tests/test_pos_atomic.py`. |

---

## 4. ZATCA compliance (SRS §3.5, §7) — **legal blocker**

| ID | Requirement | Status | Evidence / Gap |
|----|-------------|--------|----------------|
| ZA-01 | CSR → ZATCA onboarding, store cert+secret (encrypted) | ✅ **(Phase B)** | Real EC secp256k1 keypair + PKCS#10 EGS CSR (`services/zatca.py::generate_egs_keypair_and_csr`, exposed at `POST /api/v1/zatca/onboard/csr`); compliance + production CSID exchange (`/onboard/compliance-csid`, `/onboard/production-csid`) via the Fatoora API client. Private key + ZATCA secret stored **AES-256-GCM encrypted** in `zatca_credentials`. Live CSID issuance still requires a configured gateway + OTP (503 until then). |
| ZA-02 | Invoice fields + cryptographic stamp via SDK | ✅ **(Phase B)** | Placeholder HMAC removed. `POST /api/v1/zatca/invoices/{id}/sign` produces a **real ECDSA-SHA256 stamp** over the canonical invoice hash with the per-client EGS key (`sign_invoice_hash`), verified at sign time (`verify_stamp`). *Remaining:* embedding the signature as a XAdES `ds:Signature` envelope inside the UBL (needs the field SDK's signed-properties layout). |
| ZA-03 | QR with mandatory fields in TLV | ✅ Implemented | Real byte-level TLV (tags 1–5) + base64 in `routers/pos.py:67`. |
| ZA-04 | Per-client sequential counter + hash chain | ✅ Implemented | Atomic per-client counter `INV-{client}-{counter}` + SHA-256 hash (`pos.py`); Phase B adds a persisted **PIH chain** across signed documents (`zatca_credentials.pih`, seeded with `INITIAL_PIH = base64(SHA256("0"))`). |
| ZA-05 | 6-year retention | ✅ **(Phase B)** | Every signed invoice is archived in `zatca_documents` with `retention_until` computed from `ZATCA_RETENTION_YEARS` (default 6). Retrievable via `GET /api/v1/zatca/documents`. *(Cold-storage/backup of the archive itself is still ops-side.)* |
| ZA-06 | Sandbox/test mode | ✅ **(Phase B)** | `ZATCA_ENVIRONMENT` = `sandbox` \| `simulation` \| `production` selects the Fatoora gateway URL **and** the CSR certificate-template-name; defaults to sandbox and fails closed until explicitly opted in. |
| — | Phase-2 reporting/clearance within 24h | 🟡 **(Phase B)** | `POST /api/v1/zatca/invoices/{doc}/report?clearance=` submits to the Fatoora reporting/clearance endpoints (`ZatcaApiClient.submit_invoice`) and records the response/status on the document. **No scheduler yet** — submission is caller-triggered, not an automatic 24h background job. |
| — | **Receipts/quotations always Arabic** | ✅ **(Phase D)** | All three fiscal/pre-sale documents are now forced Arabic regardless of UI language: the server invoice document (Phase C), the **on-screen POS receipt** (`POSTerminal.tsx` receipt view is now `dir="rtl" lang="ar"`, Arabic labels, SAR, Arabic-Indic digits — Phase D), and the new **quotation document** (`GET /api/v1/entities/quotations/{id}/document`, `PDFInvoiceService.generate_quotation_html`). Quotations now exist as a full feature. Tested in `tests/test_phase_d_quotations.py`. |

> **Bottom line (post-Phase B):** ZATCA is no longer a QR-only skeleton — the cryptography is real (EC keypair + EGS CSR, ECDSA stamp, encrypted secrets, PIH chain, 6-yr retention, sandbox/prod toggle, onboarding + reporting client). **Remaining before a KSA go-live:** (1) embed the stamp as a XAdES `ds:Signature` envelope in the UBL per the official spec; (2) run live onboarding/clearance against a real Fatoora gateway (the client fails closed until configured); (3) add the automatic 24h clearance/reporting background job. These are the field-SDK / live-credential steps; the in-app cryptographic foundation is now in place.

---

## 5. Multi-language (SRS §3.6)

| ID | Requirement | Status | Evidence / Gap |
|----|-------------|--------|----------------|
| L10N-01 | Locale strings ar/en/hi/ur | ✅ Implemented | `lib/i18n.ts`, ~117 keys × 4 languages, complete. |
| L10N-02 | RTL for ar/ur | ✅ Implemented | `document.documentElement.dir` toggled on language change. |
| L10N-03 | Arabic-Indic digits for ar/ur | ✅ **(Phase D)** | Central formatters added: backend `core/formatting.py` (`to_arabic_digits`, `format_money_ar`) renders the always-Arabic invoice/quotation amounts, dates and quantities in Arabic-Indic numerals (٠-٩) with the Arabic decimal/thousands separators; frontend `lib/format.ts` (`toArabicDigits`/`formatNumber`/`formatMoney`) does the same for ar/ur and drives the always-Arabic on-screen receipt. Tested in `tests/test_phase_d_arabic_digits.py`. *(Identifiers like invoice numbers stay Western by design.)* |
| L10N-04 | Locale date/time (Gregorian) | ✅ Implemented | UTC + `toLocaleString`. |
| L10N-05 | Agent default language; client override | ✅ **(Phase D)** | The agent sets a `default_language` in the branding editor (`PUT /api/v1/branding/update`); it is returned on agent/client branding responses, **inherited by a client at creation** when no explicit language is chosen (`routers/tenant.py`), and **applied on first client login** (`BrandingContext.applyDefaultLanguage`, only when the user hasn't already picked one — explicit choice wins). Tested in `tests/test_phase_d_language.py`. |

---

## 6. Production-readiness checklist

### 🔴 Critical
| Item | Status | Evidence / Gap |
|------|--------|----------------|
| Granular role permissions (refund/reports/edit) | 🟡 **(Phase C)** | **Per-client feature flags are now enforced** via `dependencies/features.require_feature` (default-on; agent toggle at `.../clients/{id}/features`). The separate `permissions` grant/revoke table (per-staff action permissions) is still **not enforced** on routes — that finer-grained layer remains. |
| Session mgmt (refresh tokens, forced logout, timeout) | 🟡 **(Phase A)** | Refresh tokens added: login/register return a `refresh_token`; `POST /api/v1/auth/refresh` mints new access tokens; access/refresh tokens carry a `type` claim and are not interchangeable. No server-side revocation store yet (forced logout still relies on client discard). Tested in `tests/test_auth.py`. |
| Rate limiting | ✅ Implemented | `RateLimitMiddleware` (token bucket) in `middlewares/production.py` — **but in-memory only** (won't scale across replicas); confirm it's added in `main.py`. |
| Input validation/sanitization | 🟡 Partial | Pydantic + max-body middleware; no business-rule validation (price>0, etc.). |
| CORS lockdown | ✅ **(Phase A)** | New `core/cors.py::get_cors_config()` drives `main.py`: `ALLOWED_ORIGINS` (env) pins exact origins with credentials; dev falls back to wildcard **without** credentials; prod with no list **fails closed** to localhost. Tested in `tests/test_cors.py`. |
| DB migrations (Alembic) | 🟡 **(Phase A)** | `alembic/env.py` now resolves the DB URL from app settings (async-normalized) and supports offline + online modes; `alembic upgrade head` applies the existing revision chain to a fresh DB (verified). Runtime `create_all` still used for dev convenience. |
| Transaction atomicity | ✅ **(Phase A)** | POS sale + inventory now atomic — see §3. |
| Data backup/recovery | 🔴 Missing | None. |
| Audit trail completeness | 🟡 **(Phase C)** | New `AuditLogMiddleware` (`middlewares/audit.py`) auto-writes an `audit_logs` row for **every authenticated, successful mutation** (POST/PUT/PATCH/DELETE on `/api/v1`, auth paths excluded), resolving the actor from the bearer token; writes are best-effort in their own session so they never break a request. Tested in `tests/test_phase_c_audit.py`. *(Capturing before/after field-level diffs is still future work.)* |
| ZATCA full compliance | 🟡 **(Phase B)** | Real crypto/onboarding/retention done (see §4); XAdES envelope, live clearance, and the 24h auto-submit job remain. |

### 🟠 Important
| Item | Status | Evidence / Gap |
|------|--------|----------------|
| Error tracking (Sentry) | 🟡 **(Phase E)** | `core/observability.py::init_sentry()` wired into `main.py` — a **config-gated no-op** that reports to Sentry only when `SENTRY_DSN` is set *and* the optional `sentry-sdk` package is installed (so dev/CI run unchanged). Tested in `tests/test_phase_e_observability.py`. *(Log aggregation/shipping still ops-side.)* |
| Health checks | ✅ Implemented | `/health`, `/database/health`, `/api/v1/production/health/detailed`. |
| Structured logging | ✅ Implemented | JSON formatter + correlation IDs (`middlewares/production.py`); **local files only**, no aggregation. |
| Performance monitoring | 🟡 Partial | In-memory p95/latency metrics (`production.py`); lost on restart. |
| PDF receipt/invoice export | 🟡 Partial | `PDFInvoiceService` returns **HTML only** (needs a renderer); CSV export exists (`features.py:636`). |
| Email notifications | 🟡 **(Phase A)** | `EmailService` reachable via `POST /api/v1/integrations/email/send` and now also drives receipts (POS-04) + low-stock alerts (still stub-logs until SMTP configured). |
| Low-stock alerts | 🟡 **(Phase C)** | On-demand `/products/low-stock` + `/inventory/alerts` plus **automated** alerts: `create_transaction` fires a low-stock email (best-effort, post-commit) for any sold product that drops to/below threshold. Delivery is stub/log until SMTP configured. Covered in `tests/test_phase_c_pos.py`. |
| Supplier & purchase orders | 🟠 CRUD-only | Tables/CRUD only; no PO workflow/receiving. |
| Shift/cash drawer | 🟡 Partial | `routers/shifts.py` open/close CRUD; no cash-difference calc/validation. |
| Payment method breakdown | ✅ **(Phase C/E)** | `transactions.payment_breakdown` column + validated `payments[]` on POS create (see POS-02). **(Phase E)** Loyalty redemption in the pay flow is now wired (redeemed points apply as an order discount within the atomic sale). |
| Multi-branch | 🟡 Partial | `branches` + `branch_id` fields; branch isolation not consistently enforced in queries. |
| User profile / **change password** | ✅ **(Phase A)** | `POST /api/v1/users/change-password` (verifies current password, rejects no-op/wrong) added in `routers/user.py` + `services/user.py`; frontend `changePassword()` wrapper in `lib/api.ts`. Tested in `tests/test_auth.py`. |
| Bulk import/export | ✅ **(Phase A)** | `BulkImportService` wired via `POST /api/v1/integrations/bulk-import/products` — validates the CSV **and inserts** valid rows for the client. Tested in `tests/test_integrations.py`. (Customer import still validate-only.) |
| Global search & filtering | ✅ **(Phase A)** | `SearchService.global_search` wired via `GET /api/v1/integrations/search?q=` (user-scoped). Tested in `tests/test_integrations.py`. |
| Server-side pagination | 🟡 **(Phase C)** | Backend lists already take `skip`/`limit`. Frontend now has a reusable `DataPagination` control (`components/DataPagination.tsx`) wired into **ProductManagement** (10/page, bounded DOM). Remaining list pages still render large fetches — roll the same control out across them. |

### 🟡 Nice-to-have
| Item | Status |
|------|--------|
| Offline POS (SW/IndexedDB) | 🟡 **(Phase E)** — IndexedDB queue + app-shell service worker + idempotent reconnect sync (see POS-05) |
| Loyalty/rewards | ✅ **(Phase E)** — accrual + redemption wired into the **atomic** POS sale (`services/loyalty.py`); points earn on each customer sale and `redeem_points` redeems as an order discount, both committed with the sale. Tested in `tests/test_phase_e_loyalty.py` |
| Customer-facing display | 🟡 Partial (`CustomerDisplay.tsx` exists) |
| Receipt template customization | 🟠 CRUD-only (no render engine) |
| SAR-only currency | 🟡 Partial (15% VAT/SAR assumptions hardcoded, not configurable) |
| Thermal printer (WebUSB/BT) | 🟡 **(Phase E)** — ESC/POS byte builder (`services/escpos.py`) + `GET /pos/transactions/{id}/escpos` (base64) + frontend WebUSB helper (`lib/thermalPrint.ts`); embeds the canonical ZATCA QR. Tested in `tests/test_phase_e_escpos.py`. Arabic glyphs depend on the printer code page (the always-Arabic HTML invoice remains the native-Arabic path) |
| Mobile-responsive / tablet POS | 🟡 Partial |
| Per-agent API rate plans | 🔴 Missing |
| White-label mobile app (RN/Flutter) | 🔴 Missing — **out of scope for this repo** (a separate native codebase, not this FastAPI+React app; see §13). The web POS is now offline-capable (POS-05) as the interim path |
| Advanced analytics/forecasting | 🟡 **(Phase E)** — `GET /api/v1/production/analytics/forecast` (moving-average projection + trend) is wired and now reachable from the frontend (`getSalesForecast`); real ML forecasting remains a stub |
| Webhook system | 🟡 **(Phase A)** — `WebhookDispatcher` now reachable via `POST /api/v1/integrations/webhooks/dispatch` (HMAC-signed; stub delivery until an HTTP client is configured) |

---

## 7. Cross-cutting architectural findings

1. ~~**Orphaned service code**~~ — **(Phase A)** Stripe, webhooks, email, bulk-import and search wired (`routers/payment.py`, `routers/integrations.py`). **(Phase B)** ZATCA XML/signing/reporting now wired via `routers/zatca.py` (`zatca_service.generate_xml_invoice` is reached when signing). No orphaned ZATCA code remains.
2. ~~**White-labeling doesn't render** (AG-04)~~ — **(Phase A)** branding now applied at runtime via `BrandingContext`.
3. **No real auth lifecycle** — **(Phase A + C)** refresh tokens, `is_active` enforcement, change-password, and **per-client feature enforcement** (Phase C) are done; the finer-grained per-staff `permissions` table and a token-revocation store are still pending.
4. **Data-integrity risks** — **(Phase A + C)** sale/inventory atomic, Alembic functional, and the **audit log is now auto-written** on every authenticated mutation (Phase C); data backup/recovery still missing.
5. ~~**ZATCA is a façade**~~ — **(Phase B)** real ECDSA stamp, EGS CSR + CSID onboarding, AES-256 secrets, PIH chain, 6-yr retention, sandbox/prod toggle, reporting client. Residual gaps: XAdES envelope embedding, live-gateway clearance, and the 24h auto-submit job.
6. ~~**No mobile / offline**~~ — **(Phase E)** the web POS is now **offline-capable** (IndexedDB queue + app-shell service worker + idempotent reconnect sync, POS-05). The **native white-label mobile app (RN/Flutter)** remains out of scope for this repo (separate native codebase).

---

## 8. Recommended remediation order

Aligns with the SRS author's "top 5" and adds the integrity/white-label blockers:

**Phase A — make the core honest & safe (1–2 wks) — ✅ DONE (2026-06-02)**
1. ✅ Make POS sale + inventory deduction **atomic** (single backend endpoint/transaction).
2. ✅ **Wire what exists**: Stripe (`routers/payment.py`), webhook dispatch + email + bulk-import + search (`routers/integrations.py`). *(Real SMTP/HTTP delivery still pending — services remain in stub/log mode until credentials configured.)*
3. ✅ **Apply agent branding** at runtime (CSS variables + logo) — fulfills white-label promise (AG-04).
4. ✅ Auth lifecycle: **change-password**, enforce `is_active`, refresh tokens. *(Token revocation store still pending.)*
5. ✅ Lock down **CORS**; **Alembic** env wired and verified (`upgrade head` applies the chain).

**Phase B — ZATCA Phase-2 (legal, 2–3 wks) — ✅ DONE (2026-06-02)** — real EC keypair + EGS CSR, ECDSA cryptographic stamp/CSID, AES-256 cert/secret storage, sandbox/simulation/production toggle, 6-yr retention, and a Fatoora onboarding + reporting/clearance API client (fails closed to 503 until a gateway is configured). *Residual (needs live gateway / field SDK, tracked in §10 follow-ups):* XAdES `ds:Signature` envelope embedding, live clearance against a real Fatoora endpoint, and an automatic 24h clearance/reporting background job.

**Phase C — required product features (2–4 wks) — ✅ DONE (2026-06-02)** — master agent-create (MA-01) + slot refill (MA-04) + global tax (MA-05); always-Arabic invoice document; email receipts (POS-04); payment breakdown; automated low-stock alerts; per-client feature enforcement; auto-write audit log; frontend pagination (ProductManagement). See [§11](#11-phase-c-implementation-log). *Residual:* SMTP/SMS delivery, server-side PDF bytes (headless renderer), thermal/ESC-POS, per-staff `permissions` enforcement, pagination rollout to remaining list pages.

**Phase D — Arabic-output rule & polish — ✅ DONE (2026-06-02)** — on-screen POS receipt forced Arabic; **quotation** feature added end-to-end (entity triad + always-Arabic, non-fiscal quotation document + frontend page); central Arabic-Indic digit formatter (backend + frontend); agent-default language propagated to clients (set → inherited → applied on first login). See [§12](#12-phase-d-implementation-log). *Residual:* on-screen quotation builder is minimal (no PDF bytes/thermal — shares the headless-renderer follow-up); SMS receipts and `name_ar` localisation of catalog items remain.

**Phase E — mobile/offline & nice-to-haves — ✅ DONE (2026-06-02)** — loyalty accrual + redemption wired into the atomic POS sale; web offline POS (IndexedDB queue + service worker + idempotent reconnect sync); thermal/ESC-POS printing (backend bytes + WebUSB); analytics forecast reachable; config-gated Sentry error tracking. See [§13](#13-phase-e-implementation-log). *Residual:* the **native white-label RN/Flutter mobile app** is a separate codebase (out of scope for this repo); real ML forecasting, log shipping, SMS receipts, per-staff `permissions`, token-revocation store, and data backup/recovery also remain.

> Effort estimate (SRS author's): Critical ~2–3 wks, Important ~3–4 wks, Nice-to-have ~4–6 wks — realistic **only after** the "wire the orphaned code" cleanup, which is cheap and unblocks several items at once.

---

## 9. Phase A implementation log

Completed **2026-06-02**. All changes are covered by a new backend test suite
(`backend/tests/`, 15 tests, all green via `python -m pytest`).

### Backend changes
| Area | Files | What changed |
|------|-------|--------------|
| Atomic sale + inventory | `routers/pos.py`, `routers/features.py` | `create_transaction` deducts stock in the same transaction (`_deduct_inventory`); oversell → 400 + full rollback; `allow_negative_stock` opt-out; legacy `/inventory/deduct` deprecated. |
| Refresh tokens | `core/auth.py`, `services/auth.py`, `routers/auth.py`, `schemas/auth.py` | `create_refresh_token`, `type` claim on every token, `POST /api/v1/auth/refresh`; access/refresh not interchangeable. |
| `is_active` enforcement | `dependencies/auth.py` | `get_current_user` blocks suspended clients (403). |
| Change password | `routers/user.py`, `services/user.py` | `POST /api/v1/users/change-password` (verifies current, rejects no-op). |
| CORS lockdown | `core/cors.py`, `main.py`, `core/config.py` | Env-aware `get_cors_config()`; `ALLOWED_ORIGINS` / `REFRESH_TOKEN_EXPIRE_MINUTES` settings. |
| Stripe wiring | `routers/payment.py` | `POST /api/v1/payments/checkout`, `GET /api/v1/payments/status/{id}`; 503 when unconfigured. |
| Bulk-import / search / webhook / email wiring | `routers/integrations.py` | `bulk-import/products` (validates + inserts), `search`, `webhooks/dispatch`, `email/send`. |
| Alembic | `alembic/env.py` | Resolves async DB URL from settings; offline + online modes; chain verified with `upgrade head`. |

### Frontend changes
| Area | Files | What changed |
|------|-------|--------------|
| White-label branding (AG-04) | `contexts/BrandingContext.tsx`, `App.tsx` | Fetches branding by role, applies CSS vars (`--primary`/`--ring`/`--accent`/`--radius`), font, logo; clears on logout. Includes `hexToHslTriple`. |
| POS atomicity | `pages/POSTerminal.tsx` | Removed fire-and-forget `deductInventory`; backend now handles it. |
| Refresh + change-password | `lib/auth.ts`, `lib/api.ts` | Stores `refresh_token`, `refreshAccessToken()`, `changePassword()` wrapper. |

### Tests (`backend/tests/`)
`test_pos_atomic.py` (deduction, rollback, override), `test_auth.py` (refresh flow, change-password), `test_account_active.py` (suspension), `test_cors.py` (config matrix), `test_integrations.py` (bulk import + scoped search), `test_payment.py` (503 when unconfigured + auth gate).

### Known follow-ups deferred to later phases
Token-revocation store; per-agent Stripe credentials; real SMTP/HTTP delivery; permission enforcement; auto-written audit log; Alembic as the *sole* schema source (runtime `create_all` still on). ~~ZATCA real cryptographic stamp/onboarding/reporting remains **Phase B**~~ — **done, see §10.**

---

## 10. Phase B implementation log

Completed **2026-06-02**. ZATCA Phase-2 cryptography made real. The suite now
has **27 tests** (15 Phase A + 12 ZATCA), all green via `python -m pytest`.

### What changed
| Area | Files | What changed |
|------|-------|--------------|
| Real crypto service | `services/zatca.py` (new) | EC **secp256k1** keypair + PKCS#10 **EGS CSR** (subject + EGS `subjectAltName` directory carrying VAT/serial/invoice-type/address/category + ZATCA cert-template-name extension); **ECDSA-SHA256 cryptographic stamp** (`sign_invoice_hash`/`verify_stamp`); **AES-256-GCM** secrets at rest (`encrypt_secret`/`decrypt_secret`); base64 invoice hash + `INITIAL_PIH` chain seed; **Fatoora API client** (compliance CSID, production CSID, reporting/clearance) with sandbox/simulation/production resolution that **fails closed** (503) unless explicitly configured. |
| Placeholder stamp removed | `services/production.py` | `ZATCAService.generate_cryptographic_stamp` now delegates to the real ECDSA signer when a per-client key is supplied (HMAC retained only as a clearly-labelled non-compliant dev fallback); normalises hex/base64 hashes. |
| Persistence | `models/zatca_credentials.py`, `models/zatca_documents.py` (new) | Per-client onboarding store (encrypted key/CSID/secret + PIH chain head) and the retained signed-invoice archive (`retention_until`). |
| Endpoints | `routers/zatca.py` (new) | `GET /status`; onboarding `POST /onboard/csr`, `/onboard/compliance-csid`, `/onboard/production-csid`; `POST /invoices/{txn}/sign` (real stamp + chain advance + retention); `POST /invoices/{doc}/report?clearance=`; `GET /documents`. Client-scoped via the tenancy `clients` row. |
| Config | `core/config.py` | `ZATCA_ENVIRONMENT`, `ZATCA_API_BASE_URL`, `ZATCA_ENCRYPTION_KEY`, `ZATCA_RETENTION_YEARS`. |
| Migration | `alembic/versions/b1f2c3d4e5f6_zatca_phase_b.py` (new) | Creates `zatca_credentials` + `zatca_documents`; `alembic upgrade head` applies the full chain to a fresh DB (verified). |

### Tests (`backend/tests/test_zatca.py`)
Unit: keypair/CSR validity (VAT + serial present in DER), stamp sign/verify round-trip + tamper-rejection, AES secret round-trip, gateway-unconfigured detection. HTTP: CSR requires `vat_number`; CSR generation + status; sign produces a **verifiable** stamp with 6-yr retention and advances the PIH; multi-invoice **hash chaining**; sign-without-CSR rejected; report/compliance **fail closed** (400/503) without onboarding/gateway; non-client gets 403.

### Known follow-ups deferred to later phases
**XAdES `ds:Signature` envelope** embedding into the UBL (current stamp is a real but detached ECDSA signature); **live clearance** against a real Fatoora gateway (client is wired but fails closed until configured); **automatic 24h clearance/reporting background job** (submission is currently caller-triggered — no scheduler). Carried over from Phase A: token-revocation store, per-agent Stripe creds, real SMTP/HTTP delivery, permission enforcement, auto-written audit log.

---

## 11. Phase C implementation log

Completed **2026-06-02**. The required product features are wired and enforced.
The suite now has **42 tests** (27 prior + 15 Phase C), all green via
`python -m pytest`.

### Backend changes
| Area | Files | What changed |
|------|-------|--------------|
| Master agent provisioning (MA-01) | `routers/tenant.py` | `POST /master/agents` creates a login `User` (email + `secrets`-generated temp password, bcrypt-hashed) **and** the linked `Agents` row; resolves `client_slots` from a `package_id` or explicit `slots`; 409 on duplicate email. |
| Slot refill (MA-04) | `routers/tenant.py` | `POST /master/agents/{id}/slots` adds N slots to `package_type` (master-only). |
| Global tax rate (MA-05) | `models/system_settings.py` (new), `services/system_settings.py` (new), `routers/tenant.py`, `routers/pos.py` | Platform key/value store; `GET /tenant/tax-rate` + `PUT /master/tax-rate`; POS resolves the **effective** VAT via `get_effective_tax_rate` (global rate overrides per-request `vat_rate`). |
| Payment breakdown (POS-02) | `models/transactions.py`, `routers/pos.py` | New `payment_breakdown` column; `payments[]` validated to sum to total; `payment_method` derived (`mixed`). |
| Invoice document + email (POS-03/04) | `routers/pos.py` | `GET /pos/transactions/{id}/invoice` (always-Arabic HTML via `PDFInvoiceService`); `POST /pos/transactions/{id}/email` (gated by `email_receipts` feature). |
| Automated low-stock alerts | `routers/pos.py` | Post-commit best-effort `EmailService.send_low_stock_alert` for sold products at/below threshold. |
| Per-client feature enforcement (AG-03) | `dependencies/features.py` (new), `routers/tenant.py` | `require_feature(name)` dependency (default-on; `is_enabled=False` → 403); `POST /agent/clients/{id}/features` runtime toggle; `POST /agent/clients/{id}/toggle` suspend/reactivate (CL-05). |
| Auto-write audit log | `middlewares/audit.py` (new), `services/audit.py` (new), `main.py` | Middleware records authenticated mutations to `audit_logs` (own session, best-effort, auth paths skipped). |
| Migration | `alembic/versions/c2d3e4f5a6b7_phase_c.py` (new) | Creates `system_settings`, adds `transactions.payment_breakdown`; `alembic upgrade head` applies the full chain to a fresh DB (verified). |

### Frontend changes
| Area | Files | What changed |
|------|-------|--------------|
| Pagination | `components/DataPagination.tsx` (new), `pages/ProductManagement.tsx` | Reusable pagination control; ProductManagement now pages its list (10/page) instead of rendering everything. |
| API wrappers | `lib/api.ts` | `addAgentSlots`, `getTaxRate`, `setGlobalTaxRate`, `setClientFeature`, `emailReceipt`, `invoiceDocumentPath`. |

### Tests (`backend/tests/`)
`test_phase_c_master.py` (agent provisioning + login + role, duplicate-email 409, slot refill, global-tax set/get + 5% applied to a sale + non-master 403), `test_phase_c_pos.py` (split payment ok/mismatch, always-Arabic invoice doc, email receipt, low-stock sale succeeds), `test_phase_c_features.py` (agent disables client feature → 403, cross-agent 404, suspend blocks auth), `test_phase_c_audit.py` (mutation writes a row, GET does not).

### Known follow-ups deferred to later phases
Real SMTP/SMS delivery; server-side **PDF bytes** (headless renderer in front of the Arabic HTML) + thermal/ESC-POS; loyalty redemption in the pay flow; per-staff `permissions` enforcement; pagination rollout to the remaining list pages; field-level audit diffs. Carried over: token-revocation store, per-agent Stripe creds, data backup/recovery. ~~**Phase D**~~ **done, see §12.** **Phase E** (mobile/offline, Sentry, analytics) remains.

---

## 12. Phase D implementation log

Completed **2026-06-02**. The Arabic-output rule and its polish are done. The
suite now has **51 tests** (42 prior + 9 Phase D), all green via `python -m pytest`.

### Backend changes
| Area | Files | What changed |
|------|-------|--------------|
| Arabic-Indic digit formatter (L10N-03) | `core/formatting.py` (new), `services/production.py` | `to_arabic_digits` / `format_money_ar` (Arabic-Indic numerals + Arabic decimal `٫` / thousands `٬` separators); the always-Arabic invoice document now renders amounts, dates and quantities in Arabic-Indic digits (identifiers like the invoice number stay Western by design). |
| Quotation feature (عرض سعر) | `models/quotations.py`, `services/quotations.py`, `routers/quotations.py` (new triad), `services/production.py` | Standard CRUD entity at `/api/v1/entities/quotations` (auto-assigns a `QT-…` number) **plus** `GET /{id}/document` → `PDFInvoiceService.generate_quotation_html`, an **always-Arabic, non-fiscal** quotation document (RTL/Arabic, Arabic-Indic digits, validity date, explicitly labelled "not a tax invoice" — no ZATCA QR/stamp). Owner-scoped. |
| Agent default language (L10N-05) | `routers/tenant.py`, `routers/features.py` | `default_language` exposed on the agent/client `BrandingResponse` and settable via `PUT /api/v1/branding/update`; a new client **inherits the agent default** when no language is supplied at creation (explicit value overrides). |
| Migration | `alembic/versions/d3e4f5a6b7c8_phase_d.py` (new) | Creates the `quotations` table; `alembic upgrade head` applies the full chain to a fresh DB (verified). (The agent `default_language` column already existed from `368d6a17ebd5`.) |

### Frontend changes
| Area | Files | What changed |
|------|-------|--------------|
| Arabic-Indic formatter | `src/lib/format.ts` (new) | `toArabicDigits`, `formatNumber`/`formatMoney` (Arabic-Indic for ar/ur, Western otherwise) and `*Ar` always-Arabic variants. |
| Always-Arabic on-screen receipt | `src/pages/POSTerminal.tsx` | The post-sale receipt view is now `dir="rtl" lang="ar"` with Arabic labels, SAR, Arabic-Indic numerals and Arabic payment-method names — regardless of the cashier's UI language. |
| Quotation page | `src/pages/QuotationManagement.tsx` (new), `src/App.tsx`, `src/lib/api.ts` | List/create/delete quotations with live VAT totals; "view" opens the always-Arabic quotation document (fetched with the bearer token into a new tab). Routed under the shared agent/client group; API wrappers + `quotationDocumentPath` added. |
| Agent default language UI | `src/pages/BrandingEditor.tsx`, `src/contexts/BrandingContext.tsx`, `src/lib/api.ts` | Branding editor gains a default-language selector (persisted via `updateBranding`); `BrandingContext.applyDefaultLanguage` applies the agent default on first client login (only when the user hasn't already chosen — explicit choice wins). |
| i18n | `src/lib/i18n.ts` | Added `quotations`, `new_quotation`, `item_name`, `add_item`, `notes`, `no_quotations`, `customer_name`, `default_language` to all four languages. |

### Tests (`backend/tests/`)
`test_phase_d_quotations.py` (auto-numbered create, always-Arabic quotation document that is *not* a tax invoice, owner-scoping 404), `test_phase_d_arabic_digits.py` (`format_money_ar` digits/separators, letters untouched, invoice totals render Arabic-Indic while the invoice number stays Western), `test_phase_d_language.py` (agent sets default language → returned on branding; new client inherits it; explicit override wins; client branding exposes the agent default).

### Known follow-ups deferred to later phases
Server-side **PDF bytes** (headless renderer) for the quotation/receipt documents; SMS receipts; `name_ar` localisation of catalog item names within the Arabic documents. ~~**Phase E**~~ **done, see §13.** Residual after Phase E: native white-label mobile app, real ML forecasting, log shipping, per-staff permissions, token revocation, data backup.

---

## 13. Phase E implementation log

Completed **2026-06-02**. Mobile/offline & nice-to-haves. Much of this surface
already existed as *orphaned* endpoints in `routers/production.py` (loyalty
earn/redeem/balance, offline sync, forecast); Phase E turns the headline gaps
into real, wired, tested behaviour. The suite now has **63 tests** (51 prior + 12
Phase E), all green via `python -m pytest`.

### Backend changes
| Area | Files | What changed |
|------|-------|--------------|
| Loyalty in the atomic sale | `services/loyalty.py` (new), `routers/pos.py` | `create_transaction` now resolves the merchant's active loyalty program and, **within the same DB transaction as the sale + inventory deduction**, (a) redeems `redeem_points` against the customer's balance as an order discount (validated: positive, ≥ `min_redemption_points`, ≤ balance, ≤ subtotal) and (b) accrues `floor(total × points_per_sar)`. A rolled-back sale (e.g. oversell) never moves the ledger. New optional request fields `customer_id` / `redeem_points`; loyalty outcome returned on the response. |
| Thermal/ESC-POS receipt | `services/escpos.py` (new), `routers/pos.py` | `EscPosBuilder` emits a raw ESC/POS stream (init, centered header, line items, totals, **ZATCA QR via the `GS ( k` model-2 sequence**, partial cut). `GET /api/v1/pos/transactions/{id}/escpos` returns it base64-encoded (owner-scoped). |
| Error tracking (Sentry) | `core/observability.py` (new), `main.py`, `core/config.py` | `init_sentry()` — a **config-gated no-op** initialised at startup; reports only when `SENTRY_DSN` is set **and** `sentry-sdk` is installed. `sentry_dsn` / `sentry_traces_sample_rate` settings added. |
| Offline sync (hardening/coverage) | `routers/production.py` (existing `/offline/sync`) | Confirmed + locked down with tests: dedupe on the client-generated `offline_id` makes a replayed batch idempotent (re-posting the same queue skips duplicates rather than double-inserting). |

### Frontend changes
| Area | Files | What changed |
|------|-------|--------------|
| Offline POS queue | `src/lib/offlineQueue.ts` (new), `src/main.tsx`, `src/pages/POSTerminal.tsx` | IndexedDB-backed queue (`enqueueTransaction`/`getQueued`/`flushQueue`/`registerAutoFlush`). When `navigator.onLine` is false, checkout buffers the sale (with an `offline_id`) and shows a "saved offline, will sync" receipt; a reconnect listener auto-flushes to `/production/offline/sync`. |
| App-shell service worker | `frontend/public/sw.js` (new), `src/main.tsx` | Cache-first app shell so the POS keeps loading with no network; API traffic is never cached (fails fast so the queue takes over). Registered in production builds only. |
| Thermal printing | `src/lib/thermalPrint.ts` (new), `src/pages/POSTerminal.tsx` | `printEscPos(base64)` streams the ESC/POS bytes to a WebUSB printer; a print button appears on the receipt when `isThermalPrintSupported()`. |
| API wrappers | `src/lib/api.ts` | `getEscposReceipt`, `getLoyaltyBalance`, `getSalesForecast`, `syncOfflineTransactions`. |

### Tests (`backend/tests/`)
`test_phase_e_loyalty.py` (points accrue on a sale; redemption applies as a discount and recomputes VAT/total + balance; redeem requires a customer; insufficient-points 400; **redemption rolls back with a failed/oversold sale** so points aren't spent), `test_phase_e_escpos.py` (byte-structure: ESC @ init, embedded invoice number, `GS ( k` QR family, `GS V` partial cut; the endpoint returns base64 and is owner-scoped 404), `test_phase_e_offline.py` (sync is idempotent on `offline_id`; empty batch rejected), `test_phase_e_observability.py` (Sentry is a no-op without/blank DSN). Frontend changes pass `tsc --noEmit` and `eslint`.

### Out of scope for this repo / residual
The **native white-label mobile app (RN/Flutter)** is a separate native codebase, not this FastAPI + React application — the offline-capable web POS (POS-05) is the interim path here. Real **ML sales forecasting** (the endpoint is a moving-average stub), **log shipping/aggregation**, **SMS receipts**, server-side **PDF bytes** (headless renderer), per-staff **`permissions`** enforcement, a **token-revocation store**, and **data backup/recovery** also remain as ops/later work.
