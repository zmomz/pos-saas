# PRD — Restaurant Vertical (RST core, F-055–F-062)

> **Scope:** F-055–F-062 · **Status:** COMPLETE (see git history) · **Bar:** Foodics / Rewaa / Marn parity, localized for Saudi. This PRD is self-contained — acceptance criteria are below.
>
> Covers the eight open restaurant findings: F-055 (order-ticket line items + course/transfer/merge/split), F-056 (modifiers/combos), F-057 (KDS/KOT), F-058 (order types drive behavior), F-059 (check → settle-to-ZATCA), F-060 (aggregator ingest), F-061 (service charge), F-062 (composite/BOM depletion).

---

## Problem Statement

A merchant whose business type is `restaurant` or `both` can today map a floor, place tables, and open an order ticket against a table — and then hits a wall. From the user's perspective:

- **A server cannot put food on the ticket.** Opening a table is the *only* thing that works; there is no way to add a single item, let alone fire it by course, transfer a table, or split a bill. The ticket can only ever be `open`.
- **The menu is flat.** A merchant cannot define "no onions / extra cheese (+5 SAR)" modifiers or a meal combo, so the kitchen and the bill can never reflect how the food was actually ordered.
- **The kitchen is blind.** There is no Kitchen Display, no kitchen printer, no prep-stations, no bump/recall. "Firing" an order has nowhere to go.
- **Order type is a label that does nothing.** Takeaway and delivery still require a table; nothing about tax, printing, or flow changes based on dine-in vs takeaway vs delivery.
- **There is no bill and no settlement.** A table flips to "bill printed" purely in the browser with no document produced, and **no path turns an order ticket into a paid, ZATCA-stamped invoice.** The `settled` state is unreachable — a restaurant literally cannot take money through this surface.
- **Aggregator orders never arrive.** Orders from Jahez / HungerStation cannot flow into the POS/kitchen or reconcile into sales and stock.
- **Service charge and recipes are missing.** A restaurant cannot add an optional service % outside the VAT base, and selling a dish never depletes its recipe ingredients from stock.

Net effect: **a restaurant client cannot operate.** The first slice (F-045) proved the floor exists; this PRD makes the vertical usable end to end.

## Solution

Complete the restaurant vertical so a `restaurant`/`both` merchant can run a full service from seating to a compliant fiscal invoice, with the kitchen and stock in sync — matching what Foodics/Marn do, localized for Saudi.

From the user's perspective, after this ships:

- A server **adds items to an order ticket**, assigns them to **courses** and **seats**, **fires** a course to the kitchen, and can **transfer** a table or **merge/split** bills (by seat, by amount, by item).
- A merchant **builds a menu** with required/optional **modifier groups**, add-on pricing, and **combos/meal bundles**; modifiers flow into the line price (before VAT) and onto the kitchen ticket.
- The kitchen sees fired items on a **Kitchen Display (KDS)**, one column per **prep-station**, updating in near-real-time, with **bump/recall** and ticket timers — and/or an 80mm **KOT** printed in Arabic.
- **Order type drives behavior:** takeaway/delivery need no table; print routing and any delivery/tax rule key off the type.
- A server prints a **non-fiscal check** (فاتورة مبدئية) before payment, then **settles** the ticket — which mints a real **ZATCA invoice** through the same atomic sale path the POS uses, frees the table, and marks the ticket `settled`.
- **Aggregator orders** (Jahez/HungerStation, via a Deliverect-class middleware webhook) land as order tickets that fire to the KDS *and* book a ZATCA sale decrementing shared stock — idempotently.
- A restaurant can add an **optional service charge** that sits outside the VAT base and renders correctly on the ZATCA invoice.
- Selling a dish or a bundle SKU **depletes its recipe/BOM components** from stock inside the same atomic transaction.

Every new screen renders its loading / empty / error / permission / offline states, uses brand tokens (never hardcoded styling), is translated across all four languages with RTL verified, and **every fiscal/kitchen printable renders in Arabic regardless of UI language.**

---

## User Stories

