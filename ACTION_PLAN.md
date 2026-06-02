# Action Plan — Closing the SRS Gaps (Front + Back + Tests)

**Source:** `GAP_ANALYSIS.md` (2026-06-02). Every gap there is mapped to a task here.
**Principle:** phases are ordered by **dependency**, not by SRS section. Each phase ships backend + frontend + tests together and is independently mergeable/releasable. A phase is "done" only when its acceptance tests pass on both ends.

**Legend:** `[B]` backend · `[F]` frontend · `[T]` tests · `(gap-id)` traces to GAP_ANALYSIS.

---

> **Progress log**
> - **Phase 0 (backend): DONE** — `backend/pytest.ini` (`asyncio_mode=auto`), session-scoped in-memory-style SQLite fixture + auth/role factories in `tests/conftest.py`; 63 baseline tests green. Frontend Vitest/Playwright + CI workflow still **TODO**.
> - **Phase 1 (backend): DONE & TESTED** — C-1, C-2, MA-02, C-5, C-6 closed; first-login force-reset wired; provisioning email helper with dev fallback. New suite `tests/test_phase1_identity.py` (8 tests); **71 backend tests green**. Frontend: temp-password modals (master+agent), first-login reset screen, typed create responses — `pnpm build` + `eslint` clean. Deep `get_tenant_scope` refactor **deferred** (user_id scoping + gated `/all` already isolate tenants); real SMTP wiring is Phase 3; Playwright E2E pending the Phase 0 frontend harness.
> - **Phase 3 (backend + frontend): DONE & TESTED** — production-hardening security backbone landed. **Session revocation:** every JWT now carries a `jti`; `POST /auth/logout` blocklists it server-side (`models/revoked_tokens.py` + `services/token_revocation.py`), `get_current_user` and `/auth/refresh` reject revoked tokens — a logged-out token is dead before it expires (logout also revokes the supplied refresh token). **Permissions:** `dependencies/permissions.py::require_permission(key)` gates the refund route (`pos.refund`), grant-by-default / explicit-deny / master-bypass (mirrors `require_feature`); new `GET /auth/me/permissions` feeds the permission-aware UI. **Rate limiting:** `RateLimitMiddleware` registered (429 + `Retry-After`), live-toggled by `RATE_LIMIT_ENABLED` (off by default so dev/CI never throttles). **Input validation:** `RequestValidationMiddleware` registered (413 over `MAX_BODY_SIZE_MB`, default 10MB). **Webhooks:** `WebhookDispatcher.dispatch` rewritten to do real HMAC-SHA256-signed httpx POSTs with retry-on-5xx; `fire_event`/`fire_event_background` fire `sale.completed` + `refund.created` out-of-band from `pos.py` (best-effort, never blocks the sale). **Email:** `EmailService` now delegates to the real `core/email` transport (SMTP when configured, dev-log fallback) instead of the stub. New suite `tests/test_phase3_hardening.py` (12 tests) + 1 updated email-receipt test; **92 backend tests green**. Frontend: atomsClient response interceptor handles 401-after-revocation (clear token + redirect + toast) and 429 (toast); logout revokes the refresh token; `getMyPermissions`/`canUse` + permission-gated Refund UI in `POSTerminal`; global rate-limit/session-expired toasts in `App.tsx` — `vite build` + `eslint` clean. **Deferred** (documented in `RUN.md`, consistent with Phases 0–2): Alembic migrations-on-boot (still `create_all`), Twilio **SMS**, **API-usage metering** rows, audit before/after **diffs** + failed-auth logging, **frontend Sentry** wiring (package not installed; backend Sentry already config-gated), structured-JSON-logging activation, and the `[T-F]`/`[T-E2E]` Vitest/Playwright specs (await the Phase 0 frontend harness).
> - **Phase 2 (backend + frontend): DONE & TESTED** — C-3, C-4, POS-07, ZA-04 closed. Every POS sale is now ECDSA-signed on the real sale path, hash-chained (per-client PIH), stamped (TLV tags 1–8), archived to `zatca_documents`, and queued for Fatoora reporting — all atomic with the sale (`services/zatca_sale.py::sign_transaction`, wired into `routers/pos.py::create_transaction`). Signing self-provisions a per-client EGS key on first sale so no sale is ever silently unsigned; the manual `/zatca/invoices/{id}/sign` endpoint is now **idempotent** (returns the existing fiscal doc instead of corrupting the chain). The fiscal QR is the stamped TLV, rendered **server-side to a PNG** (`render_qr_png_base64`, `qrcode`+`Pillow`) and returned as `zatca_qr_base64` — the frontend renders it directly (C-4 field mismatch fixed). Refunds issue a real ZATCA **381 credit note** (`POST /pos/transactions/{id}/refund`): references the original invoice (`cac:BillingReference`), **restores inventory**, advances the chain, signs + reports — the negative-price fake refund is gone. Reporting (`report_document`) retries transient 5xx and **fails closed to "pending"** when the gateway/onboarding is unconfigured (never blocks a sale); runs out-of-band via `BackgroundTasks`. New `GET /zatca/integrity` (ZA-04) re-verifies the whole chain + every stamp. New suite `tests/test_phase2_zatca_sale.py` (9 tests) + 2 updated ZATCA tests; **80 backend tests green**. Frontend: `refundTransaction` wrapper + credit-note receipt, QR PNG now renders, invoice ZATCA-status line — `vite build` + `tsc` + `eslint` clean. **Deferred** (consistent with Phase 0/1): the `[T-F]`/`[T-E2E]` QR-render + sale→refund Playwright specs still wait on the Phase 0 frontend Vitest/Playwright harness; production-CSID key rotation and the `test_zatca_compliance.py` golden harness fold into Phase 3.

