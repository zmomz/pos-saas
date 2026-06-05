# F-056 — Modifiers, modifier groups & combos

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-056.

## What to build

Make the menu express how food is actually ordered. A menu manager defines **modifier groups** (e.g. "Doneness") with a `required` flag and `min_select` / `max_select` rules, and **modifiers** within them carrying a bilingual name and a `price_delta` (e.g. "extra cheese +5 SAR"). Modifier groups attach to products, so the right options surface when that item is ordered. The manager also defines **combos / meal bundles** — a set of component products sold at a **bundle price that overrides the sum of the components**.

When a server adds an item, **required modifier groups are enforced** (an under-specified item cannot be sent to the kitchen), and the **line total includes modifier price deltas before VAT** so both the charge and the tax base are correct. The selected modifiers flow onto the kitchen ticket so the kitchen makes the order exactly as requested.

Line-math contract: `line total = unit_price × qty + Σ(modifier price_delta) − line_discount`, computed **before VAT**. A combo's bundle price overrides the component sum.

Backend: new `modifier_groups` (`name`, `required`, `min_select`, `max_select`), `modifiers` (`group_id`, `name`, `name_ar`, `price_delta`), a products↔modifier_groups link table, and `combos` (components + bundle price), each as an owner-scoped triad behind the restaurant double-gate. Wire modifier selection into the `order_ticket_items` line total from F-055 and persist the serialized selection on the line.

Frontend: menu-builder surface for modifier groups / modifiers / combos; modifier picker on the ticket-edit add-item flow with required-group enforcement; typed `api.ts` wrappers; i18n ×4 with RTL.

## Acceptance criteria

- [ ] A manager can define a modifier group with required + min/max, modifiers with bilingual names and price deltas, and attach groups to products.
- [ ] Adding an item with an unsatisfied required group is rejected; satisfying it succeeds.
- [ ] Line total reflects `unit_price × qty + Σ(price_delta)` computed before VAT.
- [ ] A combo's bundle price overrides the sum of its component prices.
- [ ] Selected modifiers are persisted on the line and appear on the kitchen ticket payload.
- [ ] All new entities are owner-scoped (SEC-02) and behind the restaurant double-gate.
- [ ] Tests added and green: `test_required_modifier_group_enforced`, `test_combo_price_overrides_component_sum`.
- [ ] Menu-builder + modifier-picker screens render loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `01-F055-order-ticket-line-items.md` (modifiers compose onto ticket line items and their pre-VAT total).