### Order tickets & line items (F-055)
1. As a server, I want to add a menu item to an open order ticket, so that the customer's order is captured against their table.
2. As a server, I want to set the quantity of a line item, so that "3× espresso" is one line.
3. As a server, I want to assign each item to a course (e.g. starters, mains, dessert), so that the kitchen prepares and serves them in the right order.
4. As a server, I want to assign an item to a specific seat number, so that I can later split the bill by seat.
5. As a server, I want to add a note to a line (e.g. "well done"), so that the kitchen and the customer's intent are recorded.
6. As a server, I want to remove or void a line before it is fired, so that a mistaken entry doesn't reach the kitchen.
7. As a server, I want to fire a course to the kitchen, so that the line items move from `open` toward `fired` and reach the relevant prep-stations.
8. As a server, I want to hold a course and fire it later, so that mains don't start before starters are cleared.
9. As a server, I want to see an all-day count of fired items, so that the kitchen and I share a view of outstanding work.
10. As a server, I want to transfer an order ticket from one table to another, so that a party that moves keeps its order.
11. As a server, I want to merge two tickets into one bill, so that two tables that joined pay together.
12. As a server, I want to split a bill by seat, by amount, or by item, so that each guest pays their share.
13. As a manager, I want every line edit, void, transfer, and split to be owner-scoped and auditable, so that one client can never see or mutate another client's tickets (SEC-02).

### Modifiers, modifier groups & combos (F-056)
14. As a menu manager, I want to define a modifier group (e.g. "Doneness") with required/optional and min/max selection rules, so that ordering enforces valid choices.
15. As a menu manager, I want to define modifiers with a price delta (e.g. "extra cheese +5 SAR"), so that add-ons are priced correctly.
16. As a menu manager, I want to attach modifier groups to products, so that the right options appear when that item is ordered.
17. As a server, I want required modifier groups to be enforced when I add an item, so that I cannot send an under-specified item to the kitchen.
18. As a server, I want the line total to include modifier price deltas before VAT, so that the customer is charged correctly and the tax base is right.
19. As a menu manager, I want to define a combo/meal bundle (components + a bundle price), so that I can sell "meal deals" at a price that overrides the sum of components.
20. As a customer, I want my modifiers to appear on the kitchen ticket, so that the kitchen makes my order exactly as requested.

### KDS / KOT (F-057)
21. As a menu manager, I want to define prep-stations (e.g. Grill, Bar, Cold), so that fired items route to the station that prepares them.
22. As a kitchen cook, I want a Kitchen Display with one column per prep-station, so that I see only the work for my station.
23. As a kitchen cook, I want fired items to appear on the KDS within ~1 second, so that I can start preparing immediately (SRS §5.1).
24. As a kitchen cook, I want to bump (complete) a ticket, so that finished items leave the active board.
25. As a kitchen cook, I want to recall a bumped ticket, so that I can correct a mistaken bump.
26. As a kitchen cook, I want ticket timers and all-day counts, so that I can manage prep order and spot delays.
27. As a kitchen operator, I want an 80mm Arabic KOT printed per station (modifiers grouped by course, no prices), so that stations without a screen still get tickets.
28. As an expo, I want fired/bumped state to stay consistent between the server's screen and the KDS, so that the front and back of house agree on order status.

### Order types (F-058)
29. As a cashier, I want to start a takeaway order without a table, so that walk-up orders don't require seating.
30. As a cashier, I want to start a delivery order without a table, so that delivery orders are captured.
31. As a manager, I want order type to drive print routing (and any delivery-fee/tax rule), so that dine-in, takeaway, and delivery behave differently as the business requires.
32. As a user, I want order type labels translated across all four languages, so that staff in any language understand the order.

### Check & settle-to-ZATCA (F-059)
33. As a server, I want to print a non-fiscal check (فاتورة مبدئية) before payment, so that the customer can review the bill before paying.
34. As a server, I want the check to clearly be non-fiscal (no QR, no stamp, always Arabic), so that it is never mistaken for a tax invoice.
35. As a cashier, I want to settle an order ticket into a real ZATCA invoice on payment, so that the sale is compliant and reported.
36. As a cashier, I want settlement to reuse the same atomic sale path as the POS (tender capture, inventory, shift, ECDSA stamp), so that a restaurant sale is identical in compliance and side effects to a retail sale.
37. As a server, I want settling to free the table and mark the ticket `settled`, so that the table can be reseated.
38. As a cashier, I want a declined card at settlement to roll the whole settlement back (ticket stays open, table stays occupied, no invoice minted), so that I never have a settled ticket without captured payment.

