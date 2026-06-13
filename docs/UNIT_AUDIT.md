# POS SaaS — Master Gap Audit Report

*Lead-reviewer consolidation of 18 per-unit audits • Saudi POS SaaS (Foodics/Rewaa/Marn parity target)*
*Generated 2026-06-13 via parallel multi-agent audit (21 agents). Dimensions: feature completeness, functionality, app-wide consistency, design/aesthetics, code cleanliness, dead-code/residuals.*

---

## 1. Executive Summary

### Overall health
The platform is **substantially more built than a façade**, but it is **uniformly "wired core + scaffold periphery."** Almost every unit follows the same shape: a genuine, atomic, well-tested backend slice living in hand-written modules (`sale_core.py`, `production.py`, `restaurant.py`, `tenant.py`, `features.py`), surrounded by auto-generated entity-CRUD routers that are mounted, unauthenticated-or-mis-scoped, and never called by the UI. The fiscal/sale engine, restaurant vertical, and omnichannel ingestion are real achievements. The two systemic risks are (a) **a ZATCA signing path that a real Fatoora gateway would reject**, and (b) **a large unauthenticated/mis-scoped auto-CRUD attack surface** shipped live via blanket auto-router discovery.

### Maturity distribution (18 units)

| Maturity | Count | Units |
|---|---|---|
| **solid** | 3 | U3.4 POS core, U3.5 Pricing, U4.1 Restaurant floor/settle |
| **partial** | 15 | all others |
| **façade / broken** | 0 (unit-level) | but several *slices within* partial units are façades: U3.8 loyalty admin, U5.1 webhook logs, U6.1 storage, U3.7 ZATCA gateway substance |
| **dead** | 0 (unit-level) | substantial dead modules listed in §4 |

No unit is wholly dead or wholly façade, but **four "headline" sub-features are façades hiding behind swallowed errors**: the LoyaltyProgram admin page (4 missing endpoints), WebhookManagement delivery logs, the storage router (500s on every call), and ZATCA gateway submission.

### Cross-cutting themes (most important first)

