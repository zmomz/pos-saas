# POS-SaaS — Complete System Functionality

A multi-tenant, white-label **Point-of-Sale SaaS** built for the Saudi Arabian market (ZATCA e-invoicing, 15% VAT, Arabic-first receipts, Moyasar/Mada payments). Backend is **FastAPI + async SQLAlchemy + Alembic** (37 routers, ~60 models, ~70 services, 79 migrations); frontend is **React + Vite + TypeScript** (~50 pages) with offline-capable POS, WebUSB thermal printing, and per-tenant branding.

## 1. The Three-Tier Platform Model

The whole system is organized around a reseller hierarchy, resolved live per request in `dependencies/tenancy.py`:

| Tier | Identity | What they do |
|------|----------|--------------|
| **Master** (`users.role == "admin"`) | Seeded from `ADMIN_EMAIL`/`ADMIN_PASSWORD` | Platform owner. Manages packages, agents, the global tax rate; sees platform-wide economics. `owner_user_id = None` (unrestricted). |
| **Agent** (`Agents` row) | White-label reseller | Provisions merchant clients under their own brand (logo, colors, fonts, custom domain). Connects their *own* Moyasar account to collect merchant subscriptions. |
| **Client** (`Clients` row) | The merchant/tenant | Runs the actual POS. Belongs to exactly one agent. Has a `business_type` (retail / restaurant / both). |
| **Staff** (`Staff_members` row) | Cashier / manager under a merchant | Logs in with their own account but resolves to the **merchant's** tenant — shares the merchant's catalog, customers, and sales. |

