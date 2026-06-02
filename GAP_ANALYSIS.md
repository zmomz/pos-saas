# Deep Gap Analysis — POS System vs. SRS

**Date:** 2026-06-02
**Method:** Code-level audit of `backend/` and `frontend/` against every SRS requirement ID plus the production-readiness checklist. Each item is rated:

- **IMPLEMENTED** — works end to end.
- **PARTIAL** — works in part; meaningful pieces missing.
- **FAÇADE** — code/tables exist and look done, but the feature does not actually function (stub, never wired, never invoked).
- **MISSING** — not present.

> **Headline:** The backend is far more built-out than it looks, and the ZATCA cryptography is genuinely real (ECDSA secp256k1, real Fatoora HTTP client, hash chaining). But three structural defects undercut the product: **(1) clients are never given login accounts (CL-01), (2) the everyday POS sale is NOT cryptographically signed — it emits an unsigned TLV QR that the frontend can't even display, and (3) a large amount of backend capability is silently un-wired** (rate-limit & validation middleware not registered, permissions never checked, webhooks never fired, email/SMS/PDF are stubs). The system demos well but is not production-ready or fully ZATCA-compliant on the real sale path.

---

## 1. Critical defects (fix before any production use)

> **Phase 1 update (resolved & tested):** **C-1** clients now get a real login account (own `user_id`, generated temp password, force-reset flag) — `tenant.py::create_client_for_agent`. **C-2** suspension now targets the merchant (proven by test). **MA-02** slot deduction is now an atomic guarded `UPDATE` (409 when full). **C-5** all 24 `/all` triad routes are gated behind `get_admin_user` (master). **C-6** the generic `transactions` triad rejects create/update/delete (403) — sales only via the POS path. Regression coverage: `backend/tests/test_phase1_identity.py`. Still open from the original Tier-0 list: **C-3/C-4** (ZATCA on the sale path + QR rendering) → Phase 2.

| # | Defect | Evidence | Impact |
|---|--------|----------|--------|
| C-1 | **Clients get no login account.** `create_client_for_agent` never creates a `User`, generates no password, sends no email; it stamps `Clients.user_id = agent's own id`. | `tenant.py:485-554` (esp. `:511`) | The merchant can never log in. Breaks CL-01 and the entire "client uses the POS" premise. Cascades into C-2 and tenant-isolation. |
| C-2 | **Suspension targets the wrong account.** `is_active` enforcement matches `Clients.user_id`, which is the agent's id (per C-1). | `dependencies/auth.py:30-49`; `tenant.py:557-586` | Suspending a client would lock the agent (and all their clients), not the merchant. CL-05 effectively broken. |
| C-3 | **Everyday POS sale is not cryptographically signed.** `create_transaction` calls only `generate_zatca_tlv` (unsigned TLV); it never calls `sign_invoice`, never writes `zatca_documents`. Real ECDSA signing exists but is a separate, manually-invoked endpoint. | `pos.py:311` (no `sign_invoice`/`zatca_documents` references anywhere in `pos.py`); signing lives at `zatca.py:268-346` | Real sales produce **non-compliant** invoices (no cryptographic stamp, not reported/cleared to Fatoora). ZATCA Phase 2 is not met on the path that matters. |
| C-4 | **Receipt QR never renders.** Backend returns `zatca_qr` (a TLV **string**); frontend reads `zatca_qr_base64` and renders it as a PNG `data:image/png;base64,...`. Field name **and** format mismatch. | backend `pos.py:397`; frontend `POSTerminal.tsx:256, 462, 468` | The QR code — a ZATCA hard requirement (ZA-03/POS-03) — is never shown on the receipt; always falls to the text error fallback. |
| C-5 | **Unauthenticated `/all` routes leak every tenant's data.** Every generic CRUD triad exposes `GET /api/v1/entities/<entity>/all` with no auth and no user filter. | `clients.py:141-175`, `agents.py:147-181`, `packages.py`, `transactions.py`, `webhooks.py:135`, etc. | Anyone can read all clients, agents, packages, transactions across all tenants. Violates 5.2 row-level security and the "client cannot see other clients" constraint. The UI even depends on it (`api.ts` `queryAll`). |
| C-6 | **Generic transactions triad bypasses the atomic POS flow.** `routers/transactions.py` allows create/update/delete (and unauth `/all`) on transactions outside ZATCA and inventory logic. | `transactions.py` | Fiscal records can be inserted/mutated/deleted outside the sequenced, hashed, inventory-aware sale path — undermines ZA-04 tamper-proofing. |