### Aggregator ingest (F-060)
39. As a restaurant operator, I want aggregator orders (Jahez/HungerStation) to ingest via a Deliverect-class middleware webhook, so that I manage all channels from one POS (SRS forbids direct aggregator APIs).
40. As a restaurant operator, I want an ingested aggregator order to appear as an order ticket fired to the KDS, so that the kitchen prepares it like any other order.
41. As an accountant, I want an ingested aggregator order to book a ZATCA sale that decrements shared stock, so that aggregator revenue and inventory reconcile.
42. As an operator, I want aggregator ingest to be idempotent on (provider, external order id, client), so that webhook re-delivery never double-books a sale.

### Service charge (F-061)
43. As a restaurant manager, I want to add an optional service-charge % to a ticket, so that I can apply a standard gratuity/service fee.
44. As an accountant, I want the service charge computed outside the VAT base and shown as its own line, so that the ZATCA invoice is correct (mirroring the tips-outside-VAT treatment).

### Composite / recipe BOM (F-062)
45. As an inventory manager, I want to define a bill of materials (parent product → component products with qty-per), so that selling a dish or bundle depletes its ingredients.
46. As an inventory manager, I want BOM expansion to happen inside the same atomic stock transaction as the sale, so that stock is never left inconsistent if the sale fails.
47. As a manager, I want component costs to roll up, so that margin reporting (future F-068) can use true cost of goods.

### Cross-cutting
48. As any user, I want every new restaurant screen to render loading, empty, error, permission-denied, and offline states, so that no screen is a dead end.
49. As an Arabic user, I want every new screen to render correctly in RTL with brand tokens, so that the experience is first-class in Arabic.
50. As an operator, I want every kitchen and fiscal printable to render in Arabic regardless of UI language, so that compliance and kitchen operations are consistent.

---

## Implementation Decisions

### Tracer-bullet ordering (build/test sequence)
The findings are interdependent; build in dependency order so each slice is independently testable end-to-end:
1. **F-055 order-ticket items** (foundation: nothing else works without lines on a ticket).
2. **F-056 modifiers/combos** (line composition + pricing).
3. **F-058 order types** (cheap; unblocks tableless takeaway/delivery used by aggregator).
4. **F-061 service charge** (line math; small, mirrors existing tips pattern).
5. **F-062 BOM depletion** (stock side effect; feeds settle).
6. **Extract the atomic-sale core** (prerequisite for F-059 and F-060 — see below).
7. **F-059 check + settle-to-ZATCA** (consumes items + service charge + BOM through the extracted sale core).
8. **F-057 KDS/KOT** (consumes fired items + prep-stations + real-time channel).
9. **F-060 aggregator ingest** (consumes the sale core + KDS + order types; reuses channel-orders idempotency).

### Architectural decision — one fiscal sale path, not three
The POS atomic sale path (tender capture → invoice counter → inventory deduction → shift accumulation → ECDSA sign / hash-chain / archive, all committed together) currently lives **inline in the POS create-transaction request handler.** Settle-to-invoice (F-059) and aggregator ingest (F-060) both need to mint an identical fiscal sale.

**Decision:** extract the atomic-sale core into a reusable service-layer function that takes a normalized cart (line items, tenders, customer/VAT, branch, tip, service charge) and performs the full atomic sequence, returning the persisted transaction + fiscal document. The POS handler, the restaurant settle route, and the aggregator webhook all call it. This avoids three divergent copies of compliance-critical logic and guarantees a restaurant/aggregator sale is byte-for-byte as compliant as a retail sale. The extraction must be behavior-preserving for the existing POS path (existing POS tests are the regression guard).

### Backend modules — new entity triads
Follow the per-entity triad convention (`routers/<entity>.py`, `services/<entity>.py`, `models/<entity>.py`); routers are auto-discovered by exposing a module-level `router`. All rows carry `user_id` + `client_id` and are owner-scoped in the service layer (SEC-02). All restaurant routes pass the existing double-gate (`business_type ∈ {restaurant, both}` AND the `restaurant` feature flag).