**The tenant boundary is `owner_user_id`**, never the raw login `user_id` (issue #193). For agents/merchants `owner_user_id == user_id`; for staff it's the owning merchant's id; for master it's `None`. `client_id` is *advisory* denormalized metadata that can only narrow *within* a tenant, never cross it. Every service query filters on `owner_user_id` first (SEC-02). Suspending an agent (`is_active=False`) cascades — all their merchants go dark at the auth layer; suspending a merchant blocks just that merchant and its staff.

## 2. Authentication & Security

- **Passwords**: bcrypt (`core/security.py`), with a configurable complexity policy (min length, upper/lower/digit/symbol).
- **JWT tokens** (`core/auth.py`): 24h access token + 7d refresh token. Access token carries `sub/email/role/sid/sv(security-stamp)/jti`. Refresh token is stored as an **HttpOnly cookie** (`pos_refresh_token`), never exposed to JS.
- **Revocation**: server-side blocklist (`revoked_tokens`) checked on every request; logout and per-session revoke add the `jti`. A **security stamp** (`token_version`) is bumped on password reset, instantly invalidating all prior tokens.
- **Sessions** (`user_sessions`): each login is recorded and individually revocable.
- **Login throttling** (`services/login_throttle.py`, SEC-15): three independent counters — per (email,IP) pair, per-account (anti-spray), and per-IP — with 15-min lockouts returning HTTP 429.
- **MFA/TOTP** (`core/totp.py`, RFC 6238 from stdlib): enroll → QR provisioning URI → activate; issues 10 hashed single-use recovery codes. Login with MFA returns a short-lived 5-min MFA token, then a second `/login/mfa` step (separately throttled).
- **Password reset**: single-use SHA-256-hashed token, 30-min TTL, silent on unknown email (no enumeration).
- **Forced reset**: `must_change_password` (set on every provisioned account) is checked live each request; blocks all paths except change-password/auth until rotated.
- **RBAC** (`dependencies/permissions.py`): managed keys `pos.refund`, `pos.void`, `pos.discount`, `pos.price_override`. Cashiers are denied by default, managers/admins allowed; explicit per-user `permissions` rows override role defaults; master bypasses all.

## 3. The POS Sale Core

The checkout (`POST /api/v1/pos/transaction` → `services/sale_core.py`) is a single **atomic** transaction; the server is authoritative and never trusts client totals. Calculation order:

1. **Subtotal** from line items (Decimal, half-up rounding via `core/money.py` — penny-exact on all DBs).
2. **Price-override gate**: any off-catalog price requires `pos.price_override` unless the product is open-price.
3. **Discounts** (composed, then capped at subtotal): reusable discount rules, single-use discount codes, manual discount (needs `pos.discount`), loyalty redemption, and auto-applied promotions.
4. **VAT** at the effective rate (master global setting → 15% default), computed on `subtotal − discount`.
5. **Tip/gratuity** and **service charge** are added *on top*, **outside** the VAT/ZATCA base.
6. **Tenders**: split payments must sum exactly to the charge total (no epsilon slop). Cash computes change (drawer-facing only).

Inside the commit: gift cards validated/decremented → card tenders charged via gateway (decline → 402 rollback) → **atomic invoice number** minted (`INV-{client:04d}-{seq:06d}`) → **stock deducted** with conditional UPDATEs → loyalty accrued → open shift counters bumped → **ZATCA document signed & archived**. A failure anywhere rolls the whole sale back.

**Payment tenders** (`models/payment_tenders.py`) store only gateway tokens + last-4 — **no PAN ever touches the server** (PAY-09). Supported: cash, card, mada, applepay, stcpay, tabby, tamara, transfer, loyalty, giftcard.

**Reversals**:
- **Refund** → ZATCA type-381 **credit note** (full or per-line/weighted), prorates discount/VAT, restores only returned units, routes cash refunds to drawer and card refunds back to origin via gateway. Flips original to `refunded`/`partial_refunded`.
- **Void** → cancels a whole sale and restores stock, but is **blocked once the ZATCA document is cleared** (must refund instead).
- **Hold/Recall** → parks a cart (`HELD-…`) with no fiscal effects; recall re-rings it.

**Shifts & cash drawer**: open/close with opening/closing cash; pay-in / pay-out / cash-drop movements; reconciliation formula `opening + cash_sales − cash_refunds + pay_in − pay_out − cash_drops` produces the X/Z report (single source of truth) and fires a `shift.closed` webhook.

**Receipts**: Always-Arabic ESC/POS thermal output rendered to a 1-bit bitmap (Amiri font + reshaper + bidi) with embedded ZATCA QR, 80mm/58mm, customizable templates (header/footer/logo/QR toggles), reprint marking, ASCII fallback. Printer routing by role/station. **Terminals** (Geidea/PAX/etc. SoftPOS) are registered per-owner and resolved per tender leg.

## 4. Catalog & Inventory

- **Products**: bilingual name, barcode, price/cost, VAT rate, image, category, `is_weighted` (fractional qty) and `is_open_price` flags, reorder point/quantity. CSV import (upsert by barcode) / export.
- **Variants**: independently-sellable SKUs with own barcode/price/stock; barcode scan resolves to the variant and decrements only its stock.
- **Categories**: tree via `parent_id`.
- **Branches & multi-location stock**: per-branch ledgers (`product_branch_stock`, `variant_branch_stock`), lazily seeded from client-level quantity on first touch. A branch-tagged sale deducts from that branch only.
- **Atomicity** (DAT-02/03/04): all stock mutations are single conditional UPDATEs (`WHERE quantity >= qty`) so N concurrent sales on stock K let exactly K succeed; overselling is opt-in.
- **Stock adjustments** (count/wastage/damage/correction) record variance snapshots; **stock transfers** move between branches (one-step or two-phase dispatch/receive with CAS-gated receipt).
- **Suppliers & Purchase Orders**: PO lifecycle draft → sent → partially_received → received; `/receive` (full or partial, branch-aware) increments stock and recomputes **moving-average cost**.

## 5. Customers, Loyalty, Discounts, Promotions

- **Customers/CRM**: tags/segments, VAT number (B2B), marketing consent + **PDPL data-export and right-to-erasure** (PII tombstoned while fiscal records retained), RFM-lite insights (LTV, recency, visit count, segment).
- **Loyalty**: one active program per tenant (earn `points_per_sar`, redeem at `redemption_rate`, min redemption, optional FIFO expiry); append-only ledger; atomic no-double-spend redemption capped at subtotal.
- **Gift cards**: CSPRNG bearer codes, Money-typed balance, issue/reload/void/refund-to-card, atomic redemption on the sale path, full ledger.
- **Discounts**: reusable rules (percentage/fixed, min-purchase, usage caps, validity window) — validated server-side, consumed atomically with the sale; plus batch-generated **single-use codes**.
- **Promotions**: auto-applied line/category/**BOGO** rules with `min_subtotal` thresholds; a preview endpoint prices the cart before tender.
- **Quotations**: non-fiscal Arabic quote documents (draft→sent→accepted→expired/converted); `/convert` pushes lines through the sale core into a real fiscal invoice.
- **Expenses**: simple categorized expense tracking.

## 6. Restaurant & Omnichannel

- **Floor/tables**: zones + tables with state machine (`free → occupied → bill_printed`); reservations (booked/seated/cancelled/no_show) and walk-in waitlist.
- **Order tickets**: dine-in/takeaway/delivery, statuses `open → held → fired → settled/void`; line items carry course, seat, prep-station, modifiers, combo expansion.
- **KDS (Kitchen Display)**: real-time via **Server-Sent Events** through an **in-process broker** (`services/kds_channel.py`) — boot asserts single-worker (multi-worker needs Redis). Firing a course materializes per-station KDS cards (`fired → bumped`, recallable); SSE secured by short-lived single-use stream tickets.
- **Menu builder**: modifier groups (required/min/max, price deltas), combos (bundle price, expands to components for stock), and **Bill-of-Materials/recipes** (parent product consumes `qty_per` of component products at settle, rolling up true COGS).
- **Settlement**: full / partial (per-seat or per-line) routes through the same atomic sale core (stock + ZATCA + tenders), with service charge and tip outside the VAT base.
- **Omnichannel**: **Salla** online-store connector and **delivery aggregators** (Deliverect / Delivery Hero class middleware) ingest orders via HMAC-signed webhooks (fail-closed). Orders are claimed idempotently in `channel_orders` on `(provider, external_order_id, client_id)`, settled under a **CAS settle-lock** (`received → settling → imported`) that survives concurrent re-delivery and crashes (a background sweep re-opens claims stuck > 10 min). They become tableless KDS tickets + ZATCA invoices, paid as out-of-band `online` tenders with oversell allowed.

## 7. Billing — Two Independent Revenue Rails

| | **Rail 1 — Agent Quota** | **Rail 2 — Merchant Subscription** |
|---|---|---|
| Who pays whom | Agent → Platform | Merchant → Agent |
| Moyasar account | Platform's (`MOYASAR_API_KEY`) | Agent's own (`moyasar_secret_key_enc`) |
| Ledger | `agent_quota_payments` | `subscription_payments` |
| Status | `quota_status` | `subscription_status` |

- **Packages** define `client_slots`, `wholesale_price`, suggested retail, and a JSON **feature tier**. Provisioning an agent seeds slot count + feature entitlements.
- **Features/entitlements**: `agent_features` (defaults) and `client_features` (per-merchant overrides), enabled-by-default; `require_feature(...)` dependency 403s when disabled. Keys: email/sms receipts, loyalty, restaurant, inventory, discounts, zatca, omnichannel.
- **Cards on file**: tokenized client-side via moyasar.js (no PAN), stored **encrypted at rest** (`core/crypto`, SEC-05).
- **Dunning** (`services/dunning.py`): pure state machine `active → past_due → dunning → suspended` (configurable retries/grace). Uses **reserve-then-charge** idempotency (`(client_id, period_key)` unique) to close double-charge races; sends bilingual notices; subscription charges **fail closed** (402, period not advanced) if the agent hasn't connected Moyasar.
- **Billing scheduler** (`services/billing_scheduler.py`, gated by `BILLING_SCHEDULER_ENABLED`): hourly sweep runs global subscription dunning, quota dunning, and aggregator stuck-claim recovery.
- **Trials & coupons**: per-merchant `trial_end` and percentage/fixed coupons with duration, exact Decimal math.
- Gateways (`services/payment_gateway.py`): **Sandbox** (deterministic, no creds — keeps flows demoable), **Moyasar** (Mada/ApplePay/STCPay/card, amounts in halalas), **Geidea SoftPOS** for in-store terminals. Refund-to-origin resolves the original capturing gateway.

## 8. ZATCA E-Invoicing (Saudi Phase 2)

Real cryptography, not stubs (`services/zatca.py`, `zatca_sale.py`):
- **Onboarding**: generate secp256k1 keypair + PKCS#10 CSR → exchange for compliance CSID (CSR+OTP) → production CSID; private key AES-256-GCM encrypted at rest.
- **Per-sale** (inside the commit): build UBL XML, C14N canonicalize, SHA-256 invoice hash, **ECDSA-SHA256 stamp**, enveloped XAdES signature, 8-tag **TLV QR**, and advance the **PIH hash chain** (each invoice chains to the previous via `previous_hash`/`icv`).
- **Routing** (ZA-06): `standard` (B2B clearance, buyer VAT + ≥1000 SAR) vs `simplified` (B2C reporting).
- **Reporting** is decoupled and **fail-closed** (`live_submission_enabled` default off): documents sit `pending` until onboarded; a batch reconciler resubmits stuck/failed ones; statuses `signed → reported/cleared/failed`.
- **6-year retention** archive (`zatca_documents`), an **integrity endpoint** walks the chain verifying every link and stamp, and a status summary dashboard. ZATCA can be disabled per merchant (simplified receipts, no stamp).

## 9. Platform Operations

- **Store settings** (per-merchant: CR number, receipt footer, address, hours; business name + VAT live on the `clients` row for fiscal authority). **System settings** (master-global key/value, notably the global tax rate that overrides agent/client rates).
- **Webhooks**: subscriptions with event lists + HMAC secret; append-only delivery log with attempts/status; outbound events like `product.created`, `customer.created`, `shift.closed`; inbound Moyasar webhooks deduped via `processed_webhook_events` (`(source, event_id)` unique), signature-verified fail-closed.
- **Audit logs**: append-only, **tamper-evident SHA-256 hash chain** (`prev_hash`/`row_hash`), best-effort writer in its own session (never breaks the request), tenant-scoped to the owner so merchants see all staff actions, plus failed-auth records. Read-only — no mutation routes; admin can read all.
- **API usage metering** (opt-in) + **rate limiting** (token bucket, 429 with Retry-After) + **request-size validation** (10MB cap) as middleware. Both metering and audit are read-only to clients.
- **Observability**: correlation IDs on every request, structured JSON logging (`LOG_FORMAT=json`), slow-request logging, Sentry (config-gated), SMTP email (provisioning, branded templates) and Twilio SMS senders.
- **Storage**: optional OSS gateway with presigned upload/download URLs; local `/uploads` static mount for logos/product images. Health endpoint checks DB.
- **Reports/analytics**: dashboards per tier — master economics (MRR, churn, agent leaderboard), agent revenue/commission statements, client sales KPIs + top products, all via SQL aggregation (never load-all).

## 10. Frontend Application

- **Routing** (`src/App.tsx`): five role-gated groups via `ProtectedRoute` — public (landing, login, `/d/:agentId` white-label funnel, customer-display, force-reset), master (`/master`, `/packages`), agent (`/agent`, `/branding`), client-core/POS (`/pos`, `/floor`, `/kds`, `/shifts`, `/menu-builder`, `/zatca`, `/store-settings`, …), client-data (`/products`, `/customers`, `/staff`, `/reports`, `/discounts`, …), and shared (`/profile`, `/audit`, `/notifications`).
- **Auth**: `AuthContext` resolves role via `/tenant/role` (retries rather than downgrading on a network blip — FE-06); access token in localStorage, refresh via HttpOnly cookie. The axios client injects the Bearer header and, on 401, performs a single **coalesced** refresh-and-replay, dispatching `pos:session-expired`/`pos:rate-limited` events to toasts.
- **White-label branding**: `BrandingContext` resolves brand by role (or by custom domain pre-login), injects HSL CSS variables (`--primary`, `--radius`, fonts) and a default language; agents fully re-skin their merchants' portals.
- **i18n/RTL**: Arabic/English/Hindi/Urdu, RTL via Radix `DirectionProvider`; light/dark theme.
- **Offline POS**: IndexedDB queue (`pos-offline`, ring-buffer cap 500), service-worker-cached shell, chunked replay (100/batch) on reconnect, global offline banner, `useOnlineStatus`.
- **Hardware**: WebUSB ESC/POS thermal printing (backend emits base64), Moyasar card tokenization (sandbox fallback, PAN-free), and a **customer-facing second screen** synced via localStorage (bilingual, branded).
- **Shell**: `DashboardLayout` icon-rail nav (role-specific) + command bar with ⌘K palette, notifications, page-contributed chrome (`PageChromeContext`), onboarding tour.

---

## Cross-cutting principles the code enforces everywhere

- **Tenant isolation** on `owner_user_id` (SEC-02); `client_id` is advisory only.
- **Atomicity**: sales, settlements, and stock moves commit-or-rollback as a unit; concurrency handled with conditional UPDATEs and CAS locks.
- **Penny-exact money**: Decimal + half-up, halalas at the gateway boundary; **no PAN on the server**.
- **Fail-closed security**: webhook signatures, ZATCA live submission, subscription charges, and forced-reset all default to the safe state.
- **Saudi-first**: Arabic receipts, 15% VAT, ZATCA hash-chained signed invoices, Mada/STCPay/Moyasar.