1. **Auto-generated entity-CRUD scaffolding is mounted live and is the dominant source of risk.** `include_routers_from_package` (main.py:213) auto-registers every `routers/*.py`, so dozens of generated triads ship on the API with **no frontend caller, weak/absent auth, and self-ownership scoping** that contradicts how rows are actually keyed. Concrete severe cases: `routers/packages.py` (unauthenticated create/update/**hard-delete** of platform packages), `routers/agents.py`/`agent_features.py` (any user CRUDs branding rows by user_id), `routers/audit_logs.py` (audit trail is user-writable/deletable), `routers/clients.py`/`client_features.py` GET `/all` (cross-tenant data exposure). This single pattern produces high-severity findings in **U0.2, U1.1, U1.2, U2.1, U3.1, U3.9**.

2. **Tenancy scoping is inconsistent: the good `TenantScope`/`get_owner_id` seam is not applied uniformly.** The canonical sale path correctly maps staff→owning merchant, but several secondary surfaces scope on raw `current_user.id` instead — breaking staff/cashier sub-users and/or hiding their actions. Affected: PO receive (U3.3, staff get 404), payments_gateway (U3.6, cashier 403), audit_logs/api_usage (U3.9, owner can't see staff actions), `require_feature` (U0.2, staff 403 on gated routes). This directly undercuts the recent F-SEC-1 tenant-scoping work.

3. **ZATCA fiscal substance is a façade where it counts.** (U3.7) PIH chain comes from a process-global mutable singleton that bleeds across tenants/requests; the computed ECDSA stamp is never injected into the UBL XML (submitted XML is unsigned); no C14N before hashing; invoice UUID never persisted (submission sends `uuid=""`). Crypto primitives are real but a live Fatoora gateway would reject every invoice after the first.

4. **The permission/RBAC engine exists but has no production data source and no UI.** (U0.2, U3.1) `require_permission` enforces only `pos.refund`/`pos.void`, permission rows are only ever written by `seed_demo.py`/tests, staff `role` strings are never mapped to permission keys, and there is no management UI. Staff creation also never provisions a login (U3.1) — "staff" are contact rows that cannot sign in.

5. **Pervasive frontend↔backend contract drift silently breaks visible features.** Response-shape mismatches render real data as empty/zero with no error: ProductManagement reads `data.products` vs `items` (empty table, U3.2); ExpenseTracking reads `transactions`/`tx.total` vs `items`/`total_amount` (revenue always 0, U3.8); AgentDashboard reads slot fields off the branding payload (Remaining Slots always 0, U2.1); MasterDashboard reads `retail_price_per_client` (renders 0, U1.1); AuditLog reads `user_email`/verb actions the API never returns (dead columns, U3.9); LoyaltyProgram + Webhook logs call non-existent endpoints behind swallowed 404s.

6. **Design-system migration is half-finished.** The petrol/gold re-skin landed on dashboards but multiple pages remain on raw slate/green/red Tailwind, several with no i18n/RTL on an Arabic-first product: PackageManagement, BrandingEditor, SupplierManagement, DiscountManagement, AuditLog, WebhookManagement, CustomerDisplay, ShiftManagement/StaffManagement, the auth gate screens.

7. **atoms.dev / standalone-migration residue persists** across auth (LogoutCallbackPage, SDK-shim `auth.me/login/toLogin`, dead `refreshAccessToken`), the `atomsClient.ts` filename, UserProfile's "Change Password managed by auth provider," and a Chinese-comment storage scaffold.

8. **Market-parity gaps are consistent and predictable:** no always-on billing scheduler, no quote→sale conversion, no loyalty ledger/expiry, no receipt-template designer wired to the renderer, no integrated-terminal UI, no CSV import/export for catalog, no product↔category linkage.

---

## 2. Maturity Table

| Unit | Maturity | One-line verdict |
|---|---|---|
| U0.1 Auth & sessions | partial | Local auth solid; refresh-token flow is dead, two divergent logouts, no brute-force protection. |
| U0.2 Multi-tenancy & permissions | partial | Tenancy seam solid; permission layer half-wired with no prod data source/UI and an orphaned contradictory CRUD scaffold. |
| U0.3 Platform infra | partial | Audit/metering/offline/migrations wired; audit tenancy mismatch, PerformanceMiddleware never registered, placeholder CORS dupe. |
| U1.1 Master: packages/billing/dunning | partial | Billing/dunning/commission solid end-to-end; **orphaned package router with unauthenticated hard-delete**. |
| U1.2 Master: clients & feature flags | partial | Named files are unwired scaffolding; real per-client toggle lives in tenant.py/AgentDashboard and works. |
| U2.1 Agent: reseller & white-label | partial | Branding/provisioning/domains real via a 2nd backend; slot counts always 0; BrandingEditor off-brand; dead agent CRUD. |
| U3.1 Merchant: staff/shifts/cash | partial | Shifts/cash excellent; staff never provisions a login; entire entities/shifts CRUD orphaned. |
| U3.2 Catalog | partial | Products/variants/stock wired; **product list renders empty (shape bug)**; categories table orphaned (never linked). |
| U3.3 Inventory ops | partial | Strong backend (transfers/receive/adjust); **PO create UI 422s**; receive can't land stock; receive mis-scoped. |
| U3.4 POS / sale core | **solid** | Genuine atomic fiscal sale; hold/recall drops variant_id; refund UI shows USD not SAR. |
| U3.5 Pricing | **solid** | Discounts/gift-cards/quotations all wired; feature-gating only on /validate; no quote→sale. |
| U3.6 Payments | partial | Gateway/tender/refund real; standalone router mis-scoped; integrated-terminal has no UI; dead Stripe Checkout class. |
| U3.7 ZATCA & PDF | partial | Crypto real, PDF solid; **fiscal substance broken** (shared-singleton PIH, unsigned XML, no C14N, empty UUID). |
| U3.8 CRM/loyalty/PDPL/expenses | partial | Customers/expenses/PDPL solid; **LoyaltyProgram admin is a façade (4 missing endpoints)**; expense revenue panel zeroed. |
| U3.9 Reporting & audit log | partial | Reporting deep & solid; audit log half-wired, **user-writable/deletable**, page reads a shape backend never returns. |
| U4.1 Restaurant floor/settle | **solid** | Real end-to-end vertical; bill_printed state never set; deplete-stock double-deducts. |
| U4.2 Restaurant KDS/KOT/BOM | partial | Backend solid; **BOM (F-062) has no UI/API client**; combos never deduct stock; KDS recall dead. |
| U5.1 Omnichannel/aggregators/webhooks | partial | Inbound Salla/aggregator solid; outbound webhooks fire 2 of 9 events; logs tab calls a missing endpoint. |
| U5.2 Hardware/printing/display | partial | Thermal core + customer display wired; receipt_templates entity inert (no field reaches renderer). |
| U6.1 Settings/storage/notifications | partial | Notifications + tenant VAT solid; **storage router 500s on every call**; settings env-editor orphaned; UserProfile localStorage-only. |

---

## 3. Critical & High Findings

### CRITICAL

**C1 — ZATCA PIH chain driven by a shared process-global singleton (cross-tenant bleed)** · U3.7 · *functionality*
The module-global `zatca_service = ZATCAService()` (services/production.py:379) holds `_previous_hash` (starts `"0"*64`, :146); `generate_xml_invoice` embeds it into the UBL PIH element (production.py:271) then overwrites it (:373). `sign_transaction` (services/zatca_sale.py:193) manages the *real* per-client chain separately in `creds.pih`/`doc.previous_hash` (:210,:244) and never feeds it to the singleton. The on-chain PIH is therefore whatever the last `generate_xml_invoice` call (any tenant, any concurrent request) left behind — it ≠ the recorded chain, bleeds across tenants, and a gateway validating PIH rejects every invoice after the first.
**Files:** backend/services/production.py, backend/services/zatca_sale.py, backend/routers/zatca.py
**Fix:** Pass the client's real `previous_hash` explicitly into `generate_xml_invoice`; never hold fiscal chain state in a process-global.

**C2 — Computed ECDSA stamp never embedded in the signed XML** · U3.7 · *functionality*
`sign_transaction` hashes the plain UBL string (zatca_sale.py:211) and computes a stamp (:213) that is only stored on the row + QR TLV, never injected into `<ext:UBLExtensions>` (`generate_xml_invoice` emits no signature block). The `signed_xml` POSTed to Fatoora (zatca_sale.py:293) is an **unsigned** document — Phase-2 clearance/reporting requires the enveloped signature.
**Files:** backend/services/zatca_sale.py, backend/services/production.py
**Fix:** Build the XAdES UBLExtensions signature (SignedProperties + ds:Signature with ECDSA value + cert) and inject before submission, or explicitly flag gateway submission as non-functional.

**C3 — Purchase-order create from the UI fails validation (422)** · U3.3 · *functionality*
`SupplierManagement.handleCreatePO` (SupplierManagement.tsx:202-224) POSTs `{supplier_id, supplier_name, status, total_amount, items_count, items, order_date}`; schema `Purchase_ordersData` (purchase_orders.py:24-34) requires `order_number` (no default, NOT NULL model col) → 422. Even if it passed, the body uses `items` but the field is `items_json`, so lines are dropped. Backend tests create POs correctly (test_phase6_po_receive.py:35) — the UI, not the API, is wrong.
**Files:** frontend/src/pages/SupplierManagement.tsx, backend/routers/purchase_orders.py, backend/models/purchase_orders.py
**Fix:** Map the form to the real schema (generate `order_number`, send `items_json` with `product_id`), drop the phantom fields.

**C4 — LoyaltyProgram admin page is a façade; all 4 endpoints are missing** · U3.8 · *functionality*
LoyaltyProgram.tsx calls `/production/loyalty/config` (GET+POST :73-77,:112-116), `/loyalty/balances` (:85-89), `/loyalty/transactions` (:96-100), `/loyalty/adjust` (:129-138). Backend only exposes `/loyalty/earn`, `/loyalty/redeem`, `/loyalty/balance` (singular). Grep returns zero matches for the four. Every call is wrapped in swallowing try/catch, so config Save is a no-op, balances/history are always empty, Adjust does nothing — page reachable at /loyalty (App.tsx:125).
**Files:** frontend/src/pages/LoyaltyProgram.tsx, backend/routers/production.py
**Fix:** Implement the 4 endpoints (config↔loyalty_programs, balances↔loyalty_points, adjust, transactions ledger) or rewire onto real surfaces; stop swallowing 404s.

### HIGH

**H1 — Orphaned duplicate package router with unauthenticated write + hard-delete** · U1.1 · *functionality*
`routers/packages.py` registers full CRUD+batch at `/api/v1/entities/packages`; only GET `/all` is consumed. `create_packages` (:185), `update` (:261), `delete` (:316, hard `db.delete`), list (:86), batch — **no auth dependency at all** — are live via auto-discovery, letting anyone create/modify/**permanently delete** platform packages (which agents/clients reference). The real, master-gated, soft-delete path is in features.py.
**Files:** backend/routers/packages.py, backend/services/packages.py, backend/routers/features.py
**Fix:** Delete packages.py + PackagesService; keep only `normalize_feature_tier`/`parse_feature_tier`; repoint `getPackages()` at the master-gated listing.

**H2 — Scaffold agents/agent_features CRUD are unauthenticated-by-user_id and auto-mounted** · U2.1 · *deadcode/security*
`routers/agents.py`+`agent_features.py` (and services) are generic CRUD at `/api/v1/entities/agents|agent_features` (tell-tale `agentss` plurals), no frontend caller, weaker `user_id`-string tenancy — an exposed surface letting any authenticated user CRUD agent/branding rows by user_id. Live via main.py:213.
**Files:** backend/routers/agents.py, backend/services/agents.py, backend/routers/agent_features.py, backend/services/agent_features.py
**Fix:** Delete the four scaffold files (keep the SQLAlchemy models, used by tenant.py/features.py).

**H3 — Audit trail is user-writable and user-deletable** · U3.9 · *functionality*
`routers/audit_logs.py` exposes POST/PUT/DELETE + batch to any authenticated user (:183,:208,:234,:262,:293,:319), scoped only by ownership — actors can fabricate, edit, and delete their own audit history. (api_usage has the same surface.) Defeats the purpose of a compliance log.
**Files:** backend/routers/audit_logs.py, backend/routers/api_usage.py
**Fix:** Remove all write/delete endpoints; keep only owner/admin-scoped GET; the only writer is the middleware.

**H4 — audit_logs/api_usage ignore the tenant-scope helper; owner can't see staff actions** · U3.9 · *consistency*
Sibling routers use `get_tenant_scope`→`scope.owner_user_id`; audit_logs.py and api_usage.py scope on raw `current_user.id` (audit_logs.py:109,170,194). The middleware records actions under the staff member's `sub` (audit.py:118), so a merchant owner's audit query shows only their own actions; all staff activity is invisible — the inverse of the feature's purpose.
**Files:** backend/routers/audit_logs.py, backend/routers/api_usage.py, backend/middlewares/audit.py, backend/routers/branches.py
**Fix:** Inject `get_tenant_scope`, scope reads to `owner_user_id`, and tag audit rows with the owning merchant.

**H5 — AuditLog.tsx renders against a shape the backend never returns** · U3.9 · *functionality*
Page expects `user_email` (AuditLog.tsx:15-22) and exact-match action verbs (`login`/`create`/…, :24,:52-53,:154-163), but the writer stores verbose `POST /api/v1/entities/products` (audit.py:92) and the model has only `user_id`. User column always `—`, badges always neutral, action filter matches nothing — core columns/filters dead.
**Files:** frontend/src/pages/AuditLog.tsx, backend/middlewares/audit.py, backend/models/audit_logs.py
**Fix:** Resolve `user_id`→email + emit normalized action verbs, or rewrite the page to the real fields.

**H6 — Main product list renders empty (response shape misread)** · U3.2 · *functionality*
`getProductsList()` returns `GET /products/list` body (`ProductListResponse { items, total }`, features.py:134-136) but `ProductManagement.loadProducts()` reads `data?.products || []` (ProductManagement.tsx:176) → always `[]`. The primary catalog table is permanently empty; create/edit/reorder use other endpoints so the page looks alive.
**Files:** frontend/src/pages/ProductManagement.tsx, frontend/src/lib/api.ts, backend/routers/features.py
**Fix:** Read `data?.items`; type the return to catch this at compile time.

**H7 — Categories table is orphaned — never linked to products** · U3.2 · *completeness*
Full categories model/service/router/UI island, but products store free-text `category` (models/products.py:27, no FK), the product form uses a hardcoded `CATEGORIES` array (ProductManagement.tsx:102), and features.py never references categories. A merchant's category tree cannot be assigned to products.
**Files:** backend/models/products.py, backend/routers/features.py, frontend/src/pages/ProductManagement.tsx, CategoryManagement.tsx
**Fix:** Add `category_id` FK + source the product form Select from `getCategories()`, or drop the categories CRUD until consumed.

**H8 — ExpenseTracking revenue/net-profit always zero (shape + field name)** · U3.8 · *functionality*
ExpenseTracking.tsx:68-74 reads `txData.transactions` and reduces on `tx.total`; endpoint returns `items` with `total_amount` (pos.py:982,968). Revenue and Net Profit/Loss cards are permanently wrong.
**Files:** frontend/src/pages/ExpenseTracking.tsx, backend/routers/pos.py
**Fix:** Read `txData.items`, sum `tx.total_amount`.

**H9 — AgentDashboard reads slot counts off the branding payload (Remaining Slots always 0)** · U2.1 · *functionality*
Dashboard computes `remainingSlots` from `branding.client_slots/used_slots` (AgentDashboard.tsx:29-36,245), but `BrandingResponse` (tenant.py:121-137) carries none of these; the real `remaining_slots` returned by GET /agent/clients (:525,541) is discarded (:86). Slot tile and footers render 0/blank for every agent.
**Files:** frontend/src/pages/AgentDashboard.tsx, backend/routers/tenant.py
**Fix:** Read `remaining_slots`/`total` from the clients response (already returned); drop the unused interface fields.

**H10 — Refresh-token flow is a façade; `refreshAccessToken()` never called** · U0.1 · *functionality*
Backend issues refresh tokens and exposes POST /auth/refresh (auth.py:51-72,81-111); frontend stores and implements `refreshAccessToken()` (auth.ts:88-102) but nothing calls it — the axios 401 interceptor clears the token and bounces to /login (atomsClient.ts:64-73). Sessions hard-expire at the 24h access-token boundary; the 7-day refresh token does nothing.
**Files:** frontend/src/lib/auth.ts, frontend/src/lib/atomsClient.ts, frontend/src/contexts/AuthContext.tsx
**Fix:** Wire `refreshAccessToken()` into the 401 interceptor: attempt one refresh + replay before clearing/redirecting.

**H11 — Two divergent logout paths; dashboard logout never revokes the refresh token** · U0.1 · *consistency*
`AuthContext.logout()` sends `refresh_token` and clears both keys; the three dashboards call `client.auth.logout()` (atomsClient.ts:198-206) which POSTs with no body (server never revokes the jti — session resurrectable via /auth/refresh) and leaves `pos_refresh_token` in localStorage.
**Files:** frontend/src/lib/atomsClient.ts, MasterDashboard.tsx, AgentDashboard.tsx, ClientDashboard.tsx
**Fix:** Dashboards call `useAuth().logout()` (or delegate); remove the duplicate.

**H12 — No merchant path maps staff role→permission keys; no permission management UI** · U0.2 · *completeness*
`staff_members.role` is never translated to `permission_key` grant/deny rows; the only writer is seed_demo.py:320/tests. `require_permission` (pos.refund/void) fires only for hand-seeded data; StaffManagement.tsx has no permission UI. A real merchant cannot deny a cashier refund/void/discount through any supported flow.
**Files:** backend/models/staff_members.py, frontend/src/pages/StaffManagement.tsx, backend/dependencies/permissions.py, backend/seed_demo.py
**Fix:** Drive `has_permission` off a role→permission_key default map, or add a staff-permission editor (endpoint + UI) writing rows keyed on staff user_id.

**H13 — Generic permissions CRUD router is orphaned with a contradictory ownership model** · U0.2 · *functionality*
`routers/permissions.py` (note `permissionss` typos) scopes every read/write by `Permissions.user_id == current_user.id` — but `user_id` is the *subject* of a grant, not its owner, so a user can only ever see/edit grants about themselves (opposite of admin-granting-staff). No frontend caller; wired live.
**Files:** backend/routers/permissions.py, backend/services/permissions.py, frontend/src/lib/api.ts
**Fix:** Remove, or replace with an owner-scoped admin endpoint that manages staff permission rows.

**H14 — clients.py / client_features.py are unwired scaffolding, not the real management surface** · U1.2 · *functionality*
Both are generic CRUD at `/api/v1/entities/...`, allowlisted as orphans (test_orphan_routers.py:52-53); service filters on `user_id == current_user.id` (the merchant's own login) so an agent/master can never read/mutate another tenant's clients/flags — structurally incapable. The working toggle is `tenant.py::set_client_feature` + `require_feature`, driven by AgentDashboard.
**Files:** backend/routers/clients.py, backend/routers/client_features.py, backend/routers/tenant.py, backend/services/clients.py
**Fix:** Treat tenant.py + features.py + AgentDashboard as canonical; delete or clearly document the triads.

**H15 — GET `/all` on clients/client_features returns ALL tenants' data unscoped** · U1.2 · *consistency*
clients.py:141 and client_features.py:120 require only `get_admin_user` and call `get_list()` with no `user_id` — every client/flag platform-wide, no agent filter. A cross-tenant exposure path if ever wired.
**Files:** backend/routers/clients.py, backend/routers/client_features.py
**Fix:** Gate master-only or delete (nothing calls it).

**H16 — Integrated SoftPOS terminal feature has no frontend surface** · U3.6 · *completeness*
Backend complete (models/terminals.py, GeideaTerminalGateway, /payments/terminals + /terminal/charge, sale_core honoring `terminal_id`) and api.ts client exists (`registerTerminal`:409, `listTerminals`:424, `chargeTerminal`:434) with **zero callers**; POSTerminal never sends `terminal_id`. The headline integrated-terminal capability is unreachable in-app.
**Files:** frontend/src/lib/api.ts, frontend/src/pages/POSTerminal.tsx, backend/routers/payments_gateway.py
**Fix:** Add a Devices settings page + checkout terminal picker setting `payments[].terminal_id`.

**H17 — Standalone payments router scopes by raw current_user.id (breaks cashier/staff)** · U3.6 · *consistency*
payments_gateway.py scopes every op by `str(current_user.id)` (`_client_for_user`:45-48, register/list/charge), unlike the owner-scoped sale path. A cashier hits 403 on /charge and empty /terminals — diverges from F-SEC-1. Latent only because the UI never calls these.
**Files:** backend/routers/payments_gateway.py, backend/dependencies/tenancy.py, backend/routers/pos.py
**Fix:** Replace per-handler scoping with `Depends(get_owner_id)`.

**H18 — PO receive scopes to current_user.id, not the tenant owner → staff 404** · U3.3 · *consistency*
`receive_purchase_order` filters `Purchase_orders.user_id == str(current_user.id)` (purchase_orders.py:330-331), unlike every CRUD route in the same file and the transfer/adjustment endpoints. A staff cashier who can list POs cannot receive them.
**Files:** backend/routers/purchase_orders.py, backend/dependencies/tenancy.py
**Fix:** Inject `TenantScope`/`get_owner_id` and filter on `owner_user_id`.

**H19 — PO receive cannot land stock from the UI (no product_id on lines)** · U3.3 · *functionality*
Receive keys off `product_id` per `items_json` line (skips None, :257-267), but the create form only collects `product_name` (:497-515), so UI-created POs fall into the "no receivable lines → close with 0 stock" branch (:351-362). `receivePurchaseOrder` is also called with no options, so branch_id/partial receipts (the INV-07 headline) are unreachable.
**Files:** frontend/src/pages/SupplierManagement.tsx, backend/routers/purchase_orders.py
**Fix:** Capture `product_id` on lines; add a receive dialog with branch + per-line quantities.

**H20 — Entire entities/shifts CRUD module is orphaned** · U3.1 · *deadcode*
`routers/shifts.py`+`services/shifts.py` register full CRUD at `/api/v1/entities/shifts`, but the real lifecycle (open/close/movements/reconciliation) is in production.py:549-852 and the UI calls only those. Zero callers for `entities/shifts`/`ShiftsService`; ~370 lines of unused, separately-scoped duplicate endpoints (lets clients PUT/DELETE arbitrary shift fields).
**Files:** backend/routers/shifts.py, backend/services/shifts.py
**Fix:** Delete both (keep models/shifts.py).

**H21 — Staff management never provisions a login** · U3.1 · *functionality*
StaffManagement create/update writes a `Staff_members` row (name/email/phone/role) with no auth User and no password/invite (auth.py has no staff reference). Tenancy resolution matches `Staff_members.email` to an *existing* User.email (tenancy.py:103-118) — but that User must be created elsewhere. Adding a "cashier" produces someone who cannot log in.
**Files:** frontend/src/pages/StaffManagement.tsx, backend/routers/staff_members.py, backend/dependencies/tenancy.py
**Fix:** Create/link a User (temp password or invite token) on staff creation, scoped to the merchant; until then relabel as "staff directory."

**H22 — BOM (F-062) has a full backend but zero frontend reachability** · U4.2 · *completeness*
Recipe endpoints + service + sale-core deduction are built and tested (restaurant.py:1414-1478, sale_core.py:593), but there is **no BOM api.ts client and no UI** — a merchant can never define a recipe in-app; depletion only fires for raw-API-seeded recipes.
**Files:** frontend/src/pages/MenuBuilder.tsx, frontend/src/lib/api.ts, backend/routers/restaurant.py
**Fix:** Add BOM client functions + a recipe editor (product detail or MenuBuilder tab).

**H23 — Combo lines never deduct component stock at settle** · U4.2 · *functionality*
Combo lines are created with `product_id=None` (restaurant.py add_item:424-444), so settle's `_cart_lines` carries None and sale_core skips inventory + BOM for them. Selling a combo charges the bundle but decrements **no** stock and routes nothing to the kitchen; `Combos.components` is used only for a strike-through display. Silently oversells.
**Files:** backend/services/restaurant.py, backend/services/sale_core.py
**Fix:** Expand combo lines into component products (id + qty) for deduction/KDS at settle, or document as non-stock bundles.

**H24 — WebhookManagement 'Delivery Logs' tab calls a non-existent endpoint** · U5.1 · *functionality*
WebhookManagement.tsx:105-111 fetches `GET /production/webhooks/logs` — no such route exists (only POST /webhooks/test). Always 404s, swallowed (:112), tab renders "No delivery logs" forever; dispatch outcomes are never persisted (result dict discarded).
**Files:** frontend/src/pages/WebhookManagement.tsx, backend/routers/production.py
**Fix:** Add a `webhook_deliveries` table + GET route, or remove the tab and "Deliveries Today" stat.

**H25 — 7 of 9 advertised webhook events are never fired** · U5.1 · *completeness*
UI offers 9 events (:47-57) but `fire_event_background` is invoked only for `sale.completed` (pos.py:713) and `refund.created` (pos.py:1529). Subscribers to shift/product/customer/inventory events silently never receive deliveries. (Compounded by a name mismatch: backend fires `refund.created`, UI offers `sale.refunded`.)
**Files:** frontend/src/pages/WebhookManagement.tsx, backend/routers/pos.py, backend/services/production.py
**Fix:** Fire the remaining events at source, or trim AVAILABLE_EVENTS to what's emitted; reconcile the refund event name.

**H26 — receipt_templates entity is a disconnected CRUD scaffold — no field reaches the renderer** · U5.2 · *functionality*
The renderer (escpos.py) never loads a template: labels hardcoded in `_L` (:48-78), QR always emitted (:499), paper fixed at 576px/80mm (:45), no font_size/logo/header path. All 11 settable template knobs are ignored at print time (test_orphan_routers.py:64 flags it as a wire-up gap).
**Files:** backend/services/escpos.py, backend/routers/receipt_templates.py, backend/models/receipt_templates.py
**Fix:** Wire the default template into build_receipt/build_kot (at minimum header/footer/logo/show_qr/font_size), or drop the CRUD entity.

**H27 — Storage router is a dead façade — StorageService always raises on init** · U6.1 · *functionality*
services/storage.py:31-32 reads `settings.oss_service_url`/`oss_api_key`, neither of which exists on Settings (config.py `extra="ignore"`), so `StorageService()` raises AttributeError → all 8 storage endpoints return 500 unconditionally. No frontend caller; allowlisted "wire-later AG-07."
**Files:** backend/services/storage.py, backend/routers/storage.py, backend/core/config.py
**Fix:** Add the config keys (degrade to intended ValueError) + a caller, or delete router+service+schemas.

**H28 — Hold/recall loses variant_id and open-price** · U3.4 · *functionality*
`handleHold` maps cart lines without `variant_id`/open-price unitPrice; `handleRecall` rebuilds lines as `{product, quantity, key: cartKeyFor(product_id)}` (POSTerminal.tsx:296-339). A held variant SKU returns as a plain product → execute_sale deducts the **parent** product's stock (sale_core.py:570-592), variant siblings collapse to one key, open-price reverts to catalog. Backend round-trips items_json verbatim, so this is a frontend serialization fix.
**Files:** frontend/src/pages/POSTerminal.tsx, frontend/src/lib/api.ts
**Fix:** Carry variant_id + unitPrice through hold→items_json→recall and key with `cartKeyFor(product_id, variant_id)`.

---

## 4. Dead Code & Residuals (consolidated)

### Auto-generated entity-CRUD scaffolds (orphaned, often mis-scoped — mounted live via main.py:213)
- `routers/packages.py` + `services/packages.py` PackagesService — unauthenticated CRUD + hard-delete; keep only `normalize/parse_feature_tier`. *(U1.1)*
- `routers/agents.py` + `services/agents.py`, `routers/agent_features.py` + `services/agent_features.py` — keep the SQLAlchemy models. *(U2.1)*
- `routers/clients.py` + `client_features.py` (+ services' `get_by_field`/`list_by_field`/`check_ownership`) — orphan-allowlisted; superseded by tenant.py. *(U1.2)*
- `routers/permissions.py` + `services/permissions.py` (+ `data_models/permissions.json`) — contradictory self-ownership scoping. *(U0.2)*
- `routers/shifts.py` + `services/shifts.py` — superseded by production.py. *(U3.1)*
- `routers/api_usage.py` + `services/api_usage.py` — served by metering middleware + production.py stats. *(U3.9)*
- `routers/loyalty_points.py` + `loyalty_programs.py` — orphan-allowlisted; loyalty admin page hits non-existent paths instead. *(U3.8)*
- `routers/categories.py` + `services/categories.py` + `models/categories.py` — fully built, unconsumed (orphaned island). *(U3.2)*
- Entity-triad `routers/products.py` (overlaps features.py), `routers/transactions.py` write methods (hard-disabled), discounts/quotations `/all` cross-tenant endpoints, branches/suppliers/purchase_orders `/all` + `check_ownership`/`get_by_field`/`list_by_field` helpers, staff_members `/all`. *(U3.2, U3.4, U3.5, U3.3, U3.1)*
- `data_models/*.json` generator artifacts (permissions, clients, client_features, categories, products, webhooks) — no runtime use.
- Pervasive `…ss` double-plural naming + copy-paste docstrings across all generated routers/services.

### atoms.dev / standalone-migration residue
- `frontend/src/pages/LogoutCallbackPage.tsx` — orphaned, unrouted redirect splash. *(U0.1)*
- `frontend/src/lib/auth.ts:refreshAccessToken` — implemented, never called. *(U0.1)*
- `frontend/src/lib/atomsClient.ts` `auth.me`/`auth.login`/`auth.toLogin` — unused SDK-shim methods; filename itself is migration cruft (rename → apiClient.ts). *(U0.1, U3.3)*
- `UserProfile.tsx` Change Password block (~:198-206) — "Managed by authentication provider" leftover. *(U6.1)*
- `frontend/src/api/settings.ts` (settingsApi) — exported, imported nowhere; backend `routers/settings.py` allowlisted orphan (.env editor). *(U6.1)*
- `services/storage.py:191` Chinese comment `统一的 OSS 服务请求方法` + wrong return annotation + copy-paste log strings. *(U6.1)*

### Dead/inert backend
- `services/payment.py` PaymentService + CheckoutSession* models (Stripe Checkout) — only `initialize_stripe` is used (subscription_billing.py:56). *(U3.6)*
- `middlewares/production.py:157-204` PerformanceMiddleware — defined, never registered → `performance_monitor` stays empty. *(U0.3)*
- `middlewares/production.py:210-245` `get_cors_config` — duplicate with `yourdomain.com` placeholders; core/cors.py is source of truth. *(U0.3)*
- `pos.py:224-264` `generate_zatca_tlv`/`generate_zatca_hash` — legacy in-router helpers superseded by services.zatca_sale. *(U3.4)*
- `routers/zatca.py::sign_invoice` — divergent duplicate signer, reachable only via idempotency early-return. *(U3.7)*
- `services/restaurant.py:363 count_tables` — no callers. *(U4.1)*
- `services/escpos.py`/`receipt_templates.py` `get_by_field`/`list_by_field` — unused. *(U5.2)*
- `TenantScope.is_master`/`is_unrestricted` (tenancy.py:56-63) — never referenced. *(U0.2)*

### Inert schema fields / dead UI bindings
- `Permissions.role` (NOT NULL, ignored by has_permission). *(U0.2)*
- `ZatcaDocuments.invoice_uuid` — read on submit, never written by non-test code. *(U3.7)*
- `webhooks.last_triggered`/`failure_count`, WebhookItem.`last_status` — declared, never written/rendered. *(U5.1)*
- DiscountManagement `used_count` (API only returns `usage_count` → Total Uses always 0). *(U3.5)*
- AgentDashboard `Branding.client_slots/used_slots/package_type`; AgentLandingPage `tagline`/`max_clients`/`active_clients`; unused `Eye`/`TrendingUp` imports. *(U2.1)*
- `frontend/public/sw.js:9` `/manifest.webmanifest` in SHELL — file does not exist (voids the whole `addAll`). *(U0.3)*
- KDS.tsx recall button (gated on `status==='bumped'`, but board only holds active cards → never renders); api.ts `attachModifierGroup`/`detachModifierGroup` exported, no caller. *(U4.2)*
- `'restaurant'` FEATURE_KEY (gated by business_type, never via require_feature); `'bill_printed'` table state (rendered/translated, never assigned). *(U1.2, U4.1)*
- Note: the audit brief's `frontend/src/lib/giftCards.ts` does not exist — wrappers live in api.ts. *(U3.5)*

---

## 5. Missing Features (consolidated, by tier/vertical, prioritized)

### P0 — Compliance / correctness blockers
- **ZATCA:** C14N canonicalization before hashing; enveloped XAdES/UBLExtensions signature in the XML; persisted invoice UUID matching `cbc:UUID`; per-client (not singleton) PIH; verification against a live Fatoora sandbox; in-app onboarding wizard (CSR→OTP→production CSID). *(U3.7)*
- **Audit:** append-only/tamper-evident storage; merchant-admin visibility of staff actions. *(U3.9, U0.3)*

### P1 — Core merchant workflows that are broken or unreachable
- Staff login provisioning (PIN/passcode or email invite) + enforced per-role permissions + a permission-management UI. *(U3.1, U0.2)*
- Valid, receivable PO create + receive-into-branch/partial-receipt UI. *(U3.3)*
- Working loyalty config/balances/adjust/history (4 missing endpoints) + a points-movement ledger + expiry. *(U3.8)*
- Product↔category linkage; BOM recipe-editor UI; combo component stock deduction; product↔modifier-group attach UI. *(U3.2, U4.2)*
- Refresh-token silent-refresh; single correct logout; login brute-force protection. *(U0.1)*
- Receipt-template designer wired to the renderer + 58mm support + saved/selected printer + per-station routing. *(U5.2)*
- Integrated SoftPOS terminal UI (register/list/checkout picker). *(U3.6)*
- Outbound webhook delivery-log persistence + emission of all advertised events. *(U5.1)*

### P2 — Market-parity gaps (Foodics/Rewaa/Marn)
- Always-on billing scheduler (dunning/retry auto-sweep); proration/mid-cycle plan changes; coupons/trials; agent/master commission statements. *(U1.1)*
- Quote→sale conversion + quotation status lifecycle; gift-card void/reload + refund-to-card; advanced discounts (line/category/BOGO/auto-promotions); unique discount codes. *(U3.5)*
- Stock-transfer history endpoint/UI; two-phase transfer; branch is_main UI; supplier VAT number; catalog CSV import/export; product images; modifiers/combos in retail catalog; per-branch variant stock; soft-delete products. *(U3.3, U3.2)*
- Restaurant: reservations/waitlist; per-seat/partial settlement; in-app thermal print of proforma/receipt; tip entry on settle dialog; KDS bumped-card/undo view. *(U4.1, U4.2)*
- Cash drawer change-due helper; reprint past receipts; price/stock check. *(U3.4)*
- Email/SMS/push notification delivery honoring UserProfile prefs; persisted per-user profile; merchant store-settings screen (VAT/CR, receipt footer, branch profile, hours); working object storage/exports. *(U6.1, U3.9)*
- MFA; password reset/forgot-password; active-session management; password complexity policy. *(U0.1)*

---

## 6. Recommended Review Order / Next Actions

**Sprint 1 — Security & compliance (highest blast radius, do first):**
1. **Purge/secure the auto-CRUD attack surface.** Delete or master-gate the orphaned scaffolds in one sweep: packages, agents/agent_features, clients/client_features, permissions, shifts, api_usage; remove audit_logs write/delete endpoints. This closes H1, H2, H3, H13, H14, H15, H20 and most of §4 at once. Consider replacing blanket `include_routers_from_package` with an explicit allowlist so future generated routers don't auto-ship. *(U1.1, U2.1, U1.2, U0.2, U3.1, U3.9)*
2. **Fix ZATCA fiscal substance** (C1, C2, canonicalization, invoice UUID). Until done, the product cannot legally clear invoices — treat gateway submission as non-functional and gate it. *(U3.7)*
3. **Unify tenancy scoping** on `get_owner_id`/`TenantScope` for PO receive, payments_gateway, audit_logs/api_usage, and `require_feature` (H4, H17, H18, U0.2 feature-gate). Tag audit rows with the owning merchant. *(U3.3, U3.6, U3.9, U0.3)*

**Sprint 2 — Make visible features actually work (cheap, high-trust wins):**
4. **Contract-drift one-liners:** fix the response-shape/field bugs that silently zero out real UIs — ProductManagement (H6), ExpenseTracking (H8), AgentDashboard slots (H9), MasterDashboard price, AuditLog shape (H5). Add typed API return signatures to prevent recurrence. *(U3.2, U3.8, U2.1, U1.1, U3.9)*
5. **Stop the façades from lying:** remove swallowed-error catches so missing endpoints surface; then implement or delete the LoyaltyProgram endpoints (C4), webhook delivery logs (H24), storage (H27). *(U3.8, U5.1, U6.1)*
6. **POS data-integrity:** hold/recall variant_id (H28), combo component deduction (H23) — both silently corrupt stock.

**Sprint 3 — Close core merchant workflows:**
7. Staff login provisioning + role→permission mapping + permission UI (H12, H21) — unblocks the entire RBAC engine that already exists.
8. PO create/receive UI (C3, H19); product↔category linkage (H7); BOM UI (H22); auth refresh/logout/brute-force (H10, H11).

**Sprint 4 — Parity & polish:**
9. Receipt-template designer wiring (H26), integrated-terminal UI (H16), webhook event emission (H25), billing scheduler, quote→sale.
10. **Design-system sweep** across the remaining slate/green pages with i18n/RTL: PackageManagement, BrandingEditor, SupplierManagement, DiscountManagement, AuditLog, WebhookManagement, CustomerDisplay, Shift/StaffManagement, auth gates.

**Rationale for ordering:** the auto-CRUD purge and tenancy unification are *subtractive and low-risk* yet eliminate the most high/critical findings per unit of effort; ZATCA is the only true compliance blocker; the contract-drift fixes are near-zero-cost and restore trust in features that already exist; everything else is additive feature work best done once the foundation is consistent. The three **solid** units (U3.4, U3.5, U4.1) need only minor cleanup and should not be touched first.