## Phase 0 — Test harness & CI baseline (1–2 days)

You cannot safely fix the rest without a regression net. There are backend tests under `backend/tests/` but no committed config, and **no frontend tests at all**.

- `[B]` Add `pytest.ini`/`pyproject` config: `asyncio_mode=auto`, test DB = in-memory SQLite per test (fixture), `httpx.AsyncClient` app fixture, auth-token + role fixtures (master/agent/client). Factory helpers to seed an agent and a *real* client login.
- `[B]` Coverage gate (`pytest --cov`, fail < 60% to start, ratchet up per phase).
- `[F]` Add **Vitest + React Testing Library + MSW** (mock API). Config `vitest.config.ts`, `setupTests.ts`, a `renderWithProviders` helper wrapping `AuthProvider` + `BrandingProvider` + Router + React Query.
- `[F]` Add Playwright for E2E (one smoke spec: login → dashboard renders) — reused by later phases.
- `[T]` CI workflow (`.github/workflows/ci.yml`): backend `pytest`, frontend `pnpm lint && pnpm test && pnpm build`, Playwright smoke. Block merge on red.

**Acceptance:** `pytest` green; `pnpm test` green; CI runs both on PR.

---

## Phase 1 — Identity & tenancy foundation (CRITICAL — unblocks everything)

Root cause first: **C-1** (clients have no login) cascades into C-2, isolation, suspension, and the branding chain. Do this before anything else.