- **`order_ticket_items`** — line items on a ticket: `ticket_id`, `product_id`, `variant_id?`, `qty`, `unit_price`, `course`, `seat_no?`, `fire_state` (`open`/`fired`/`bumped`), `prep_station_id?`, `notes`, plus a serialized modifier selection and computed line total. Add `course_state` to `OrderTickets`. Drive the ticket lifecycle so `held`/`fired`/`settled`/`void` are actually reachable (today only `open` is set).
- **`modifier_groups`** — `name`, `required` (bool), `min_select`, `max_select`; **`modifiers`** — `group_id`, `name`, `name_ar`, `price_delta`; link table products↔modifier_groups. **`combos`** — components + bundle price.
- **`prep_stations`** — `name`, `name_ar`; **`kds_tickets`** — materialized fired items routed to a station with status (`active`/`bumped`) and timestamps for timers.
- **`bill_of_materials`** — `parent_product_id`, `component_product_id`, `qty_per`.

### Backend interfaces — new/changed routes
- **Order tickets:** `POST …/order-tickets/{id}/items` (add line), line edit/void, `POST …/order-tickets/{id}/fire` (by course → routes items to prep-stations + creates KDS tickets), `POST …/order-tickets/{id}/transfer`, `…/merge`, `…/split` (by seat/amount/item).
- **Tableless create:** a `POST …/order-tickets` create path that does **not** require a table (for takeaway/delivery); `order_type` becomes a real discriminator that drives print routing.
- **Check & settle:** `POST …/order-tickets/{id}/check` → 80mm non-fiscal **always-Arabic** printable marked *فاتورة مبدئية* (no QR/stamp); `POST …/order-tickets/{id}/settle` → builds a normalized cart from the ticket (lines + modifiers + combos + service charge + BOM-backed components) and calls the extracted atomic-sale core to mint the ZATCA invoice, then sets ticket `settled` + frees the table.
- **KDS:** `GET /kds/tickets` (real-time stream — WS or SSE; this is a **new** seam, none exists today), `POST /kds/{id}/bump`, `POST /kds/{id}/recall`.
- **Aggregator:** an HMAC-verified Deliverect-class inbound webhook that materializes an aggregator order as an `order_ticket` (fires to KDS) **and** books a ZATCA sale via the sale core, reusing `channel_orders` idempotency on `(provider, external_order_id, client_id)`. Providers extend `channel_orders.provider` to include `deliverect` / `delivery_hero`. **Middleware adapter only — the SRS forbids direct aggregator APIs.**

### Line math contract (modifiers, combos, service charge)
- Line total = `unit_price × qty + Σ(modifier price_delta) − line_discount`, computed **before VAT**.
- A combo's bundle price **overrides** the sum of its components.
- **Service charge** is computed as a separate line **outside** the VAT base and rendered on the ZATCA invoice — identical treatment to the shipped tips-outside-VAT behavior (tip is added on top of total, excluded from the taxable base). The tenders must cover invoice total + tip + service charge.
- **BOM:** on settle, BOM-backed lines expand into component deductions inside the same atomic stock transaction as the sale (the sale core owns this).

### Frontend modules
- **Ticket-edit surface** (add items, courses, seats, modifiers, fire, transfer, merge/split) under `src/pages/`, reached from the floor map.
- **Menu-builder page** for modifier groups / modifiers / combos / prep-stations / BOM.
- **`KDS.tsx`** — a column-per-station board with timers and all-day counts; new role-gated route (client) in `App.tsx`.
- Replace the client-side-only "bill printed" table flip with a real check → settle flow calling the new endpoints.
- Typed wrappers for all new endpoints in `src/lib/api.ts` (alongside the existing restaurant wrappers); base URL resolved at runtime (never hardcoded).
- i18n keys added to **all four** language objects (ar/en/hi/ur) in `src/lib/i18n.ts`; RTL verified; new strings include `dine_in`/`takeaway`/`delivery`, `رسوم خدمة` (service charge), course/fire/bump/recall, *فاتورة مبدئية*.

### Printables
- **KOT** (80mm, always Arabic): modifiers grouped by course, **no prices**, per prep-station.
- **Check** (80mm, always Arabic): marked *فاتورة مبدئية*, no QR/stamp.
- **Settled invoice:** the standard ZATCA invoice produced by the sale core (Arabic regardless of UI language).

---

## Testing Decisions

**What makes a good test here:** assert *external behavior* through the highest existing seam, not implementation details. Drive the real ASGI app over HTTP with `httpx.AsyncClient`, create a `restaurant`/`both` client via the `make_client_account` fixture, and assert on response payloads and durable DB state (table state, ticket status, stock quantity, the existence and shape of the ZATCA document). Do not test private service functions where an endpoint test exercises the same path.