---

## 2. SRS requirement-by-requirement

### 3.1 Agent Management (Master Dashboard)
| ID | Status | Notes |
|----|--------|-------|
| MA-01 create agent (name/email/phone/package) | **PARTIAL** | Backend creates a `User` + `Agents` row and returns a one-time `temp_password` (`tenant.py:267-337`), and the agent **can** log in. But the UI discards `temp_password` (`MasterDashboard.tsx:76-96`), so the credential is lost. Packages are arbitrary integers, not a 10/50/100 enum. |
| MA-02 deduct one slot on client create | **PARTIAL** | Works, but non-atomic read-modify-write (`tenant.py:504-528`) — TOCTOU race oversells slots under Postgres concurrency. |
| MA-03 real-time used vs remaining | **FAÇADE** | Backend `AgentStatsResponse` sends `used_slots` + `package_type` only; UI renders `{used_slots}/{client_slots}` where `client_slots` is never sent → shows `used/undefined` (`tenant.py:45-54` vs `MasterDashboard.tsx:326`). |
| MA-04 add slots (refill) | **PARTIAL** | Backend `POST /tenant/master/agents/{id}/slots` + `addAgentSlots` wrapper exist, but no UI calls it (`MasterDashboard.tsx` never imports it). |
| MA-05 global tax, agents can't override | **PARTIAL** | Enforcement is real: `get_effective_tax_rate` gives global precedence and POS uses it (`system_settings.py:61-74`, `pos.py:263`). Backend `PUT /tenant/master/tax-rate` exists but there is **no master UI** to set it. |

### 3.2 White-Labeling & Feature Toggles (Agent Dashboard)
| ID | Status | Notes |
|----|--------|-------|
| AG-01 logo upload (PNG/SVG → bucket) | **FAÇADE** | No upload. `BrandingEditor.tsx:149-156` is a plain "Logo URL" text field; stored as a string. No file upload, no bucket, no format validation. |
| AG-02 colors / radius / font | **IMPLEMENTED** | Pickers in `BrandingEditor.tsx:159-256`, persisted to the `Agents` row (`features.py:452-486`). |
| AG-03 per-client feature toggle | **PARTIAL** | Backend upsert + `require_feature` 403 enforcement are real (`tenant.py:589-638`, `dependencies/features.py:49-68`), but **no UI** calls it and **no route** is actually gated with `require_feature`. Mechanism built, never attached. |
| AG-04 client UI loads agent theme dynamically | **IMPLEMENTED** | `BrandingContext.tsx` fetches `/tenant/client/branding` for the owning agent and writes CSS vars (`--primary`, `--radius`, …) + body font (`:111-130, 145-166`). Genuinely works for colors/font/radius. (Logo URL only.) |

### 3.3 Client Onboarding & Subscription
| ID | Status | Notes |
|----|--------|-------|
| CL-01 create client → email + temp password | **MISSING / BROKEN** | See C-1. No account, no password, no email (no SMTP anywhere). |
| CL-02 client picks language on first login | **PARTIAL** | Generic language `Select` available at login (`Index.tsx:66-77`); no guided first-login step. |
| CL-03 agent sets subscription fee | **PARTIAL** | Backend stores `subscription_fee` (`tenant.py:91,517`); the create-client dialog never sends it (`AgentDashboard.tsx:206-224`) so it defaults to 0. Shown read-only in the table. |
| CL-04 client pays via agent gateway | **MISSING** | No subscription/billing payment flow for clients; client dashboard shows no plan/billing. Stripe exists only as generic `routers/payment.py`, not wired to subscriptions. |
| CL-05 agent suspends client | **PARTIAL/BROKEN** | Toggle + enforcement exist but target the wrong account (C-2). |