### Backend
- `[B]` **(C-1)** In `tenant.py::create_client_for_agent`: create a real `User` (unique email, bcrypt temp password via `secrets.token_urlsafe`), set `Clients.user_id = new_user.id` (NOT the agent's id). Return one-time `temp_password` + force-reset-on-first-login flag. `tenant.py:485-554`.
- `[B]` **(C-2)** Now that `Clients.user_id` is the merchant, suspension enforcement in `dependencies/auth.py:30-49` correctly targets the merchant — add a test proving suspending client A blocks A and not the agent.
- `[B]` **(MA-02)** Make slot deduction atomic: `UPDATE agents SET used_slots = used_slots + 1 WHERE id=? AND used_slots < package_type` and check `rowcount`; 409 if no slot. Replace read-modify-write at `tenant.py:504-528`.
- `[B]` **(C-5)** Remove the unauthenticated `/all` route from the CRUD triad generator, OR gate it behind `get_admin_user` + master role. Audit every `routers/*.py` for `/all`. Replace UI dependence with authed `query`.
- `[B]` **(C-6)** Lock the generic `transactions` triad: disable external create/update/delete (sales only via `pos.py`); same for `zatca_documents`. Make them read-only/owner-scoped.
- `[B]` **(isolation)** Add a tenancy guard layer: clients resolve to their `client_id`, agents to their `agent_id`; service-layer filters use the **tenancy** scope, not just `user_id`. Add `get_tenant_scope(current_user)` helper and apply to products/customers/transactions/reports list+get+update+delete.
- `[B]` Email delivery for provisioning (real SMTP via `core/email.py`, configurable; falls back to returning temp password in dev). This replaces the email stub for the provisioning path (full stub replacement in Phase 3).

### Frontend
- `[F]` **(MA-01/C-1)** `MasterDashboard` create-agent and `AgentDashboard` create-client dialogs: capture and **display the returned temp password** once (copy-to-clipboard modal), with "email sent" confirmation. `MasterDashboard.tsx:76-96`, `AgentDashboard.tsx:59-72`.
- `[F]` First-login force-password-change screen (consumes the reset flag).
- `[F]` Replace `queryAll`/`/all` reliance (e.g. `getPackages`) with authenticated list calls. `api.ts`.

### Tests
- `[T-B]` Client provisioning creates a User that can log in; `temp_password` works; `Clients.user_id != agent.id`.
- `[T-B]` Suspend client → that client's token gets 403; agent + sibling clients unaffected.
- `[T-B]` Slot race: fire N concurrent client creates against a 1-slot agent → exactly 1 succeeds.
- `[T-B]` `/all` routes return 401/403 unauthenticated; cross-tenant read (client A requesting client B's product) returns 404/403.
- `[T-B]` Generic transactions create/delete is rejected.
- `[T-F]` Create-client flow shows temp password; first-login reset redirects correctly.
- `[T-E2E]` Master creates agent → agent logs in → agent creates client → **client logs in and lands on Client dashboard**.

**Acceptance:** a freshly provisioned client can log in; suspension works; no unauth data leak; slots can't oversell.

---

## Phase 2 — ZATCA compliance on the real sale path (LEGAL BLOCKER)

The cryptography is real but **off the sale path (C-3)**. Make every real sale signed, reported, and display a valid QR.

### Backend
- `[B]` **(C-3)** In `pos.py::create_transaction`, after the atomic commit, sign the invoice: call the existing `sign_invoice` (ECDSA) + build the **stamped** TLV (add the cryptographic-stamp + public-key tags 6–8) and persist to `zatca_documents`. Keep it in/just-after the sale transaction so a sign failure is visible (not silently unsigned). `pos.py:311`, `zatca.py:268-346`.
- `[B]` **(C-3 / Phase-2 reporting)** Add a background reporting job (FastAPI `BackgroundTasks` now, swappable to a real queue later): POST signed simplified invoices to Fatoora `/invoices/reporting/single`, standard to `/clearance/single`, within 24h, with retry + status column (`reported|cleared|failed`) on `zatca_documents`. Fail-closed to "pending" when gateway unconfigured (don't block the sale).
- `[B]` **(C-4)** Fix the QR contract: return a field the frontend renders. Either return `zatca_qr` as the raw TLV base64 **and** rename the frontend, or render server-side to a PNG. Recommended: keep TLV string, render to PNG **client-side** (smaller payload). Ensure the field name matches end to end. `pos.py:397`.
- `[B]` **(POS-07)** Real refund + **ZATCA credit note**: new endpoint `POST /pos/transactions/{id}/refund` that creates a credit-note document (UBL InvoiceTypeCode 381), references the original invoice, **restores inventory**, advances the hash chain, signs + reports. Remove the negative-price fake-refund hack.
- `[B]` **(ZA-04)** Assert sequential counter + PIH chaining run on the real sale path; add integrity check endpoint/test.

### Frontend
- `[F]` **(C-4)** Render the TLV QR to an actual QR image (e.g. `qrcode` lib) from the returned TLV string; remove the broken `data:image/png` assumption. `POSTerminal.tsx:256,462`.
- `[F]` **(POS-07)** Replace the negative-line refund UI with a "Refund / Credit Note" flow: select original transaction → confirm → shows credit-note number + QR.
- `[F]` Show invoice ZATCA status (pending/reported/cleared) on the receipt + transaction list.

### Tests
- `[T-B]` A normal POS sale produces a `zatca_documents` row with a valid ECDSA stamp; `verify_stamp` passes; TLV contains tags 1–8.
- `[T-B]` Hash chain: 2nd sale's `previous_hash` == 1st sale's `invoice_hash`.
- `[T-B]` Reporting job posts to a mocked Fatoora and records status; retries on 5xx.
- `[T-B]` Refund creates a 381 credit note referencing the original, restores stock, signs + chains.
- `[T-F]` QR renders as an image from a TLV string (snapshot/img present).
- `[T-E2E]` Sale → receipt shows QR + invoice number; refund → credit note shown.

**Acceptance:** every real sale is signed, sequenced, chained, QR-rendered, and queued for Fatoora reporting; refunds issue compliant credit notes.

---

## Phase 3 — Production hardening (security & ops)

Mostly "wire what already exists" + replace stubs.

### Backend
- `[B]` **(rate limiting)** Register the existing `RateLimitMiddleware` in `main.py:96-100`; configurable limits per route class; per-agent plan limits tie-in (stub the plan lookup).
- `[B]` **(input validation)** Register `RequestValidationMiddleware` (body-size cap); add explicit sanitization on CSV import cells; tighten Pydantic constraints on money/qty fields.
- `[B]` **(migrations)** Run Alembic `upgrade head` on boot; drop `create_all` for prod (keep for test fixture). Add a CI check that models == latest migration (autogenerate diff is empty). `main.py:70-72`.
- `[B]` **(permissions)** Implement `require_permission(key)` dependency that reads granted permissions; apply to refund (`pos.refund`), reports (`reports.view`), product edit (`products.edit`), etc. `permissions.py`, `production.py:128-261`.
- `[B]` **(session)** Token revocation/forced logout: server-side blocklist (jti in a `revoked_tokens` table or Redis); `/auth/logout` revokes; `/auth/refresh` checks blocklist. Configurable idle timeout.
- `[B]` **(email)** Replace `EmailService` stub with real SMTP/SendGrid (`production.py:600-628`); wire receipts (POS-04) + alerts.
- `[B]` **(webhooks)** Replace `WebhookDispatcher` stub with real httpx POST + retry; **fire on domain events** (sale.completed, refund.created, stock.low) from `pos.py`. `production.py:657-703`.
- `[B]` **(SMS)** Add an SMS provider (Twilio) for POS-04 invoice send; feature-gated.
- `[B]` **(API usage metering)** Add metering middleware that writes `Api_usage` rows; make `/api-usage/stats` reflect real data.
- `[B]` **(audit completeness)** Extend `middlewares/audit.py` to capture entity id + before/after diff for mutations and log failed-auth attempts.
- `[B]` **(observability)** Add `sentry-sdk` to `requirements.txt`; structured JSON logging; ensure `/health` + detailed readiness are monitored.
- `[B]` **(backups)** Add a documented backup job (pg_dump cron / managed snapshots) + restore runbook in `RUN.md`.

### Frontend
- `[F]` **(Sentry)** Add `@sentry/react` with router + error-boundary integration.
- `[F]` Handle 429 (rate-limited) and 401-after-revocation gracefully (toast + redirect to login).
- `[F]` Permission-aware UI: hide/disable refund, reports, product-edit when the staff member lacks the permission (consume a `/me/permissions` endpoint).

### Tests
- `[T-B]` Rate limit returns 429 after N requests; validation rejects oversized body.
- `[T-B]` Migrations: fresh DB `upgrade head` builds schema; autogenerate diff empty.
- `[T-B]` Permission denied → 403 for refund without `pos.refund`; granted → 200.
- `[T-B]` Logout revokes token (subsequent call 401); refresh after revoke fails.
- `[T-B]` Webhook fires on sale with valid HMAC (mock receiver); email/SMS send invoked (mock transport).
- `[T-F]` UI hides refund button without permission; 429/401 handled.

**Acceptance:** no inert security middleware; permissions enforced; stubs replaced; logout actually invalidates; errors tracked.

---

## Phase 4 — POS feature completeness (wire frontend ↔ backend)

The backend already supports most of this; the frontend drops data at `createTransaction`.

### Frontend
- `[F]` **(POS-01)** Persist applied discount: send `discount`/order-discount in `createTransaction`. `POSTerminal.tsx:247`, `api.ts:89-101`.
- `[F]` **(POS-02)** Split-payment UI: multiple `PaymentEntry` rows (cash/card/bank/loyalty), validated to total; loyalty-as-tender. Send `payments[]`.
- `[F]` **(loyalty)** Customer selector + redeem-points control at checkout; send `customer_id` + `redeem_points`.
- `[F]` **(POS-06)** Camera barcode scanning (`BarcodeDetector` w/ fallback lib) + product **name search** field.
- `[F]` **(POS-05)** Fix offline queue to include `client_id` and route synced sales through the full sale logic.
- `[F]` **(shifts)** Shift report UI consumes a real history endpoint; show sales accumulation.
- `[F]` **(customer display)** Make POS write the `pos-customer-display` localStorage key the `CustomerDisplay` page reads (or use BroadcastChannel). `CustomerDisplay.tsx:33-59`.

### Backend
- `[B]` **(POS-05)** `process_offline_queue` must route through the same atomic path: inventory deduction, counter, signing, loyalty, and set `client_id`. `production.py:1009-1072`.
- `[B]` **(shifts)** POS sale updates the open shift's `total_sales`/`total_transactions`; add the missing `GET /production/shifts/history` endpoint. `pos.py`, `production.py`.
- `[B]` **(low stock)** Now that email is real (Phase 3), verify post-sale low-stock alerts deliver; make threshold per-product/config.

### Tests
- `[T-B]` Sale with split payments persists `payment_breakdown` summing to total; loyalty redeem deducts points atomically; rollback if balance insufficient.
- `[T-B]` Offline sync deducts inventory, signs, sets client_id, dedups by offline_id.
- `[T-B]` Shift accumulates sales; history returns closed shifts; reconciliation math correct.
- `[T-F]` Discount + split payment + loyalty redeem sent in checkout payload (MSW assertion).
- `[T-F]` Barcode scan adds product; name search filters; customer display updates on add-to-cart.
- `[T-E2E]` Full sale with discount + split payment + loyalty redeem + QR + email.

**Acceptance:** what the cashier sees (discount, split pay, loyalty) is what gets persisted and reported; offline sales are fiscally complete.

---

## Phase 5 — Admin & white-label UI completeness

Backends exist; surface them and finish onboarding/subscription.

### Backend
- `[B]` **(AG-01)** Logo upload endpoint → cloud bucket (S3/compatible via `routers/storage.py`), MIME/size validation, returns URL; store on agent.
- `[B]` **(CL-03/CL-04)** Subscription: store fee + billing cycle; client subscription status/next-billing/payment-history endpoints; client pay-subscription via agent's gateway (`services/payment.py` Stripe Connect / agent creds). Suspend on non-payment hook (CL-05 already enforced).
- `[B]` **(AG-03)** Actually gate at least the toggleable features (inventory, discounts, loyalty, ZATCA) with `require_feature(...)` so per-client toggles take effect. `dependencies/features.py`.

### Frontend
- `[F]` **(AG-01)** Logo file-upload widget (drag-drop, preview) replacing the URL text field. `BrandingEditor.tsx:149-156`.
- `[F]` **(MA-03)** Fix slot display to read the right field (`used_slots`/`package_type`) → `used/total`. `MasterDashboard.tsx:326`.
- `[F]` **(MA-04)** Master "Add slots / refill" button calling `addAgentSlots`.
- `[F]` **(MA-05)** Master tax-rate settings UI calling `PUT /tenant/master/tax-rate`.
- `[F]` **(CL-03)** Subscription-fee input in the create-client dialog. `AgentDashboard.tsx:206-224`.
- `[F]` **(CL-04 / client dashboard)** Subscription panel: plan name, next billing date, payment history, "Pay now". `ClientDashboard.tsx`.
- `[F]` **(AG-03)** Per-client feature-toggle UI in Agent dashboard.
- `[F]` **(CL-02)** Guided first-login language picker step.

### Tests
- `[T-B]` Logo upload stores file + returns URL; rejects non-image/oversized.
- `[T-B]` Disabled feature → gated route 403 for that client; enabled → 200.
- `[T-B]` Subscription pay flow records payment; non-payment suspends.
- `[T-F]` Slot display shows `used/total`; refill increments; tax-rate save calls API.
- `[T-F]` Per-client feature toggle persists; client UI hides disabled feature.
- `[T-E2E]` Agent uploads logo → client login shows that logo + theme + only enabled features.

**Acceptance:** full agent self-service white-label + per-client features + master slot/tax controls + client subscription visibility.

---

## Phase 6 — Multi-branch, i18n polish, PDF, procurement (completeness)

### Backend
- `[B]` **(multi-branch)** Thread `branch_id` through `Transactions` and inventory; per-branch stock (`product_branch_stock` or `branch_id` on stock movements); branch-scoped reports. Replace the façade branch-inventory view. `pos.py`, `transactions.py`, `production.py:990-1036`.
- `[B]` **(PDF)** Add a real renderer (WeasyPrint/wkhtmltopdf) converting the existing Arabic HTML invoice to PDF bytes; endpoint returns `application/pdf`. Add lib to `requirements.txt`.
- `[B]` **(suppliers/PO)** Real receiving workflow: receiving a PO **increments inventory** + records cost; PO status lifecycle. `purchase_orders.py`.
- `[B]` **(bulk)** Confirm CSV import handles large catalogs with validation report (already mostly there).

### Frontend
- `[F]` **(branch)** Branch selector in POS + reports; respect active branch.
- `[F]` **(PDF)** "Download PDF" on receipts/quotations/invoices.
- `[F]` **(L10N-03)** Use `format.ts` Arabic-Indic digits everywhere; **SAR** currency (not `$`) across dashboards. `ClientDashboard.tsx:82`, `MasterDashboard.tsx:138`, etc.
- `[F]` **(L10N-04)** Locale-aware date/time helper (Gregorian required, Hijri optional) used app-wide.
- `[F]` **(i18n instant toggle)** Introduce a shared `LanguageContext`/provider so language changes re-render the whole app instantly. `i18n.ts:492-518`.
- `[F]` Fill missing translation keys flagged by the inline `|| 'English'` fallbacks across dashboards.
- `[F]` **(suppliers/PO)** Receiving UI updating stock.

### Tests
- `[T-B]` Sale in branch A deducts branch-A stock only; branch reports isolated; PO receive increments inventory.
- `[T-B]` PDF endpoint returns valid PDF bytes (magic header `%PDF`).
- `[T-F]` Currency shows SAR + Arabic-Indic digits in ar/ur; dates localized; language toggle re-renders siblings instantly.
- `[T-E2E]` Multi-branch sale + branch report; PDF download.

**Acceptance:** real multi-branch, real PDF, full localization polish, working procurement.

---

## Phase 7 — Mobile app (DECISION REQUIRED — large, separate track)

The SRS mandates a generic white-label mobile app (Flutter/RN) with offline SQLite + camera. **None exists.** This is a multi-week effort and should be scoped as its own project, not folded into the web fixes.

- **Decision point:** (a) build a React Native/Expo app reusing the API + branding endpoints; (b) ship the existing responsive web PWA as the "mobile" answer (installable, offline via the Phase 4 service worker) and defer native; (c) defer entirely.
- If (a): login → `GET /tenant/client/branding` theme apply → POS with camera barcode → offline SQLite queue → sync through the Phase-2/Phase-4 atomic+signed path → share API contract tests with web.

**Recommendation:** ship (b) the PWA now (cheap, satisfies "works on tablet/phone, offline") and schedule (a) as a follow-on once the web platform is stable through Phase 6.

---

## Cross-cutting test strategy (applies every phase)

- **Backend:** unit (services), integration (router + DB via httpx app fixture), per gap. Every fixed gap gets a regression test named after its gap-id. Mock all external I/O (Fatoora, SMTP, SMS, webhooks, bucket, Stripe).
- **Frontend:** component tests (RTL + MSW) for each changed page; assert the **API payload** the component sends (this is where most gaps hid). Snapshot RTL/Arabic receipt rendering.
- **E2E (Playwright):** the golden flows — provision→login (P1), signed sale + QR + refund (P2), permissioned actions (P3), full checkout (P4), white-label client experience (P5), multi-branch + PDF (P6).
- **Compliance harness:** a dedicated `test_zatca_compliance.py` that validates a real sale's TLV tags, ECDSA stamp, hash chain, and credit-note linkage end to end — the single most important suite.
- Ratchet the coverage gate upward each phase; CI stays green-to-merge.

---

## Sequencing summary

| Phase | Theme | Blocks | Rough size |
|-------|-------|--------|-----------|
| 0 | Test harness & CI | everything | 1–2 d |
| 1 | Identity & tenancy (C-1,2,5,6; MA-02) | all features | 4–6 d |
| 2 | ZATCA on sale path (C-3,4; POS-07) | legal go-live | 5–7 d |
| 3 | Production hardening | safe go-live | 5–7 d |
| 4 | POS feature completeness | usability | 4–6 d |
| 5 | Admin/white-label/subscription | business model | 4–6 d |
| 6 | Multi-branch, i18n, PDF, procurement | completeness | 5–7 d |
| 7 | Mobile (decision) | SRS mobile clause | separate track |

**Minimum viable compliant launch = Phases 0–3.** Phases 4–6 complete the SRS. Phase 7 is a scoped follow-on.
