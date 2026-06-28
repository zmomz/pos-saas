# POS-SaaS — Scenarios & Workflows

Every realistic way a human interacts with the system, written as click-by-click journeys. Organized by actor (Master → Agent → Merchant → Staff → Customer) and then by domain. Each scenario names the screen, the buttons/fields touched, the server call behind them, and the expected outcome (including the failure branches, because failure paths are real workflows too).

Legend: **[Button]** = a control the user clicks · `field` = an input they fill · → = resulting state/navigation · ⚠ = error/edge branch.

---

## A. MASTER (Platform Owner)

### A1. First-ever platform login & forced password rotation
1. Master opens the app at the root domain → lands on **Landing** page.
2. Clicks **[Login]** in the top nav → **Login** screen.
3. Enters `email` (= `ADMIN_EMAIL`), `password` (= `ADMIN_PASSWORD`), clicks **[Sign in]**.
4. Server authenticates; because the seeded account has `must_change_password = true`, the app redirects to **Force-Reset** (`/force-reset`) — every other route is blocked.
5. Master fills `current password`, `new password`, `confirm new password`. The strength meter validates against the complexity policy (min length, upper/lower/digit/symbol). Clicks **[Update password]**.
6. ⚠ If new ≠ confirm, or policy fails → inline error, stays on page.
7. On success the security stamp (`token_version`) bumps, all prior tokens die, master is bounced to **Login** to sign in fresh → lands on **Master Dashboard** (`/master`).

### A2. Read platform economics
1. On **Master Dashboard**, master sees MRR, churn, agent leaderboard cards (SQL-aggregated, never load-all).
2. Clicks **[Date range]** selector → picks "Last 30 days" → cards re-query.
3. Clicks an agent row in the **Agent Leaderboard** → drills into that agent's revenue/commission.
4. Clicks **[Export]** (if present) → downloads CSV of the aggregate.

### A3. Create a subscription Package
1. Master clicks the **Packages** nav icon → **Packages** list (`/packages`).
2. Clicks **[+ New Package]** → package form drawer.
3. Fills `name`, `client_slots` (e.g. 25), `wholesale_price` (what the agent pays platform), `suggested_retail` (hint for agents).
4. Toggles the **feature tier** JSON switches: email/sms receipts, loyalty, restaurant, inventory, discounts, zatca, omnichannel.
5. Clicks **[Save]** → package appears in list.
6. Edits later via **[⋮ → Edit]**; **[⋮ → Archive]** to retire (existing agents keep their seeded entitlements).

### A4. Provision / suspend an Agent
1. Master opens **Agents** (under master area) → **[+ New Agent]**.
2. Fills agent `name`, `email`, `package` (dropdown), optional `custom domain`.
3. Clicks **[Create Agent]** → server seeds the agent, copies the package's `client_slots` and feature entitlements into `agent_features`, sets `must_change_password = true`, and fires a branded provisioning email (SMTP).
4. To pause an agent: open the agent row → toggle **[Active]** off → `is_active = false`. This **cascades**: the agent and *all* their merchants and staff are blocked at the auth layer instantly.
5. Toggle back **[Active]** on to restore.

### A5. Set the global tax rate (overrides everyone)
1. Master opens **System Settings** (master-global key/value).
2. Edits `global_tax_rate` field (default 15%), clicks **[Save]**.
3. → This rate now overrides any agent/client tax rate in the sale core's VAT step.

---

## B. AGENT (White-label Reseller)

### B1. Agent first login + forced reset
Same flow as A1 but lands on **Agent Dashboard** (`/agent`) after rotating the provisioned password.

### B2. Connect the agent's own Moyasar account (Rail 2 enabler)
1. Agent opens **Billing / Payments settings**.
2. Pastes their Moyasar `secret key` into the `moyasar_secret_key` field → clicks **[Connect]**.
3. Server encrypts it at rest (`moyasar_secret_key_enc`, SEC-05) and validates.
4. ⚠ Until this is connected, **all merchant subscription charges fail closed (402)** — dunning will not advance the period. A red banner warns "Connect Moyasar to collect from merchants."