### 3.4 POS Terminal
| ID | Status | Notes |
|----|--------|-------|
| POS-01 cart (items/qty/discount/tax) | **PARTIAL** | Cart + discount apply + 15% VAT client-side; backend recomputes authoritatively. But the frontend `createTransaction` sends only `{items, payment_method}` — **applied discount is never persisted** (`POSTerminal.tsx:247`). |
| POS-02 multiple payment methods + split | **PARTIAL** | Backend fully supports split tenders + `payment_breakdown` (`pos.py:40-44,267-284`). Frontend offers single-select only; loyalty-as-tender not selectable. Split/loyalty reachable only by raw API. |
| POS-03 ZATCA invoice + QR (thermal/A4) | **PARTIAL/BROKEN** | Arabic RTL HTML invoice exists; ESC/POS path exists; **but** QR doesn't render (C-4) and the printed/displayed invoice carries an unsigned QR (C-3). HTML is not converted to PDF (no PDF lib). |
| POS-04 send invoice email/SMS | **FAÇADE** | Email endpoint exists but `EmailService.send_email` is a log-only stub; no SMS at all (`production.py:600-628`). No UI button. |
| POS-05 offline mode | **PARTIAL/FAÇADE** | Service worker + IndexedDB queue + flush-on-online are real, but `process_offline_queue` inserts a row only — **no inventory deduction, no ZATCA QR/hash, no counter, no loyalty**, and stores `client_id=NULL` (queue never sends it) so synced sales are orphaned (`production.py:1009-1072`, `offlineQueue.ts:54-71`). |
| POS-06 barcode (camera) / name search | **PARTIAL** | Manual SKU/keyboard-wedge match against loaded products only; **no camera** (`BarcodeDetector`/`getUserMedia` absent); no name-search field on POS. |
| POS-07 return/refund + ZATCA credit note | **FAÇADE** | "Refund" is a new sale with negative prices and `product_id:0` (so stock isn't returned); no credit-note document type, no original-invoice reference (`POSTerminal.tsx:331-366`; no refund/credit-note route in `pos.py`). |

### 3.5 ZATCA Compliance
| ID | Status | Notes |
|----|--------|-------|
| ZA-01 onboarding (CSR → CSID, store encrypted) | **IMPLEMENTED** | Real secp256k1 keypair + PKCS#10 CSR, AES-256-GCM-encrypted private key, compliance + production CSID exchange (`services/zatca.py:129-211`, `zatca.py:164-262`). |
| ZA-02 mandatory fields + cryptographic stamp | **IMPLEMENTED (but off the sale path)** | UBL 2.1 XML + SHA-256 hash + real ECDSA stamp (`zatca.py:268-346`, `production.py:199-359`). **Caveat C-3:** not invoked by normal sales. |
| ZA-03 QR via TLV (base64) | **PARTIAL** | TLV byte structure is correct (`pos.py:98-132`) but unsigned (no stamp tag) and **never displayed** (C-4). |
| ZA-04 per-client sequence + hash chain | **IMPLEMENTED** | Atomic counter per client (`pos.py:286-296`), PIH chaining on signed docs (`zatca.py:309-334`, tests confirm). Undermined for unsigned sales (C-3) and by the generic transactions triad (C-6). |
| ZA-05 6-year retention | **IMPLEMENTED** | `retention_until` computed at signing (`zatca.py:127-129`); no auto-purge (acceptable). |
| ZA-06 sandbox/simulation | **IMPLEMENTED** | sandbox/simulation/production environments with per-env base URLs + CSR templates (`services/zatca.py:63-112`); fails closed (503) when unconfigured. |
| Phase 2 Fatoora reporting/clearance | **IMPLEMENTED (but off the sale path)** | Real async httpx client to `/compliance`, `/production/csids`, `/invoices/clearance|reporting/single` (`services/zatca.py:284-375`). Not triggered automatically after a sale. |
| Receipts/quotations always Arabic | **IMPLEMENTED** | Invoice/quotation HTML forced `dir="rtl" lang="ar"` with Arabic-Indic numerals regardless of UI language (`production.py:369-594`; `POSTerminal.tsx:392-406`). |

### 3.6 Multi-Language
| ID | Status | Notes |
|----|--------|-------|
| L10N-01 ar/en/hi/ur locale files | **IMPLEMENTED** | All four objects in `i18n.ts` have ~119 keys at full parity with real translations. Caveat: many pages call keys not in the map and rely on inline `|| 'English'` fallbacks, so some strings render English-only in ar/hi/ur. |
| L10N-02 RTL for Arabic AND Urdu | **IMPLEMENTED** | `isRTL()` covers `ar` + `ur`; `document.documentElement.dir` set on change/mount (`i18n.ts:488-506`). |
| L10N-03 Arabic-Indic digits | **PARTIAL** | `format.ts` implements it but is imported in only 2 files; dashboards hardcode Western digits and a `$` sign (should be SAR). |
| L10N-04 date/time locale (Gregorian req.) | **MISSING** | No date helper; bare `toLocaleString()` with no locale; no Hijri option. |
| L10N-05 agent default lang, client override | **IMPLEMENTED** | `applyDefaultLanguage` applies agent default only if client hasn't chosen (`BrandingContext.tsx:27-35`). |
| Instant app-wide toggle | **PARTIAL** | `useLanguage()` uses component-local `useState` with **no shared LanguageContext** — sibling components can lag until remount; only `dir` flips globally. |

### Mobile App (2.3 / 4.1)
**MISSING.** No React Native/Flutter/Expo code anywhere — web SPA only. Offline (POS-05) is the web service-worker approximation described above, not the spec's mobile+SQLite offline.

---

## 3. Production-readiness checklist

### 🔴 Critical
| Item | Status | Notes |
|------|--------|-------|
| Granular role permissions | **FAÇADE** | Stored + queryable (`permissions.py`, `production.py:128-261`) but **no endpoint enforces them**; no `require_permission` call sites; **no refund endpoint** despite `pos.refund` key. |
| Session mgmt (refresh/forced logout/timeout) | **PARTIAL** | Bcrypt ✅ + refresh tokens ✅ (`auth.py:78-102`). Logout is a no-op; no revocation/blocklist; `/session/refresh` is a self-admitted façade (`production.py:1105-1119`). |
| Rate limiting | **FAÇADE** | `RateLimitMiddleware` exists but is **never registered** in `main.py:96-100`. Inert. |
| Input validation/sanitization | **PARTIAL** | Pydantic only; size-limit middleware exists but **not registered**; CSV cells inserted raw. |
| CORS lockdown | **IMPLEMENTED** | Env-aware, fails closed to localhost in prod (`core/cors.py:33-63`). |
| DB migrations (Alembic) | **PARTIAL** | 6 real chained revisions exist, but boot still uses `create_all` (`main.py:70-72`) — migrations aren't run. Two parallel schema mechanisms. |
| Transaction atomicity | **IMPLEMENTED** | Sale + counter + inventory + loyalty share one `AsyncSession`, single commit, rollback on oversell (`pos.py:287-378`; tests confirm). **But** offline-sync path bypasses it (POS-05). |
| Backup & recovery | **MISSING** | No scripts/snapshots/tooling. |
| Audit trail | **IMPLEMENTED (coarse)** | Middleware logs every authed 2xx mutation on `/api/v1` (`middlewares/audit.py`), but records only `METHOD path` + status + IP — no before/after, no entity id, no reads/failures. |
| ZATCA full (reporting + CSID + sequential) | **PARTIAL** | Cryptography real but off the sale path (C-3); sequential/hash real for signed docs only. |

### 🟠 Important
| Item | Status | Notes |
|------|--------|-------|
| Error tracking (Sentry) | **PARTIAL/ MISSING** | Backend gated init exists but `sentry-sdk` not in requirements (can't activate); frontend has none. |
| Health checks | **IMPLEMENTED** | `/health` + DB-touching `/production/health/detailed`. |
| Structured logging / aggregation | **MISSING** | Local logging only. |
| Performance monitoring | **MISSING** | No APM/slow-query tracking. |
| PDF receipt/invoice export | **PARTIAL** | Arabic HTML only; no PDF library; no frontend consumer/print. |
| Email notifications | **FAÇADE** | Log-only stub; wired into low-stock/receipt but never sends. |
| Low-stock alerts | **PARTIAL** | Detection real; delivery rides the email stub; threshold hardcoded (10). |
| Supplier & purchase orders | **MISSING** | Empty CRUD triads; received PO never increments inventory. |
| Shift/cash drawer | **PARTIAL** | Open/close + reconciliation math exist, but **sales never update the open shift** (expected cash = opening float forever), and `shifts/history` endpoint the UI calls **doesn't exist**. |
| Payment-method breakdown | **IMPLEMENTED (backend) / unused** | Column populated; UI never produces split data. |
| Multi-branch | **MISSING** | `branch_id` not on transactions or inventory; branch inventory view reports identical user-wide totals per branch (façade). |
| User profile & settings | **IMPLEMENTED** | `routers/user.py` profile + change password; `UserProfile.tsx`. |
| Bulk import/export | **IMPLEMENTED** | Real CSV import/export persists rows (`production.py:778-924`). |
| Search & filtering | **IMPLEMENTED** | `SearchService.global_search` ILIKE across products/customers/transactions, user-scoped. |
| Pagination | **PARTIAL** | Real offset/limit on hand-written lists; triads cap at 2000 **and** expose unauth `/all`. |

### 🟡 Nice-to-have
| Item | Status |
|------|--------|
| Offline POS (web) | **PARTIAL** (sync incomplete — see POS-05) |
| Loyalty/rewards | **PARTIAL** (backend in atomic checkout; UI never sends customer/redeem) |
| Customer-facing display | **FAÇADE** (`CustomerDisplay` polls a localStorage key nothing ever writes) |
| Receipt template customization | **PARTIAL** (`receipt_templates` CRUD; limited wiring) |
| SAR-only currency | **PARTIAL** (dashboards show `$`/USD) |
| Thermal printer (ESC/POS) | **PARTIAL** (ASCII labels; QR embedded) |
| Mobile-responsive POS | not separately verified |
| API rate plans per package | **MISSING** (rate limiter inert) |
| White-label mobile app | **MISSING** |
| Advanced analytics | **MISSING** |
| Webhook system | **FAÇADE** (HMAC computed, but never HTTP-sent; never fired on domain events) |
| API usage metering | **FAÇADE** (table never auto-written; stats over empty table) |

---

## 4. Recommended fix order

**Tier 0 — makes the product actually function & compliant**
1. **C-1/C-2:** create a real `User` per client on provisioning (own credentials, temp password surfaced/emailed), set `Clients.user_id` to that user; fix suspension to match the merchant.
2. **C-3:** call the existing `sign_invoice` + Fatoora reporting from `create_transaction` (or a post-commit job) so real sales are signed & cleared; embed the signed QR.
3. **C-4:** align the QR contract — return the QR as the frontend expects (render TLV→PNG client-side, or return a base64 PNG) and unify the field name.
4. **C-5/C-6:** remove or authenticate the `/all` routes and lock down the generic `transactions` triad (no external create/update/delete of fiscal rows).

**Tier 1 — production hardening**
5. Register the existing `RateLimitMiddleware` + `RequestValidationMiddleware` in `main.py` (code already written).
6. Run Alembic migrations on boot instead of `create_all`.
7. Enforce permissions (`require_permission`) on refund/reports/edit; add a real refund + ZATCA credit-note route.
8. Replace email/webhook/API-usage stubs with real implementations and fire webhooks on domain events.
9. Fix offline-sync to route through the atomic sale path (inventory, counter, signing, loyalty, `client_id`).
10. Add `sentry-sdk` (backend) + frontend Sentry; add backups.

**Tier 2 — feature completeness**
11. Wire the frontend to the backend it already has: persist discounts, split payments, loyalty (customer + redeem), shift sales accumulation, `shifts/history`.
12. Logo file upload to a bucket; master UI for tax-rate + slot refill + temp-password display; per-client feature-toggle UI.
13. Thread `branch_id` through transactions + inventory for real multi-branch.
14. PDF generation (add a renderer); date/locale formatting + SAR currency everywhere; shared LanguageContext for instant toggling.

---

## 5. What genuinely works well (don't rebuild)
- Real ZATCA cryptography: ECDSA secp256k1 stamp, AES-256-GCM key encryption, PIH hash chaining, real Fatoora httpx client (just not on the sale path).
- Atomic online POS sale (sale + counter + inventory + loyalty, one commit, rollback on oversell).
- Agent→client dynamic theming via CSS variables (AG-02/AG-04).
- Global tax enforcement with agent-override prevention (MA-05 backend).
- Full 4-language locale parity, RTL for ar+ur, env-aware fail-closed CORS, real Alembic revisions, real bulk CSV + global search, refresh tokens, coarse-but-real audit middleware.