**Seam & prior art:** the established pattern in `backend/tests/conftest.py` — fixtures `client`, `auth_headers`, `make_client_account(business_type="restaurant")`, `add_product`, `get_product_quantity`. Closest prior art:
- `test_phase5_restaurant.py` — floor/table/open-order, gating (restaurant vs retail 403, feature-flag off), owner-scoping, double-seat 409. New ticket/menu tests extend this file's style.
- `test_pos_atomic.py` + `test_phase2_zatca_sale.py` — the atomic sale + ZATCA signing the settle path must reuse; these are the **regression guard** for the sale-core extraction (they must keep passing unchanged).
- `test_phase6_tips.py` — the tips-outside-VAT assertion that the service-charge test mirrors.
- `test_phase6_omnichannel.py` — channel-order idempotency, the model for the aggregator-ingest test.

**Named tests to add (the "catch forever" set, by finding):**
- F-055: `test_add_items_by_course`, `test_transfer_table_moves_ticket`, `test_split_bill_by_seat`.
- F-056: `test_required_modifier_group_enforced`, `test_combo_price_overrides_component_sum`.
- F-057: `test_fire_creates_kds_ticket_per_station`, `test_bump_then_recall`; a KOT-render snapshot test.
- F-058: `test_takeaway_order_needs_no_table`, `test_order_type_drives_print_routing`.
- F-059: `test_check_is_non_fiscal_no_qr`, `test_settle_creates_zatca_invoice_and_frees_table`, and a settlement-rollback test (declined card → ticket still open, no invoice).
- F-060: `test_deliverect_webhook_creates_ticket_and_sale_idempotent`.
- F-061: `test_service_charge_excluded_from_vat_base_and_shown_on_invoice`.
- F-062: `test_bom_sale_depletes_components`.

**Regression gate:** the full existing `backend/tests` suite must stay green after the sale-core extraction — that extraction is behavior-preserving by definition.

---

## Out of Scope

- **Other feature families** (F-063+): payments breadth, inventory sessions, pricing/promotions, reporting, finance/AP, white-label depth, billing, reseller economics, CRM campaigns, omnichannel (Zid/C&C), ZATCA C14N, hardware drivers, L10N cleanup. Each is its own PRD.
- **Direct aggregator APIs.** The SRS explicitly forbids them; only a Deliverect-class / Delivery-Hero-POS-partner middleware adapter is in scope.
- **Card PANs on our servers.** Settlement reuses the existing tokenized, no-PAN tender capture; no new card-data handling.
- **Advanced KDS analytics** (speed-of-service dashboards, course-pacing AI) beyond timers + all-day counts.
- **Menu engineering / recipe costing reports** — F-062 only wires BOM *depletion* and the cost roll-up hook; the margin report itself is F-068 (separate).
- **ZATCA canonicalization (C14N)** — F-094, gated on official ZATCA SDK sample vectors; settlement uses the current signing path as-is.
- **Net-new offline support for KDS/aggregator** beyond rendering offline states; the offline-first sale queue is already shipped for the POS path.

## Further Notes

- **CLAUDE.md is stale on tests:** it claims no test suite exists, but `backend/tests/` has ~65 pytest files with `conftest.py` fixtures and full async HTTP coverage. Build to that suite. (Worth correcting CLAUDE.md separately.)
- **Schema is created/patched at runtime** (no committed Alembic history in active use); new tables register on `Base.metadata` and are created at startup — ensure new models are imported so they register (mirror the `# noqa: F401` import pattern already used for branch-stock/variants in the POS router).
- **The sale-core extraction is the linchpin.** Doing F-059 and F-060 without it would fork compliance logic three ways; do the extraction first and prove it against the existing POS/ZATCA tests before building settle.
- **Real-time channel is a genuinely new capability.** Choose WS or SSE deliberately; SRS §5.1 sets a ≤1s KDS update target. This is the one place without existing prior art in the repo.
- **Arabic-always rule is non-negotiable** for KOT, check, and the settled invoice — fiscal and kitchen documents render in Arabic regardless of UI language.
- **Publish target:** no issue tracker is configured (`git remote` empty, `gh` absent), so this PRD is filed as a local markdown artifact. If/when a GitHub tracker is set up, this can be split into per-finding issues via `/to-issues` using the tracer-bullet ordering above.