### B3. Customize branding / style (the "customizing style for agent" journey)
1. Agent clicks **Branding** nav (`/branding`).
2. **Logo:** clicks **[Upload logo]** → file picker → image uploads (OSS presigned URL or `/uploads`), live preview updates.
3. **Colors:** uses the `--primary` color picker, adjusts the `--radius` slider (corner roundness). The HSL CSS variables update the live preview pane in real time.
4. **Fonts:** picks a `heading font` and `body font` from the dropdown.
5. **Default language:** sets Arabic / English / Hindi / Urdu.
6. **Custom domain:** enters `pos.mybrand.com` in the `custom domain` field.
7. Clicks **[Save branding]** → `BrandingContext` re-resolves; from now on this agent's merchants see the re-skinned portal, and pre-login visitors hitting the custom domain get this brand.
8. Clicks **[Preview as merchant]** to sanity-check the skin.
9. ⚠ Resets to defaults via **[Restore defaults]**.

### B4. Provision a Merchant (Client)
1. Agent opens **Clients/Merchants** list → **[+ New Merchant]**.
2. Fills merchant `business name`, `email`, **`business_type`** = retail / restaurant / both, optional `trial_end`, optional `coupon`.
3. Clicks **[Create Merchant]**.
4. ⚠ If the agent has no free `client_slots` left → blocked with "Quota full — buy more slots."
5. → Server creates the `Clients` row under this agent, seeds `client_features` (overridable), sets `must_change_password = true`, emails the merchant branded credentials.

### B5. Per-merchant feature overrides
1. Agent opens a merchant → **Features** tab.
2. Toggles e.g. **[Restaurant]** off for a retail-only shop, **[Omnichannel]** on, etc. (`client_features` overrides agent defaults).
3. Clicks **[Save]** → any route guarded by `require_feature` now 403s for that merchant if disabled.

### B6. Agent buys more quota slots (Rail 1: Agent → Platform)
1. Agent dashboard shows "Slots: 24/25 used." Clicks **[Buy more slots]** / **[Upgrade package]**.
2. Selects a package, clicks **[Pay]** → charged via the **platform's** Moyasar (`MOYASAR_API_KEY`), logged in `agent_quota_payments`, `quota_status` updated.
3. ⚠ If quota payment fails → quota dunning state machine progresses; eventually agent is restricted.

### B7. Agent revenue & commission statement
1. Agent opens **Reports** → sees subscription revenue collected from merchants, commission owed, statements.
2. Clicks **[Download statement]** → CSV/PDF.

---

## C. MERCHANT ONBOARDING

### C1. Self-serve signup through the white-label funnel
1. A prospect visits the agent's funnel link `/d/:agentId` (or the agent's custom domain) → sees the **agent-branded** landing/signup funnel.
2. Fills `business name`, `email`, `business type`, clicks **[Start free trial]** / **[Sign up]**.
3. → Creates a merchant under that agent (consuming a slot), `trial_end` set, provisioning email sent.
4. Merchant clicks the email link → **Force-Reset** → sets password → **Onboarding tour** begins on first dashboard load.

