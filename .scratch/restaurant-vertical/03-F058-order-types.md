# F-058 — Order types drive behavior (tableless takeaway / delivery)

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-058.

## What to build

Turn `order_type` from a label that does nothing into a real discriminator. Today takeaway and delivery still require a table and nothing about the flow changes. After this slice:

- A cashier can **start a takeaway or delivery order without a table** — a `POST …/order-tickets` create path that does not require a table assignment.
- `order_type` (dine-in / takeaway / delivery) **drives print routing** and is the hook for any delivery-fee / tax rule the business needs.
- Order-type labels are translated across all four languages.

This is a small but enabling slice: it unblocks the tableless path that aggregator ingest (F-060) later relies on.

Backend: extend the order-ticket create path to accept `order_type` and allow a null table for takeaway/delivery; make `order_type` route printing. Keep owner-scoping and the restaurant double-gate.

Frontend: order-type selector on the new-order flow that, for takeaway/delivery, skips table selection; i18n keys `dine_in` / `takeaway` / `delivery` across ar/en/hi/ur with RTL.

## Acceptance criteria

- [ ] A takeaway order can be created with no table; a delivery order can be created with no table.
- [ ] A dine-in order still requires a table (existing behavior preserved).
- [ ] `order_type` drives print routing (dine-in / takeaway / delivery route differently).
- [ ] Order-type labels render in all four languages with RTL verified.
- [ ] New/changed routes remain owner-scoped and behind the restaurant double-gate.
- [ ] Tests added and green: `test_takeaway_order_needs_no_table`, `test_order_type_drives_print_routing`.
- [ ] Order-type selector renders loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `01-F055-order-ticket-line-items.md` (order types parameterize the ticket create/line flow).
