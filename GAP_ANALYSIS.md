# Gap Analysis — Multi-Tenant POS vs. SRS v1.0

**Date:** 2026-06-02
**Scope:** `backend/` (FastAPI) + `frontend/` (React/TS) compared against `srs.md` (functional SRS §3 + production-readiness checklist + the "receipts/quotations always Arabic" rule).

> **▶ Phase A completed 2026-06-02** — see [§9 Phase A implementation log](#9-phase-a-implementation-log) for the full change list, file references, and the new `backend/tests/` suite (15 tests, all passing). Status cells touched by Phase A are marked **✅ (Phase A)** below.

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
| MA-01 | Master creates agent (company, email, phone, package) | 🔴 Missing | Frontend `createAgent` calls `POST /api/v1/tenant/master/agents` (`lib/api.ts:282`) but **no such endpoint exists** — `routers/tenant.py` only has `GET /master/agents` and `POST /master/agents/{id}/toggle`. A generic `POST /api/v1/entities/agents` exists (`routers/agents.py`) but isn't master-scoped and isn't what the UI calls. |
| MA-02 | Deduct one slot on client creation | ✅ Implemented | `routers/tenant.py:284` checks `used_slots` vs `package_type`, increments on create. |
| MA-03 | Master sees used vs remaining slots | ✅ Implemented | `tenant.py` `AgentStatsResponse` + `remaining_slots` calc. |
| MA-04 | Master refills/adds slots | 🔴 Missing | No endpoint to change `package_type`/add slots. |
| MA-05 | Master sets global tax rate; agents inherit, can't override | 🔴 Missing | VAT is per-product (`models/products.py`, default 15.0); no global tax setting or inheritance. POS hardcodes 15% (`POSTerminal.tsx`). |
| AG-01 | Agent uploads logo to cloud bucket | 🟡 Partial | `routers/storage.py` issues presigned upload URLs but requires external `OSS_SERVICE_URL`/`OSS_API_KEY` (an atoms-style OSS); not a self-hosted/S3 setup. `agents.logo_url` stores the result. |
| AG-02 | Agent sets primary/secondary color, radius, font | ✅ Implemented | Fields on `models/agents.py`; editor `BrandingEditor.tsx`; persisted via `PUT /api/v1/branding/update` (`routers/features.py:445`). |
| AG-03 | Agent toggles features per client | 🟡 Partial | `agent_features`/`client_features` tables + features created on client creation (`tenant.py`), but **no runtime per-client toggle endpoint** and features aren't enforced in the UI/route gating. |
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
| POS-02 | Multiple payment methods (cash/card/transfer/loyalty) | 🟠 Stub | Single `payment_method` string; **no split/breakdown** (cash+card), no loyalty redemption in pay flow. |
| POS-03 | Print ZATCA invoice (thermal/A4) + QR | 🟡 Partial | QR (TLV) rendered on receipt; **browser-print only**, no thermal/ESC-POS, no A4 PDF. |
| POS-04 | Send invoice via email/SMS | 🔴 Missing | No email/SMS sending anywhere (stub logger only). |
| POS-05 | Offline mode (mobile) + sync | 🔴 Missing | No mobile app, no service worker/IndexedDB, no sync queue. |
| POS-06 | Product search by barcode (camera) / name | 🟡 Partial | Keyboard/"scanner-as-keyboard" barcode match; **no camera**; name search limited. |
| POS-07 | Return/refund with ZATCA credit note | 🟡 Partial | Refund creates a negative-amount transaction; **no formal credit-note doc, no link to original invoice**. |
| — | **Atomicity of sale + inventory** | ✅ **(Phase A)** | `routers/pos.py::create_transaction` now deducts stock in the **same DB transaction** as the sale (single commit) via `_deduct_inventory`. Insufficient stock raises 400 and rolls back the whole sale (counter not consumed) unless `allow_negative_stock=true`. Frontend fire-and-forget call removed; legacy `/inventory/deduct` marked deprecated. Tested in `tests/test_pos_atomic.py`. |

---

## 4. ZATCA compliance (SRS §3.5, §7) — **legal blocker**

| ID | Requirement | Status | Evidence / Gap |
|----|-------------|--------|----------------|
| ZA-01 | CSR → ZATCA onboarding, store cert+secret (encrypted) | 🔴 Missing | No CSR generation, no ZATCA API call, no cert storage, no AES-256. `clients` has only `zatca_enabled`, `vat_number`, `invoice_counter`. |
| ZA-02 | Invoice fields + cryptographic stamp via SDK | 🟡 Partial | Fields present; **stamp is a placeholder** `hmac.new(b"…PLACEHOLDER…")` in `services/production.py` — not a real CSID/ECDSA signature. |
| ZA-03 | QR with mandatory fields in TLV | ✅ Implemented | Real byte-level TLV (tags 1–5) + base64 in `routers/pos.py:67`. |
| ZA-04 | Per-client sequential counter + hash chain | ✅ Implemented | Atomic per-client counter `INV-{client}-{counter}` + SHA-256 hash (`pos.py`). |
| ZA-05 | 6-year retention | 🔴 Missing | No retention policy/archival. |
| ZA-06 | Sandbox/test mode | 🔴 Missing | No prod/sandbox switch. |
| — | Phase-2 reporting/clearance within 24h | 🔴 Missing | UBL XML generation is partial (`production.py`) but **no submission to Fatoora**, no background job. |
| — | **Receipts/quotations always Arabic** | 🟡 Partial | PDF/HTML invoice (`production.py` `PDFInvoiceService`) is hardcoded `dir="rtl" lang="ar"` ✅; but the **on-screen POS receipt follows the UI language** (not forced Arabic), and **quotations don't exist** at all. |

> **Bottom line:** ZATCA support is a *QR + sequencing skeleton*. The compliance-critical pieces (onboarding, real cryptographic stamp, reporting) are absent. This must be built on the official Fatoora SDK before any KSA go-live.

---

## 5. Multi-language (SRS §3.6)

| ID | Requirement | Status | Evidence / Gap |
|----|-------------|--------|----------------|
| L10N-01 | Locale strings ar/en/hi/ur | ✅ Implemented | `lib/i18n.ts`, ~117 keys × 4 languages, complete. |
| L10N-02 | RTL for ar/ur | ✅ Implemented | `document.documentElement.dir` toggled on language change. |
| L10N-03 | Arabic-Indic digits for ar/ur | 🟡 Partial | Some reports use `toLocaleString('ar-SA')`; **POS prices/cart use Western digits** (`toFixed(2)`); no central digit formatter. |
| L10N-04 | Locale date/time (Gregorian) | ✅ Implemented | UTC + `toLocaleString`. |
| L10N-05 | Agent default language; client override | 🟡 Partial | Client override works (localStorage); **no agent-set default** propagated to client. |

---

## 6. Production-readiness checklist

### 🔴 Critical
| Item | Status | Evidence / Gap |
|------|--------|----------------|
| Granular role permissions (refund/reports/edit) | 🟠 Stub | `permissions` table + grant/revoke (`production.py`) exist but **never enforced** on any route. |
| Session mgmt (refresh tokens, forced logout, timeout) | 🟡 **(Phase A)** | Refresh tokens added: login/register return a `refresh_token`; `POST /api/v1/auth/refresh` mints new access tokens; access/refresh tokens carry a `type` claim and are not interchangeable. No server-side revocation store yet (forced logout still relies on client discard). Tested in `tests/test_auth.py`. |
| Rate limiting | ✅ Implemented | `RateLimitMiddleware` (token bucket) in `middlewares/production.py` — **but in-memory only** (won't scale across replicas); confirm it's added in `main.py`. |
| Input validation/sanitization | 🟡 Partial | Pydantic + max-body middleware; no business-rule validation (price>0, etc.). |
| CORS lockdown | ✅ **(Phase A)** | New `core/cors.py::get_cors_config()` drives `main.py`: `ALLOWED_ORIGINS` (env) pins exact origins with credentials; dev falls back to wildcard **without** credentials; prod with no list **fails closed** to localhost. Tested in `tests/test_cors.py`. |
| DB migrations (Alembic) | 🟡 **(Phase A)** | `alembic/env.py` now resolves the DB URL from app settings (async-normalized) and supports offline + online modes; `alembic upgrade head` applies the existing revision chain to a fresh DB (verified). Runtime `create_all` still used for dev convenience. |
| Transaction atomicity | ✅ **(Phase A)** | POS sale + inventory now atomic — see §3. |
| Data backup/recovery | 🔴 Missing | None. |
| Audit trail completeness | 🟠 Stub | `audit_logs` is a CRUD table; **not written automatically** on mutations. |
| ZATCA full compliance | 🔴 Missing | See §4. |

### 🟠 Important
| Item | Status | Evidence / Gap |
|------|--------|----------------|
| Error tracking (Sentry) | 🔴 Missing | No Sentry. |
| Health checks | ✅ Implemented | `/health`, `/database/health`, `/api/v1/production/health/detailed`. |
| Structured logging | ✅ Implemented | JSON formatter + correlation IDs (`middlewares/production.py`); **local files only**, no aggregation. |
| Performance monitoring | 🟡 Partial | In-memory p95/latency metrics (`production.py`); lost on restart. |
| PDF receipt/invoice export | 🟡 Partial | `PDFInvoiceService` returns **HTML only** (needs a renderer); CSV export exists (`features.py:636`). |
| Email notifications | 🟡 **(Phase A)** | `EmailService` now reachable via `POST /api/v1/integrations/email/send` (still stub-logs until SMTP configured). |
| Low-stock alerts | 🟡 Partial | On-demand `/products/low-stock` + `/inventory/alerts` exist (`features.py`); **no automated push/email**. |
| Supplier & purchase orders | 🟠 CRUD-only | Tables/CRUD only; no PO workflow/receiving. |
| Shift/cash drawer | 🟡 Partial | `routers/shifts.py` open/close CRUD; no cash-difference calc/validation. |
| Payment method breakdown | 🔴 Missing | Single string; no per-method amounts. |
| Multi-branch | 🟡 Partial | `branches` + `branch_id` fields; branch isolation not consistently enforced in queries. |
| User profile / **change password** | ✅ **(Phase A)** | `POST /api/v1/users/change-password` (verifies current password, rejects no-op/wrong) added in `routers/user.py` + `services/user.py`; frontend `changePassword()` wrapper in `lib/api.ts`. Tested in `tests/test_auth.py`. |
| Bulk import/export | ✅ **(Phase A)** | `BulkImportService` wired via `POST /api/v1/integrations/bulk-import/products` — validates the CSV **and inserts** valid rows for the client. Tested in `tests/test_integrations.py`. (Customer import still validate-only.) |
| Global search & filtering | ✅ **(Phase A)** | `SearchService.global_search` wired via `GET /api/v1/integrations/search?q=` (user-scoped). Tested in `tests/test_integrations.py`. |
| Server-side pagination | ✅ Implemented (backend) | All entity lists take `skip`/`limit`; **frontend mostly requests large `limit` (100–2000) and renders all** — effectively unpaginated UX. |

### 🟡 Nice-to-have
| Item | Status |
|------|--------|
| Offline POS (SW/IndexedDB) | 🔴 Missing |
| Loyalty/rewards | 🟠 CRUD-only (no accrual/redemption logic) |
| Customer-facing display | 🟡 Partial (`CustomerDisplay.tsx` exists) |
| Receipt template customization | 🟠 CRUD-only (no render engine) |
| SAR-only currency | 🟡 Partial (15% VAT/SAR assumptions hardcoded, not configurable) |
| Thermal printer (WebUSB/BT) | 🔴 Missing |
| Mobile-responsive / tablet POS | 🟡 Partial |
| Per-agent API rate plans | 🔴 Missing |
| White-label mobile app (RN/Flutter) | 🔴 Missing |
| Advanced analytics/forecasting | 🔴 Missing |
| Webhook system | 🟡 **(Phase A)** — `WebhookDispatcher` now reachable via `POST /api/v1/integrations/webhooks/dispatch` (HMAC-signed; stub delivery until an HTTP client is configured) |

---

## 7. Cross-cutting architectural findings

1. ~~**Orphaned service code**~~ — **(Phase A)** Stripe, webhooks, email, bulk-import and search are now wired (`routers/payment.py`, `routers/integrations.py`). ZATCA XML/reporting remains orphaned (Phase B).
2. ~~**White-labeling doesn't render** (AG-04)~~ — **(Phase A)** branding now applied at runtime via `BrandingContext`.
3. **No real auth lifecycle** — **(Phase A, partial)** refresh tokens, `is_active` enforcement, and change-password are done; **permissions still unenforced** and there is no token-revocation store.
4. **Data-integrity risks** — **(Phase A, partial)** sale/inventory now atomic and Alembic is functional; backups and full audit-log auto-writing still missing.
5. **ZATCA is a façade** — QR/sequencing only; placeholder stamp; no onboarding/reporting.
6. **No mobile / offline** — an entire SRS pillar (§2.3, §3.4 POS-05) is absent.

---

## 8. Recommended remediation order

Aligns with the SRS author's "top 5" and adds the integrity/white-label blockers:

**Phase A — make the core honest & safe (1–2 wks) — ✅ DONE (2026-06-02)**
1. ✅ Make POS sale + inventory deduction **atomic** (single backend endpoint/transaction).
2. ✅ **Wire what exists**: Stripe (`routers/payment.py`), webhook dispatch + email + bulk-import + search (`routers/integrations.py`). *(Real SMTP/HTTP delivery still pending — services remain in stub/log mode until credentials configured.)*
3. ✅ **Apply agent branding** at runtime (CSS variables + logo) — fulfills white-label promise (AG-04).
4. ✅ Auth lifecycle: **change-password**, enforce `is_active`, refresh tokens. *(Token revocation store still pending.)*
5. ✅ Lock down **CORS**; **Alembic** env wired and verified (`upgrade head` applies the chain).

**Phase B — ZATCA Phase-2 (legal, 2–3 wks)** — official Fatoora SDK: CSR/onboarding, real cryptographic stamp/CSID, cert storage (encrypted), invoice reporting/clearance job, sandbox toggle, 6-yr retention.

**Phase C — required product features (2–4 wks)** — master agent-create (MA-01) + slot refill (MA-04) + global tax (MA-05); PDF invoices; email receipts (POS-04); payment breakdown; automated low-stock alerts; per-client feature enforcement; auto-write audit log; frontend pagination.

**Phase D — Arabic-output rule & polish** — force receipts **and** quotations to Arabic regardless of UI language; add a **quotation** feature (missing entirely); Arabic-Indic digit formatter; agent-default language.

**Phase E — mobile/offline & nice-to-haves** — RN/Flutter app, offline sync, thermal printing, loyalty accrual, analytics, error tracking (Sentry), log aggregation.

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
Token-revocation store; per-agent Stripe credentials; real SMTP/HTTP delivery; permission enforcement; auto-written audit log; Alembic as the *sole* schema source (runtime `create_all` still on). ZATCA real cryptographic stamp/onboarding/reporting remains **Phase B** (legal blocker).