### C2. Onboarding tour
1. On first login the **onboarding tour** overlay appears.
2. Merchant clicks **[Next]** through steps (Add products → Open shift → Make a sale → Settings), or **[Skip tour]**.
3. **[Finish]** dismisses it (won't show again).

---

## D. RETAIL MERCHANT — CATALOG & INVENTORY SETUP

### D1. Create categories (tree)
1. Open **Products** → **Categories** tab → **[+ Category]**.
2. Fill `name (AR)`, `name (EN)`, optional `parent` (dropdown to nest via `parent_id`) → **[Save]**.

### D2. Add a product manually
1. **Products** → **[+ New Product]**.
2. Fill bilingual `name AR`/`name EN`, `barcode`, `price`, `cost`, `VAT rate`, `category`.
3. Upload `image` via **[Upload image]**.
4. Toggle **[Weighted]** (sells fractional qty, e.g. produce) and/or **[Open price]** (cashier types price).
5. Set `reorder point` and `reorder quantity`.
6. **[Save]** → product live; fires `product.created` webhook.

### D3. Add variants
1. Open a product → **Variants** tab → **[+ Variant]**.
2. Fill variant `name` (e.g. "Large / Red"), own `barcode`, `price`, `stock`.
3. **[Save]** → scanning that barcode at POS resolves to the variant and decrements only its stock.

### D4. Bulk import via CSV
1. **Products** → **[Import CSV]** → **[Choose file]** → upload.
2. Preview maps columns; **[Confirm import]** → upserts by barcode (existing rows updated, new rows created).
3. **[Export CSV]** dumps the full catalog.

### D5. Multi-branch setup & stock
1. Open **Branches/Locations** → **[+ Branch]** → fill name/address → **[Save]**.
2. First sale/touch at a branch lazily seeds `product_branch_stock` from the client-level quantity.
3. A branch-tagged sale deducts from that branch only.

### D6. Stock adjustments (count / wastage / damage / correction)
1. **Inventory** → **[Adjust stock]** → pick product, `type` (count/wastage/damage/correction), enter counted/delta qty, `reason`.
2. **[Save]** → records a variance snapshot.

### D7. Stock transfer between branches
1. **Inventory** → **Transfers** → **[+ Transfer]**.
2. Pick `from branch`, `to branch`, add line items + qty.
3. One-step: **[Transfer & receive]** moves immediately.
4. Two-phase: **[Dispatch]** (source decrements) → at destination **[Receive]** (CAS-gated, increments). ⚠ Double-receive is blocked by the compare-and-swap.

### D8. Suppliers & Purchase Orders
1. **Suppliers** → **[+ Supplier]** → fill details → **[Save]**.
2. **Purchase Orders** → **[+ PO]** → pick supplier, add lines/qty/cost → **[Save as draft]**.
3. **[Send]** → status `sent`.
4. On delivery: **[Receive]** → enter received qty (full or partial), pick branch → stock increments and **moving-average cost recomputes**. Status → `partially_received` → `received`.

---

## E. RETAIL MERCHANT — CUSTOMERS, LOYALTY, DISCOUNTS, PROMOTIONS

### E1. Add a customer (B2B)
1. **Customers** → **[+ Customer]** → fill `name`, `phone`, `email`, `VAT number` (for B2B standard invoices), `tags`.
2. Toggle **[Marketing consent]** → **[Save]** → fires `customer.created` webhook.

### E2. PDPL data rights
1. Open a customer → **[Export data]** → downloads their PII bundle (PDPL right to access).
2. **[Erase / Right to be forgotten]** → confirm dialog → PII tombstoned while fiscal records retained.

### E3. Set up the loyalty program
1. **Loyalty** → **[Configure]** → set `points_per_sar` (earn), `redemption_rate`, `min redemption`, optional `FIFO expiry`.
2. **[Activate]** → one active program per tenant.
3. At POS, redemption is atomic, capped at subtotal, no double-spend.

### E4. Gift cards
1. **Gift Cards** → **[Issue]** → enter `amount`, optional recipient → CSPRNG bearer code generated.
2. **[Reload]** adds balance; **[Void]** disables; **[Refund to card]** returns funds. Every action hits the append-only ledger.

### E5. Discount rules & single-use codes
1. **Discounts** → **[+ Rule]** → choose `percentage`/`fixed`, `value`, `min purchase`, `usage cap`, `validity window` → **[Save]**.
2. **[Generate codes]** → batch quantity → produces single-use codes (export list).

### E6. Promotions (auto-applied / BOGO)
1. **Promotions** → **[+ Promotion]** → type line/category/**BOGO**, set `min_subtotal` threshold → **[Save]**.
2. At POS these auto-apply; the **[Preview]** endpoint prices the cart before tender.

### E7. Quotations
1. **Quotations** → **[+ Quote]** → add lines, customer → **[Save draft]** → **[Send]** (Arabic quote doc).
2. Customer accepts → **[Mark accepted]**.
3. **[Convert]** → pushes lines through the sale core into a real fiscal invoice.

### E8. Expenses
1. **Expenses** → **[+ Expense]** → category, amount, note → **[Save]**.

---

## F. RETAIL MERCHANT — RUNNING THE POS (the "buy 3 items" core)

### F0. Open a shift (precondition)
1. Cashier opens **Shifts** (`/shifts`) → **[Open shift]** → enter `opening cash` → **[Confirm]** → drawer opens.

### F1. Buy 3 items, pay by card (happy path)
1. Cashier opens **POS** (`/pos`).
2. **Item 1:** scans a barcode (or taps the product tile, or types in search) → line added qty 1.
3. **Item 2:** taps a product tile → **[+]** twice to set qty 3.
4. **Item 3 (weighted):** taps a weighted product → enters weight `0.750` kg → **[Add]**.
5. Optionally taps **[Customer]** → searches/selects a customer (for loyalty/B2B VAT).
6. Reviews the cart: subtotal, VAT (15% on subtotal − discount), total update live.
7. Clicks **[Pay]** → tender screen.
8. Selects **[Card]** → amount prefilled to total → SoftPOS/Moyasar leg runs → approved.
9. Clicks **[Charge]** → server runs the atomic transaction: subtotal → discounts → VAT → tip/service (none) → tender sums must equal total exactly → gift/loyalty (none) → **invoice number minted** `INV-0007-000123` → **stock deducted** (conditional UPDATE) → loyalty accrued → shift counters bumped → **ZATCA doc signed & archived**.
10. **Receipt:** clicks **[Print]** → WebUSB ESC/POS Arabic thermal receipt with ZATCA QR prints; **[Email]**/**[SMS]** receipt buttons send copies; **[New sale]** clears the cart.
11. ⚠ If card declines → **402**, whole sale rolls back, nothing minted, cashier retries another tender.

### F2. Split tender (cash + card)
1. At the tender screen click **[Split]**.
2. Add **[Cash]** SAR 50 → app shows remaining.
3. Add **[Card]** for the remainder → **[Charge]**.
4. ⚠ Tenders must sum **exactly** to the total (no epsilon slop) or **[Charge]** stays disabled.
5. Cash overpay → app computes **change** (drawer-facing only, not on fiscal total).

### F3. Manual discount, price override, open price (permission gates)
1. **Manual discount:** cashier clicks **[Discount]** → enters amount/%. Requires `pos.discount`. ⚠ Cashier without permission → blocked, prompts manager.
2. **Manager override:** manager logs the action or has the permission → discount applies (capped at subtotal).
3. **Price override:** on a line, click **[Edit price]** → off-catalog price requires `pos.price_override` (unless the product is open-price).
4. **Open-price item:** tapping it just prompts for the price, no permission needed.

### F4. Apply a discount code / gift card / loyalty at tender
1. **[Apply code]** → type single-use code → validated → consumed atomically with the sale.
2. **[Gift card]** tender → scan/type code → balance validated & decremented.
3. **[Redeem loyalty]** → choose points → converts to discount, capped at subtotal.

### F5. Add tip & service charge
1. Click **[Tip]** → enter amount/% (added **on top**, outside VAT/ZATCA base).
2. Click **[Service charge]** → applied on top similarly.

### F6. Hold & recall a cart
1. Mid-sale click **[Hold]** → cart parked as `HELD-…`, no fiscal effect, POS clears for next customer.
2. Click **[Recall]** → pick the held cart → it re-rings.

### F7. Refund (credit note)
1. **Sales/Receipts** history → open a sale → **[Refund]**. Requires `pos.refund`.
2. Choose **full** or per-line/weighted partial quantities → **[Process refund]**.
3. → ZATCA **type-381 credit note** issued, discount/VAT prorated, only returned units restocked, cash refunds routed to drawer / card refunds back to origin gateway. Original flips to `refunded`/`partial_refunded`.

### F8. Void a sale
1. Open a recent sale → **[Void]**. Requires `pos.void`.
2. ⚠ If the ZATCA document is already cleared → **Void blocked**, app says "Must refund instead."
3. Otherwise → sale cancelled, stock restored.

### F9. Cash drawer movements
1. **Shifts** → **[Pay in]** (add cash, reason), **[Pay out]** (remove, reason), **[Cash drop]** (move to safe).

### F10. Close the shift (X/Z report)
1. **Shifts** → **[X report]** → preview without closing.
2. **[Close shift]** → enter `closing cash count` → reconciliation `opening + cash_sales − cash_refunds + pay_in − pay_out − cash_drops` computes expected vs counted → **Z report** shown, over/short flagged → fires `shift.closed` webhook.

### F11. Offline POS
1. Connection drops → global **offline banner** appears.
2. Cashier keeps ringing sales → queued in IndexedDB (`pos-offline`, cap 500).
3. On reconnect → chunked replay (100/batch) flushes the queue; banner clears.
4. ⚠ Queue at cap 500 → oldest dropped (ring buffer), user warned.

### F12. Receipt template customization
1. **Store Settings** → **Receipt** → toggle header/footer/logo/QR, edit `footer text`, choose 80mm/58mm → **[Save]**.
2. **[Test print]** → sample receipt. Reprints are marked "REPRINT".

---

## G. RESTAURANT MERCHANT (the "3 items from a restaurant" core)

### G1. Build the menu
1. **Menu Builder** (`/menu-builder`).
2. **Modifier groups:** **[+ Group]** → name "Add-ons", set required?/min/max, **[+ Option]** with `price delta` → **[Save]**.
3. **Combos:** **[+ Combo]** → bundle products, set `bundle price` → on sale it expands to components for stock.
4. **Recipes/BOM:** open a product → **[+ Recipe]** → add component products with `qty_per` → at settle these are consumed, rolling up true COGS.

### G2. Set up the floor
1. **Floor** (`/floor`) → **[+ Zone]** (e.g. "Patio") → **[+ Table]** → drag to position, set seats.

### G3. Reservation & waitlist
1. **Floor** → **[Reservations]** → **[+ Reservation]** → customer, time, party size → status `booked`.
2. On arrival **[Seat]** → `seated`; or **[No-show]** / **[Cancel]**.
3. Walk-in with no table → **[Add to waitlist]**.

### G4. Dine-in: open ticket, fire 3 items, KDS, settle (full journey)
1. **Floor** → tap a `free` table → table → `occupied`, opens **Order Ticket** (dine-in).
2. **Item 1:** add a burger → prompted for **required modifiers** (e.g. doneness) → select → set `seat 1`, `course main`.
3. **Item 2:** add fries (combo) → expands to components.
4. **Item 3:** add a drink → `seat 2`.
5. Click **[Send / Fire]** (or **[Fire course]**) → ticket `open → fired`; materializes per-station **KDS** cards (kitchen vs bar).
6. **KDS screen** (`/kds`): kitchen sees the card via SSE (real-time) → cook clicks **[Bump]** when ready (`fired → bumped`); **[Recall]** if needed.
7. Table state → `bill_printed` when bill requested via **[Print bill]**.
8. **[Settle]** → tender screen (same atomic sale core): choose full or **per-seat / per-line partial**.
   - Per-seat: select seat 1's items → **[Pay]** by card; later seat 2 pays cash.
9. Add **[Service charge]** + **[Tip]** (outside VAT base) → **[Charge]** → stock + recipe COGS consumed, ZATCA invoice signed, tenders captured.
10. Table auto-returns to `free`.

### G5. Takeaway / delivery ticket
1. **Order Tickets** → **[+ Ticket]** → type `takeaway` or `delivery` (no table) → add items → **[Fire]** → **[Settle]**.

### G6. Multi-worker KDS warning
- ⚠ KDS SSE uses an in-process broker; on boot the app asserts single-worker. Running multi-worker without Redis → KDS won't broadcast (ops note, surfaced as a health warning).

---

## H. OMNICHANNEL

### H1. Connect Salla online store
1. **Integrations** → **Salla** → **[Connect]** → OAuth/credentials → **[Save]**.
2. Incoming Salla orders arrive via HMAC-signed webhook (fail-closed if signature bad), claimed idempotently in `channel_orders`.

### H2. Connect a delivery aggregator (Deliverect / Delivery Hero class)
1. **Integrations** → pick aggregator → **[Connect]** → paste webhook secret → **[Save]**.
2. An order webhook arrives → claimed on `(provider, external_order_id, client_id)` → CAS settle-lock `received → settling → imported` → becomes a **tableless KDS ticket + ZATCA invoice**, paid as out-of-band `online` tender (oversell allowed).
3. ⚠ Re-delivered/duplicate webhook → idempotent, no double order. ⚠ A claim stuck > 10 min → background sweep re-opens it.

---

## I. ZATCA E-INVOICING

### I1. Onboard a merchant to ZATCA Phase 2
1. **ZATCA** (`/zatca`) → **[Start onboarding]**.
2. App generates secp256k1 keypair + PKCS#10 CSR (private key AES-256-GCM encrypted at rest).
3. Enter ZATCA `OTP` → **[Get compliance CSID]** → then **[Get production CSID]**.
4. → Each sale now builds UBL XML, canonicalizes, hashes, ECDSA-SHA256 stamps, XAdES-signs, emits 8-tag TLV QR, advances the PIH hash chain.

### I2. Toggle live submission / reporting
1. **ZATCA** → **[Enable live submission]** (default off). Until on, docs sit `pending`.
2. **[Reconcile now]** → batch resubmits stuck/failed docs (`signed → reported/cleared/failed`).

### I3. Chain integrity check
1. **ZATCA** → **[Verify integrity]** → walks the hash chain validating every link + stamp → shows green/red per invoice.
2. **Status summary** dashboard shows counts by status.

### I4. Disable ZATCA for a merchant
1. Agent/master toggles ZATCA feature off for the merchant → receipts become simplified, no stamp.

### I5. Standard vs simplified routing (automatic)
- B2B sale with buyer VAT number and total ≥ 1000 SAR → `standard` (clearance). Otherwise → `simplified` (reporting). No button; decided by the sale core (ZA-06).

---

## J. STAFF / CASHIER & SECURITY

### J1. Create a staff member
1. Merchant opens **Staff** (`/staff`) → **[+ Staff]** → fill name/email, `role` (cashier/manager), assign branch → **[Save]** → provisioning email, `must_change_password` set.
2. Staff logs in, force-resets, resolves to the **merchant's** tenant (shares catalog/customers/sales).

### J2. Per-user permission overrides
1. Open a staff member → **Permissions** → toggle `pos.refund`, `pos.void`, `pos.discount`, `pos.price_override` → **[Save]** (overrides role defaults).

### J3. Enroll MFA/TOTP
1. **Profile** (`/profile`) → **Security** → **[Enable MFA]**.
2. Scan the QR (provisioning URI) in an authenticator app → enter the 6-digit `code` → **[Activate]**.
3. App shows 10 single-use **recovery codes** → **[Download/Copy]** → **[I've saved them]**.

### J4. Login with MFA
1. **Login** with email/password → server returns a 5-min MFA token → **MFA** screen.
2. Enter authenticator `code` → **[Verify]** (separately throttled). Or **[Use recovery code]**.
3. → Access granted.

### J5. Password reset (forgot password)
1. **Login** → **[Forgot password?]** → enter `email` → **[Send reset link]**.
2. ⚠ Always shows "If the email exists, a link was sent" (no enumeration).
3. Click email link → set new password → **[Reset]** → security stamp bumps, all old tokens invalidated.

### J6. Login throttling
- ⚠ Repeated bad logins → HTTP 429 lockout (15 min) across three counters: per (email,IP), per-account (anti-spray), per-IP. UI shows "Too many attempts, try again in N minutes."

### J7. Session management
1. **Profile** → **Sessions** → list of active sessions (device/IP/last seen).
2. **[Revoke]** a single session → that session's `jti` blocklisted instantly.
3. **[Sign out everywhere]** / **[Logout]** → current `jti` revoked.

---

## K. CUSTOMER-FACING

### K1. Customer display second screen
1. Cashier opens **Customer Display** (`/customer-display`) on a second monitor.
2. As items ring at POS, the bilingual, branded screen mirrors the cart via localStorage sync → shows running total, then "Thank you" + QR after payment.

### K2. Customer receives receipt
- Card-paid customer gets a printed Arabic thermal receipt with ZATCA QR; optionally an **emailed** or **SMS** copy (if the receipt feature is enabled).

---

## L. PLATFORM OPS & ADMIN (cross-tier)

### L1. Store settings (per merchant)
1. **Store Settings** (`/store-settings`) → fill CR number, address, business hours, receipt footer → **[Save]**. (Legal business name + VAT live on the `clients` row for fiscal authority.)

### L2. Webhooks
1. **Webhooks** → **[+ Subscription]** → enter `endpoint URL`, pick events (`product.created`, `customer.created`, `shift.closed`, …), copy the generated `HMAC secret` → **[Save]**.
2. **Delivery log** tab → see attempts/status; **[Retry]** a failed delivery.

### L3. Audit log
1. **Audit** (`/audit`) → read-only, append-only, tamper-evident hash-chained list of actions (tenant sees all staff actions; master sees all). Includes failed-auth records.
2. **[Filter]** by user/action/date. No edit/delete (read-only by design).

### L4. Notifications
1. **Notifications** (`/notifications`) bell → list of alerts (low stock, dunning notices, shift events).
2. **[Mark read]** / **[Mark all read]**.

### L5. API usage / rate limiting (opt-in)
1. **API** settings → **[Generate API key]** → metering toggled on.
2. ⚠ Over the token-bucket limit → 429 with `Retry-After`. ⚠ Request > 10MB → rejected by middleware.

---

## M. BILLING — MERCHANT SUBSCRIPTION (Rail 2)

### M1. Merchant adds a card on file
1. **Billing** → **[Add card]** → moyasar.js tokenizes client-side (no PAN to server) → token stored encrypted at rest.

### M2. Subscription charge & dunning
1. Billing scheduler (hourly, if `BILLING_SCHEDULER_ENABLED`) charges the merchant via the **agent's** Moyasar.
2. Success → `subscription_payments` row, `subscription_status = active`, period advances.
3. ⚠ Failure → state machine `active → past_due → dunning → suspended` (configurable retries/grace), bilingual notices sent. Reserve-then-charge `(client_id, period_key)` prevents double-charge.
4. ⚠ Agent hasn't connected Moyasar → charge **fails closed (402)**, period does **not** advance.

### M3. Trials & coupons
1. Merchant in trial sees `trial_end` countdown banner.
2. Agent applies a **coupon** (percentage/fixed, duration) at provisioning → exact Decimal discount on charges.

### M4. Inbound Moyasar webhook
- Payment confirmation webhook → signature-verified (fail-closed) → deduped via `processed_webhook_events` `(source, event_id)` → updates payment status.

---

## N. FRONTEND PREFERENCES (any user)

### N1. Language & RTL
1. Top bar **[Language]** → pick Arabic/English/Hindi/Urdu → Arabic switches layout to RTL (Radix DirectionProvider).

### N2. Theme
1. **[Theme toggle]** → light/dark.

### N3. Command palette
1. Press **⌘K** (or click the command bar) → type to jump to any page/action → Enter.

### N4. Session-expiry & rate-limit toasts
- ⚠ On a 401 the axios client does a single coalesced refresh-and-replay; if it fails → `pos:session-expired` toast → redirect to login. A 429 → `pos:rate-limited` toast.

---

## O. END-TO-END COMPOSITE SCENARIOS

### O1. Brand-new retail merchant, zero to first sale
A4 (agent provisions) → C1/C2 (merchant onboards, tour) → D1–D2 (categories + a few products) → I1 (ZATCA onboard) → F0 (open shift) → **F1 (buy 3 items, card)** → F10 (close shift, Z report). Result: signed ZATCA invoice, stock down, loyalty accrued, drawer reconciled.

### O2. Brand-new restaurant merchant, zero to settled table
A4 with `business_type = restaurant` → C2 → G1 (menu + modifiers + recipe) → G2 (floor) → F0 → **G4 (open table, fire 3 items, KDS bump, per-seat settle with tip + service charge)**. Result: COGS rolled up via BOM, ZATCA invoices per seat, table freed.

### O3. Agent launches their white-label business
A4 (master provisions agent) → B1 (reset) → B2 (connect Moyasar) → **B3 (full branding/style customization)** → B4 (provision first merchant) → B5 (feature overrides) → B6 (buy more slots when full) → B7 (read commission statement).

### O4. Refund-then-reconcile
F1 (original card sale) → F7 (partial refund → credit note → card refund to origin) → F10 (Z report reflects cash_refunds/over-short).

### O5. Omnichannel dinner rush
H2 (aggregator connected) → multiple webhook orders → tableless KDS tickets (G6 single-worker note) → kitchen bumps → auto ZATCA invoices → end-of-night F10 + reports.

### O6. Suspend cascade
A4 → agent active for a while → master toggles agent **[Active] off** → every merchant + staff under that agent instantly blocked at login (J6-style auth denial) → toggle back on restores all.

---

## P. EXHAUSTIVE BUTTON CHECKLIST (quick audit)

Auth: Sign in · Forgot password · Send reset link · Reset · Update password · Verify (MFA) · Use recovery code · Enable MFA · Activate · Download recovery codes · Logout · Sign out everywhere · Revoke session.
Master: New Package · Save/Edit/Archive package · New Agent · Create Agent · Active toggle · Save system settings · Export economics.
Agent: Connect Moyasar · Upload logo · color/radius pickers · font pickers · language · custom domain · Save branding · Restore defaults · Preview as merchant · New Merchant · Create Merchant · feature toggles · Buy more slots · Pay · Download statement.
Catalog: New/Edit category · New Product · Upload image · Weighted/Open-price toggles · Save · New Variant · Import CSV · Confirm import · Export CSV.
Inventory: New Branch · Adjust stock · New Transfer · Dispatch · Receive · New Supplier · New PO · Save draft · Send · Receive PO.
CRM/Promo: New Customer · Marketing consent · Export data · Erase · Configure/Activate loyalty · Issue/Reload/Void/Refund gift card · New discount rule · Generate codes · New promotion · Preview · New Quote · Send · Mark accepted · Convert · New Expense.
POS: Open shift · scan/tap/search add · +/− qty · weight entry · Customer · Pay · Card/Cash/Mada/ApplePay/STCPay/Tabby/Tamara/Transfer/Loyalty/Giftcard tenders · Split · Charge · Apply code · Redeem loyalty · Discount · Edit price · Tip · Service charge · Hold · Recall · Print · Email · SMS · New sale · Refund · Process refund · Void · Pay in · Pay out · Cash drop · X report · Close shift.
Restaurant: New Zone/Table · New Reservation · Seat · No-show · Cancel · Add to waitlist · tap table · add item/modifiers · Send/Fire · Fire course · Bump · Recall · Print bill · Settle · per-seat/per-line select.
ZATCA: Start onboarding · Get compliance CSID · Get production CSID · Enable live submission · Reconcile now · Verify integrity.
Ops: Save store settings · New webhook subscription · Retry delivery · Audit filter · Mark read/all read · Generate API key.
Billing: Add card · (auto dunning) · apply coupon.
Prefs: Language · Theme · ⌘K palette.
