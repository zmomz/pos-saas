# F-055 — Order-ticket line items + course / fire / transfer / merge / split

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-055.

## What to build

The foundation of the restaurant vertical: put food on a ticket and drive its lifecycle. A server, working from the floor map, opens a table's order ticket and adds menu items to it — each line carrying quantity, a **course** (starters/mains/dessert), an optional **seat number**, and a free-text note. Lines can be removed or voided **before they are fired**. The server **fires a course** to the kitchen, moving those lines from `open` toward `fired`; a held course can be fired later. The server can **transfer** a ticket to another table, **merge** two tickets into one bill, and **split** a bill by seat, by amount, or by item.

This slice makes the ticket lifecycle real: today only `open` is ever set; `held` / `fired` / `settled` / `void` must become reachable states. (Settlement to a fiscal invoice is a later slice — here `fired` is the furthest a line advances.) An all-day count of fired items gives the server and kitchen a shared view of outstanding work.

Backend: new `order_ticket_items` triad (`routers`/`services`/`models`) — line carries `ticket_id`, `product_id`, `variant_id?`, `qty`, `unit_price`, `course`, `seat_no?`, `fire_state` (`open`/`fired`/`bumped`), `prep_station_id?`, `notes`, a serialized modifier selection, and a computed line total. Add `course_state` to `OrderTickets`. New routes: add line, line edit/void, `fire` (by course), `transfer`, `merge`, `split` (by seat/amount/item). Every row carries `user_id` + `client_id`, owner-scoped in the service layer (SEC-02), behind the restaurant double-gate (`business_type ∈ {restaurant, both}` AND the `restaurant` feature flag). Ensure new models are imported so they register on `Base.metadata` at startup.

Frontend: a ticket-edit surface under `src/pages/`, reached from the floor map — add items, set qty, assign course/seat, add notes, void, fire, transfer, merge, split. Typed wrappers in `src/lib/api.ts`; base URL resolved at runtime. i18n keys (course/fire/hold/transfer/merge/split, seat) across all four languages (ar/en/hi/ur), RTL verified.

## Acceptance criteria

- [ ] A server can add a menu item to an open ticket with qty, course, optional seat, and a note; the line persists scoped to the client.
- [ ] A line can be voided/removed while `open`; a fired line cannot be silently deleted.
- [ ] Firing a course advances those lines' `fire_state` to `fired` and updates ticket `course_state`; a held course can be fired later.
- [ ] Transferring a ticket moves it (and its lines) to another table; the source table frees, the target occupies.
- [ ] Merging two tickets produces one bill; splitting produces shares by seat, by amount, and by item.
- [ ] All ticket/line operations are owner-scoped — one client cannot read or mutate another client's tickets (returns 404/403, never cross-tenant data).
- [ ] An all-day fired-item count is queryable.
- [ ] Tests added and green: `test_add_items_by_course`, `test_transfer_table_moves_ticket`, `test_split_bill_by_seat` (driven over HTTP via `httpx.AsyncClient`, `make_client_account(business_type="restaurant")`).
- [ ] Ticket-edit screen renders loading / empty / error / permission-denied / offline states; uses brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

None - can start immediately.
