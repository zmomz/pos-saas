# PRD — Platform Remediation (Master Gap Audit, C1–C4 + H1–H28)

> **Scope:** the full `docs/UNIT_AUDIT.md` consolidation — 4 critical + 28 high findings across 18 units · **Status:** OPEN · **Bar:** Foodics / Rewaa / Marn parity, localized for Saudi (Arabic-first, RTL, ZATCA Phase-2). This PRD is self-contained — acceptance criteria are inline per finding.
>
> Source: `docs/UNIT_AUDIT.md` (2026-06-13, 21-agent parallel audit). Implementation order follows the audit's §6 sprint plan: **Sprint 1** security & compliance (subtractive, highest blast radius) → **Sprint 2** make-visible-features-work (cheap contract-drift fixes) → **Sprint 3** close core merchant workflows → **Sprint 4** parity & polish.
>
> Finding IDs (C1–C4, H1–H28) are preserved verbatim so each user story and acceptance criterion is traceable back to the audit. The three **solid** units (U3.4 POS core, U3.5 Pricing, U4.1 Restaurant) get only the minor cleanups listed and must not be refactored first.

---

## Problem Statement

The platform is **substantially built — not a façade** — but it is uniformly "wired core + scaffold periphery." Almost every unit is a genuine, atomic, tested backend slice surrounded by auto-generated entity-CRUD routers that are mounted, mis-scoped or unauthenticated, and never called by the UI. From the people who depend on it:

- **A platform operator is exposed.** Blanket auto-router discovery (`main.py:213`) ships dozens of generated CRUD triads live. Anyone can create/modify/**hard-delete** platform packages, fabricate/edit/delete their own audit trail, and CRUD branding rows by `user_id` — all with weak or absent auth. This single pattern is the dominant source of high-severity findings.
- **A merchant owner can't trust tenancy.** The good `TenantScope`/`get_owner_id` seam isn't applied uniformly: PO-receive 404s for staff, payments-gateway 403s a cashier, and the owner's audit query shows only their own actions while *all staff activity is invisible* — the inverse of the feature's purpose.
- **A merchant can't legally clear an invoice.** The ZATCA path has real crypto primitives but broken fiscal substance: a process-global PIH singleton bleeds across tenants, the computed ECDSA stamp is never injected into the submitted XML (it goes out **unsigned**), there's no C14N before hashing, and the invoice UUID is never persisted. A live Fatoora gateway rejects every invoice after the first.
- **A merchant stares at features that silently lie.** Response-shape drift renders real data as empty/zero with no error: the main product list is permanently empty, expense revenue/net-profit is always 0, agent "Remaining Slots" is always 0, the audit-log user column is always `—`. The LoyaltyProgram admin page, the webhook delivery-logs tab, and the storage router are façades hiding behind swallowed 404s/500s.
- **A merchant can't complete core workflows.** Adding a "cashier" creates a contact row that cannot log in; there's no role→permission mapping and no permission UI; PO create 422s and receive can't land stock; loyalty config/balances/adjust/history all call non-existent endpoints; BOM recipes and combo stock deduction silently oversell.
- **The product looks half-finished.** The petrol/gold re-skin landed on dashboards but many pages remain raw slate/green/red Tailwind with no i18n/RTL on an Arabic-first product; atoms.dev migration residue lingers across auth, filenames, and comments.

Net effect: the foundation is real but **inconsistent and partly unsafe**, and several headline features are unreachable or actively misreport data.

## Solution

Remediate the audit end to end in four sprints, ordered so the *subtractive, low-risk* security/compliance work lands first and the *additive* feature work lands on a consistent foundation.

From the user's perspective, after this ships:

- **The attack surface is gone.** Every orphaned auto-CRUD scaffold is deleted or master-gated in one sweep; the audit trail is append-only (middleware-written, GET-only); blanket router discovery is replaced with an explicit allowlist so future generated routers can't auto-ship.
- **Tenancy is uniform.** Every secondary surface scopes on the owning merchant via `get_owner_id`/`TenantScope`; staff/cashiers can do everything their role allows; owners see all their staff's actions and audit history.
- **ZATCA is real or honestly gated.** Per-client PIH chaining, an enveloped XAdES signature inside the UBL, C14N before hashing, a persisted invoice UUID, and verification against the Fatoora sandbox — or, until done, gateway submission is explicitly flagged non-functional.
- **Visible features tell the truth.** The contract-drift one-liners are fixed and API return types are tightened so they can't regress; swallowed-error catches are removed so missing endpoints surface; the LoyaltyProgram/webhook-logs/storage façades are either implemented or removed.
- **Core merchant workflows close.** Staff get a real login + per-role permissions + a management UI; PO create/receive works into a branch with partial receipts; loyalty config/ledger/expiry works; product↔category, BOM recipe editor, combo deduction, modifier attach all reach the UI; auth gets silent refresh, one correct logout, and brute-force protection.
- **The product looks finished.** The remaining slate/green pages are migrated to brand tokens with full i18n/RTL; atoms.dev residue is purged.

Every new or touched screen renders its loading / empty / error / permission / offline states, uses brand tokens (never hardcoded styling), is translated across all four languages with RTL verified, and **every fiscal/kitchen printable renders in Arabic regardless of UI language.**

---

## User Stories

### Sprint 1 — Security & compliance (do first; subtractive, highest blast radius)

#### Auto-CRUD attack-surface purge

1. As a platform operator, I want the orphaned duplicate `packages` router deleted, so that no one can create/modify/**hard-delete** platform packages through an unauthenticated route (H1).
2. As a platform operator, I want the scaffold `agents`/`agent_features` CRUD routers deleted (keeping the SQLAlchemy models), so that no authenticated user can CRUD agent/branding rows by `user_id` (H2).
3. As a platform operator, I want all write/delete endpoints removed from `audit_logs` and `api_usage`, so that actors can no longer fabricate, edit, or delete their own audit history; only owner/admin-scoped GET remains and the middleware is the sole writer (H3).
4. As a platform operator, I want the generic `permissions` CRUD router removed (or replaced with an owner-scoped admin endpoint), so that its contradictory self-ownership scoping can't ship (H13).
5. As a platform operator, I want `clients`/`client_features` scaffolds deleted or clearly documented as superseded, so that the real toggle in `tenant.py` is the single source of truth (H14).
6. As a platform operator, I want the `GET /all` endpoints on `clients`/`client_features` gated master-only or removed, so that no route can ever return all tenants' data unscoped (H15).
7. As a platform operator, I want the entire `entities/shifts` CRUD module deleted (keeping the model), so that clients can't PUT/DELETE arbitrary shift fields outside the real lifecycle in `production.py` (H20).
8. As a platform operator, I want blanket `include_routers_from_package` replaced with an explicit allowlist, so that a newly-generated router cannot silently auto-ship on the API.
9. As a maintainer, I want the dead generator artifacts removed (`data_models/*.json`, double-plural `…ss` routers/services, copy-paste docstrings), so that the codebase stops advertising surface that isn't real.
10. As a maintainer, I want every deletion reflected in `tests/test_orphan_routers.py` (moved to `REMOVED_BACKEND`, allowlist shrunk), so that any removed scaffold reappearing is caught forever.

#### Tenancy unification

11. As a merchant owner, I want PO-receive scoped to the tenant owner, so that a staff cashier who can list POs can also receive them (no 404) (H18).
12. As a cashier, I want the payments-gateway router scoped via `get_owner_id`, so that I'm not 403'd on `/charge` and don't see an empty `/terminals` (H17).
13. As a merchant owner, I want `audit_logs`/`api_usage` to scope reads on `owner_user_id` and audit rows tagged with the owning merchant, so that I can see all my staff's actions instead of only my own (H4).
14. As a staff member, I want `require_feature` to resolve my owning merchant's entitlements, so that I'm not 403'd on gated routes my merchant has paid for.

#### ZATCA fiscal substance

15. As a merchant, I want the PIH chain driven by my client's real `previous_hash` (never a process-global singleton), so that my on-chain PIH matches my recorded chain and doesn't bleed across tenants/requests (C1).
16. As a merchant, I want the computed ECDSA stamp embedded as an enveloped XAdES signature inside `<ext:UBLExtensions>`, so that the XML submitted to Fatoora is actually signed (C2).
17. As a merchant, I want the UBL canonicalized (C14N) before hashing, so that the hash the gateway recomputes matches mine.
18. As a merchant, I want the invoice UUID persisted and sent as `cbc:UUID`, so that submission no longer sends `uuid=""`.
19. As a merchant, I want my invoices verified against a live Fatoora sandbox, so that I have evidence clearance actually works before going live.
20. As a merchant, I want an in-app onboarding wizard (CSR → OTP → production CSID), so that I can provision ZATCA credentials without raw API calls.
21. As a compliance officer, I want gateway submission explicitly flagged non-functional and gated until C1/C2/C14N/UUID are done, so that no one believes invoices are clearing when they aren't.
22. As a compliance officer, I want the audit log to be append-only / tamper-evident, so that the compliance trail can be trusted (P0 Audit).

### Sprint 2 — Make visible features actually work (cheap, high-trust)

23. As a merchant, I want ProductManagement to read `data.items`, so that the main catalog table shows my products instead of being permanently empty (H6).
24. As a merchant, I want ExpenseTracking to read `items` and sum `total_amount`, so that Revenue and Net Profit/Loss are correct instead of always 0 (H8).
25. As an agent, I want AgentDashboard to read `remaining_slots`/`total` from the clients response, so that the slot tile and footers show real counts instead of 0 (H9).
26. As a master operator, I want MasterDashboard to read the real per-client price field, so that it renders the actual figure instead of 0 (U1.1 contract drift).
27. As a merchant, I want AuditLog to resolve `user_id`→email and normalized action verbs (or be rewritten to the real fields), so that the user column, badges, and action filter work (H5).
28. As a developer, I want typed API return signatures on the drift-prone endpoints, so that response-shape mismatches fail at compile time and can't silently zero a UI again.
29. As a merchant, I want swallowed-error catches removed so that a missing endpoint surfaces as an error instead of an empty/inert panel (C4, H24, H27).
30. As a merchant, I want a working LoyaltyProgram admin: config (GET/POST), balances, transactions ledger, and adjust — the 4 missing endpoints implemented (or rewired onto real surfaces) (C4).
31. As a merchant, I want the WebhookManagement "Delivery Logs" tab backed by a real `webhook_deliveries` table + GET route, or the tab and "Deliveries Today" stat removed, so that it stops 404ing forever (H24).
32. As a merchant, I want the storage router to either work (config keys + a caller) or be deleted, so that it stops returning 500 on every call (H27).
33. As a cashier, I want hold/recall to carry `variant_id` and open-price through `items_json` and key on `cartKeyFor(product_id, variant_id)`, so that a held variant SKU doesn't deduct the parent's stock or revert to catalog price (H28).
34. As a merchant, I want combo lines expanded into component products (id + qty) at settle, so that selling a combo decrements component stock and routes to the kitchen instead of silently overselling (H23).

### Sprint 3 — Close core merchant workflows

35. As a merchant owner, I want creating a staff member to provision/link a login (temp password or invite token) scoped to my merchant, so that a "cashier" can actually sign in; until then the screen is honestly relabeled "staff directory" (H21).
36. As a merchant owner, I want `staff_members.role` mapped to permission keys via a default role→permission map (or a staff-permission editor), so that I can deny a cashier refund/void/discount through a supported flow (H12).
37. As a merchant owner, I want a permission-management UI, so that the existing RBAC engine (`require_permission`) has a production data source and is configurable.
38. As a merchant, I want PO create to map to the real schema (generate `order_number`, send `items_json` with `product_id`), so that creating a PO from the UI no longer 422s and lines aren't dropped (C3).
39. As a merchant, I want PO lines to capture `product_id` and a receive dialog with branch + per-line quantities, so that receiving lands stock and partial/branch receipts (the INV-07 headline) are reachable (H19).
40. As a merchant, I want products linked to a category via `category_id` FK with the product form sourced from `getCategories()` (or the categories CRUD dropped), so that my category tree can actually be assigned to products (H7).
41. As a merchant, I want a BOM recipe editor (client functions + UI in product detail / MenuBuilder), so that I can define a recipe in-app and depletion fires for real (H22).
42. As a merchant, I want a product↔modifier-group attach UI, so that the existing `attach/detachModifierGroup` clients have a caller.
43. As a returning user, I want `refreshAccessToken()` wired into the 401 interceptor (attempt one refresh + replay before redirecting), so that my 7-day refresh token actually keeps me signed in past the 24h access boundary (H10).
44. As a user, I want a single correct logout that revokes the refresh token, so that the dashboards stop leaving a resurrectable session (H11).
45. As a platform operator, I want login brute-force protection, so that credential-stuffing is throttled.
46. As a merchant, I want a loyalty points-movement ledger with expiry, so that balances are auditable and points age out (P1 loyalty).

### Sprint 4 — Parity & polish

47. As a merchant, I want a receipt-template designer wired to the renderer (at minimum header/footer/logo/show_qr/font_size), plus 58mm support and saved/selected printer + per-station routing, so that template knobs actually affect printed output (H26).
48. As a merchant, I want an integrated SoftPOS terminal UI — a Devices settings page + a checkout terminal picker setting `payments[].terminal_id`, so that the complete terminal backend is reachable in-app (H16).
49. As a subscriber, I want the remaining advertised webhook events fired at source (or `AVAILABLE_EVENTS` trimmed to what's emitted), with the `refund.created`/`sale.refunded` name reconciled, so that subscribers actually receive the deliveries they signed up for (H25).
50. As a master operator, I want an always-on billing scheduler (dunning/retry auto-sweep), proration/mid-cycle changes, coupons/trials, and commission statements, so that billing runs without manual triggers (P2 billing).
51. As a merchant, I want quote→sale conversion + quotation status lifecycle, gift-card void/reload + refund-to-card, advanced discounts (line/category/BOGO/auto-promotions), and unique discount codes, so that pricing matches market parity (P2 pricing).
52. As a merchant, I want stock-transfer history, two-phase transfer, branch `is_main` UI, supplier VAT number, catalog CSV import/export, product images, retail modifiers/combos, per-branch variant stock, and soft-delete products (P2 inventory/catalog).
53. As a restaurant, I want reservations/waitlist, per-seat/partial settlement, in-app thermal print of proforma/receipt, tip entry on settle, and a KDS bumped-card/undo view (P2 restaurant).
54. As a cashier, I want a cash-drawer change-due helper, reprint past receipts, and a price/stock check (P2 POS).
55. As a user, I want email/SMS/push notification delivery honoring UserProfile prefs, a persisted per-user profile, a merchant store-settings screen (VAT/CR, receipt footer, branch profile, hours), and working object storage/exports (P2 settings).
56. As a user, I want MFA, password reset/forgot-password, active-session management, and a password-complexity policy (P2 auth).
57. As an Arabic-first user, I want the remaining slate/green pages migrated to brand tokens with full i18n/RTL — PackageManagement, BrandingEditor, SupplierManagement, DiscountManagement, AuditLog, WebhookManagement, CustomerDisplay, Shift/StaffManagement, the auth gates.
58. As a maintainer, I want the atoms.dev residue purged: `LogoutCallbackPage`, the dead `refreshAccessToken` (once superseded by H10's wiring), the `auth.me/login/toLogin` SDK shims, `atomsClient.ts`→`apiClient.ts` rename, the UserProfile "Change Password managed by auth provider" block, the Chinese-comment storage scaffold, and the `settingsApi`/`.env` editor orphan.

### Cross-cutting (apply throughout)

59. As a merchant owner, I want every line edit / receive / charge / audit read across all touched surfaces owner-scoped, so that one tenant can never see or mutate another's data (SEC consistency).
60. As an Arabic-first user, I want every new or touched screen to render loading/empty/error/permission/offline states with brand tokens and full i18n/RTL, so that the product is consistent end to end.

---

## Implementation Decisions

### Router discovery & the auto-CRUD purge (Sprint 1)
- **Replace blanket discovery with an explicit allowlist.** `include_routers_from_package(app, "routers")` (`main.py:213`) currently mounts every `routers/*.py` exposing `router`/`admin_router`. Change to an explicit registration list (or a discovery pass that consults a maintained allowlist) so a generated router cannot auto-ship without a conscious decision.
- **Delete, don't disable.** For the genuinely orphaned scaffolds — `packages.py`+`PackagesService` (keep only `normalize_feature_tier`/`parse_feature_tier`), `agents.py`/`agent_features.py`+services (keep SQLAlchemy models), `shifts.py`+`ShiftsService` (keep `models/shifts.py`), `permissions.py`+service+`data_models/permissions.json`, `clients.py`/`client_features.py` — remove the files outright and record them in `REMOVED_BACKEND`.
- **Audit/metering routers become read-only.** `audit_logs.py` and `api_usage.py` keep only owner/admin-scoped GET; all POST/PUT/DELETE/batch endpoints are removed. The audit middleware remains the sole writer.
- **`getPackages()` repoints** at the master-gated listing in `features.py`; the soft-delete, master-gated path there is canonical.
- **The orphan-lint test is the contract.** Each deletion must update `tests/test_orphan_routers.py`: move the file path into `REMOVED_BACKEND`, drop its `ALLOWLIST` entry. The test enforces both that removed scaffolds stay removed and that the allowlist shrinks honestly.

### Tenancy seam (Sprint 1)
- **One seam everywhere:** `dependencies/tenancy.py::get_owner_id` / `get_tenant_scope` / `TenantScope`. Replace per-handler `str(current_user.id)` scoping in `payments_gateway.py` (`_client_for_user`), `purchase_orders.py::receive_purchase_order`, `audit_logs.py`, and `api_usage.py` with `Depends(get_owner_id)` and filter on `owner_user_id`.
- **Audit rows carry the owning merchant.** The audit middleware (`middlewares/audit.py`) tags each row with the owning merchant (resolved via the tenant scope), not just the actor's `sub`, so owner queries surface staff actions.
- **`require_feature`** resolves entitlements against the owning merchant so staff aren't 403'd.

### ZATCA fiscal substance (Sprint 1)
- **No fiscal state in process globals.** Remove reliance on the module-global `zatca_service` singleton's `_previous_hash`. `generate_xml_invoice` takes the client's real `previous_hash` as an explicit parameter; the per-client chain in `creds.pih`/`doc.previous_hash` is the single source of truth.
- **Enveloped signature.** `generate_xml_invoice` emits a `<ext:UBLExtensions>` XAdES block (SignedProperties + `ds:Signature` with the ECDSA value + cert); `sign_transaction` injects the signature before the document is POSTed to Fatoora. The submitted `signed_xml` must be the signed document, not the plain UBL.
- **C14N before hashing.** Canonicalize the UBL prior to computing the invoice hash so the gateway's recomputed hash matches.
- **Persist the UUID.** `ZatcaDocuments.invoice_uuid` is written at generation time and sent as `cbc:UUID`; submission never sends `uuid=""`.
- **Gating.** Until C1/C2/C14N/UUID land and pass a Fatoora-sandbox check, gateway submission is feature-flagged non-functional rather than silently emitting invalid invoices. Remove the divergent duplicate signer `routers/zatca.py::sign_invoice` and the legacy in-router `pos.py::generate_zatca_tlv`/`generate_zatca_hash` once the canonical path is authoritative.
- **Onboarding wizard** drives CSR → OTP → production CSID through the existing credential model.

### Contract-drift fixes (Sprint 2)
- **Read the real shapes:** ProductManagement → `data.items` (`ProductListResponse{items,total}`); ExpenseTracking → `txData.items`, sum `tx.total_amount`; AgentDashboard → `remaining_slots`/`total` off the `GET /agent/clients` response (drop the unused `client_slots`/`used_slots`/`package_type` interface fields); MasterDashboard → the real price field; DiscountManagement → `usage_count` (not `used_count`).
- **Tighten return types.** Give the drift-prone `api.ts` functions explicit typed return signatures so a shape mismatch is a compile error. This is the durable guard against recurrence.
- **Stop swallowing.** Remove the try/catch blocks that hide 404/500 on LoyaltyProgram, WebhookManagement logs, and storage so missing endpoints surface during development.

### Loyalty, webhooks, storage façades (Sprint 2)
- **Loyalty:** implement `GET/POST /loyalty/config` (↔`loyalty_programs`), `GET /loyalty/balances` (↔`loyalty_points`), `GET /loyalty/transactions` (ledger), `POST /loyalty/adjust`; reconcile the singular `/loyalty/balance` vs plural the UI calls. Add a points-movement ledger + expiry (Sprint 3 depth).
- **Webhooks:** add a `webhook_deliveries` table + `GET /production/webhooks/logs`, persist dispatch outcomes; fire the remaining advertised events at source (shift/product/customer/inventory) or trim `AVAILABLE_EVENTS`; reconcile `refund.created` vs `sale.refunded`.
- **Storage:** add `oss_service_url`/`oss_api_key` to `Settings` (degrade to a clear `ValueError`, not `AttributeError`→500) plus a real caller, or delete `routers/storage.py` + `services/storage.py` + schemas. Decision deferred to implementation but it must not stay a 500 façade.

### POS data integrity (Sprint 2)
- **Hold/recall:** serialize `variant_id` + open-price `unitPrice` into `items_json` and rebuild with `cartKeyFor(product_id, variant_id)` on recall. Backend round-trips `items_json` verbatim — this is a frontend serialization fix.
- **Combos:** at settle, expand combo lines into component products (id + qty) so `sale_core` deducts inventory + BOM and routes to KDS; or document combos as explicit non-stock bundles. Combo lines currently carry `product_id=None`.

### Staff, permissions, PO, catalog, BOM (Sprint 3)
- **Staff login:** on staff create/update, create or link an auth `User` (temp password or invite token) scoped to the merchant so tenancy resolution (`Staff_members.email`→`User.email`) actually finds a login.
- **RBAC data source:** drive `has_permission` off a role→`permission_key` default map, and/or a staff-permission editor (owner-scoped endpoint + UI) writing rows keyed on staff `user_id`. `Permissions.role` (currently NOT NULL, ignored) is reconciled or dropped.
- **PO:** form maps to `Purchase_ordersData` (generate `order_number`, send `items_json` with `product_id`), drop phantom fields; receive dialog adds branch + per-line quantities; `receivePurchaseOrder` passes options for partial/branch receipts.
- **Catalog:** add `products.category_id` FK; product form Select sourced from `getCategories()`; remove the hardcoded `CATEGORIES` array — or drop the categories CRUD island if not consumed.
- **BOM:** add api.ts client functions for the existing recipe endpoints + a recipe editor (product detail or MenuBuilder tab).

### Auth (Sprint 3)
- **Silent refresh:** the axios 401 interceptor (in the file currently `atomsClient.ts`, to be renamed `apiClient.ts`) attempts one `refreshAccessToken()` + request replay before clearing tokens and redirecting.
- **Single logout:** dashboards call `useAuth().logout()` (which sends `refresh_token` and clears both keys); remove the duplicate `client.auth.logout()` that posts no body.
- **Brute-force protection** on the login endpoint.

### Schema changes (summary)
- `products.category_id` FK (Sprint 3).
- `webhook_deliveries` table (Sprint 2).
- `ZatcaDocuments.invoice_uuid` written by non-test code (Sprint 1).
- Loyalty ledger / expiry columns (Sprint 2–3).
- Staff↔User link + permission rows keyed on staff `user_id` (Sprint 3).
- `Settings.oss_service_url`/`oss_api_key` if storage is kept (Sprint 2).
- Removals: `data_models/*.json` generator artifacts; `Permissions.role` reconciled.

### Out-of-the-box untouched
- The three **solid** units (U3.4 POS sale core, U3.5 Pricing, U4.1 Restaurant floor/settle) get only the named minor fixes (H28 hold/recall, refund-UI currency, `bill_printed` state, deplete-stock double-deduct) — no structural refactor.

---

## Testing Decisions

A good test here asserts **external behavior at the highest existing seam** — an HTTP request returns the right shape/scope, a deleted scaffold stays gone, a signed invoice validates — never an implementation detail. Prefer the existing seams; they already encode the audit's guards.

### Existing seams (prior art — extend, don't replace)
- **`tests/test_orphan_routers.py`** — the canonical seam for the auto-CRUD purge. Pure static analysis (no app boot): every mounted router must have a frontend caller or a justified `ALLOWLIST` entry; `REMOVED_BACKEND`/`REMOVED_FRONTEND` ensure deleted scaffolds never reappear. Every Sprint-1 deletion updates this file; the test asserts both directions (no undocumented orphan; no stale allowlist entry).
- **`tests/test_phase1_tenant_scope.py`** — prior art for tenancy. Add cases proving a staff/cashier sub-user can receive a PO, charge a terminal, and that an owner's audit/api-usage reads return staff actions scoped to `owner_user_id`.
- **`tests/test_phase2_zatca_sale.py`, `tests/test_zatca.py`, `tests/test_phase6_zatca_*`** — prior art for ZATCA. Add: PIH chains per-client across concurrent requests (no singleton bleed); submitted XML contains a `ds:Signature` in `UBLExtensions`; the hash is over C14N output; `cbc:UUID` is non-empty and persisted; gateway submission is gated off until these pass.

### Modules to test (by sprint)
- **Sprint 1:** orphan-lint (every deletion), tenancy scope (PO-receive / payments / audit / api_usage / `require_feature`), ZATCA signing/PIH/UUID/C14N, audit-log write/delete endpoints are gone (404), package hard-delete route is gone.
- **Sprint 2:** API integration tests asserting response shapes the UIs read (`items`/`total`/`remaining_slots`/`usage_count`); loyalty config/balances/transactions/adjust endpoints exist and round-trip; webhook delivery-log GET returns persisted rows; storage either returns a typed error or is absent; hold/recall preserves `variant_id`+price through `items_json`; combo settle deducts component stock (extend the restaurant settle tests).
- **Sprint 3:** staff create provisions a usable login; role→permission map denies a cashier refund/void; PO create accepts the real schema and receive lands stock into a branch; product↔category linkage; BOM recipe round-trip + depletion; 401 interceptor refresh-and-replay; logout revokes the refresh jti (a subsequent `/auth/refresh` fails); login throttling.
- **Sprint 4:** receipt-template fields reach `build_receipt`/`build_kot`; terminal picker sets `terminal_id` and `sale_core` honors it; each advertised webhook event fires (or `AVAILABLE_EVENTS` matches emitted set); billing scheduler sweep; quote→sale conversion.

### Contract-drift guard
- Tightening the `api.ts` return types is itself a test: a shape mismatch becomes a TypeScript compile error in CI. Treat type coverage on the drift-prone endpoints as a deliverable, not optional.

### What not to test
- Don't assert on internal singletons, private helper signatures, or generated-router internals being deleted (the orphan-lint already proves absence at the file seam). Don't snapshot full XML — assert the specific fiscal facts (signature present, UUID non-empty, hash over C14N).

---

## Out of Scope

- **A full design-system component library rebuild.** Story 57 migrates the named pages to existing brand tokens with i18n/RTL; it does not introduce a new design language or component framework.
- **New verticals or modules** beyond what the audit names. This PRD remediates the existing 18 units; it does not add e.g. accounting, HR, or a new channel integration.
- **Production ZATCA go-live certification.** Story 19 verifies against the *sandbox*; obtaining production CSIDs and formal Fatoora onboarding for a real merchant is an operational task outside this code PRD.
- **Performance/scale work** beyond registering the already-defined `PerformanceMiddleware` and fixing the noted infra residue (CORS dupe, `sw.js` manifest). No new load-testing or caching architecture.
- **Mobile/native apps.** Web frontend only.
- **Data migration of existing tenants** for schema changes (FK backfill strategy) is acknowledged but its rollout plan is a separate operational doc; the PRD covers the schema + code.

---

## Further Notes

- **Ordering is load-bearing.** §6 of the audit makes the case: the auto-CRUD purge and tenancy unification are *subtractive and low-risk* yet eliminate the most high/critical findings per unit of effort (H1, H2, H3, H4, H13, H14, H15, H17, H18, H20 + most of §4). ZATCA is the only true compliance blocker. The contract-drift fixes are near-zero-cost and restore trust in features that already exist. Everything else is additive and best done on a consistent foundation. **Do not start with the three solid units.**
- **The orphan-lint is the safety net for the whole purge.** Because deletions are enforced by `test_orphan_routers.py`, the risky-feeling "delete dozens of files" sweep is actually the safest work in the plan — the test fails loudly if a deletion is incomplete or if a scaffold returns.
- **Façades must stop lying before they're fixed.** Removing swallowed-error catches (story 29) is a prerequisite for diagnosing C4/H24/H27 — do it first within Sprint 2.
- **Two findings interact:** H10 (wire `refreshAccessToken`) supersedes the "dead `refreshAccessToken`" residue item in story 58 — wire it, don't delete it. Sequence H10 before that cleanup.
- **Known correctness traps to keep in view (from §4 inert bindings):** refund UI showing USD not SAR (U3.4); `bill_printed` table state never assigned (U4.1); deplete-stock double-deduct (U4.1); `sw.js` references a non-existent `/manifest.webmanifest` voiding the whole `addAll`; `PerformanceMiddleware` defined but never registered; placeholder CORS dupe in `middlewares/production.py`. Fold these into the relevant sprint.
- **Glossary discipline:** use the project's domain vocabulary throughout implementation — *tenant/owner*, *agent/reseller*, *client/merchant*, *PIH*, *KOT/KDS*, *BOM*, *tender* — matching the existing PRDs (`PRD-RST-restaurant-vertical.md`, `PRD-RPT-reporting-depth.md`).
- This PRD is a remediation umbrella; when broken into issues, each finding ID (C1–C4, H1–H28) is independently grabbable and most carry their own acceptance criterion above.
