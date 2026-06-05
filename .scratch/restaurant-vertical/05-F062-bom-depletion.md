# F-062 — Composite / recipe BOM depletion

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-062.

## What to build

Let selling a dish or a bundle SKU **deplete its recipe/BOM components** from stock. An inventory manager defines a **bill of materials**: parent product → component products with a **qty-per**. When a BOM-backed line is sold, the parent expands into component deductions, and that expansion happens **inside the same atomic stock transaction as the sale** — so stock is never left inconsistent if the sale fails. Component costs roll up to provide a true cost-of-goods hook (consumed later by margin reporting, F-068 — not in scope here).

Backend: new `bill_of_materials` triad (`parent_product_id`, `component_product_id`, `qty_per`), owner-scoped, behind the restaurant double-gate. The BOM expansion is owned by the atomic stock/sale path: on sale, BOM-backed lines expand into component deductions within the existing atomic transaction (the sale-core extraction, slice 06, will own this hand-off at settle time — but the BOM model, expansion logic, and a directly-testable depletion path land here).

Note: this slice wires BOM **depletion** + the cost roll-up hook only. The margin/recipe-costing report itself is out of scope (F-068).

## Acceptance criteria

- [ ] A manager can define a BOM: parent product → component products each with a qty-per.
- [ ] Selling a BOM-backed product depletes each component by `qty_per × qty_sold`.
- [ ] BOM expansion occurs inside the same atomic stock transaction as the sale — a failed sale leaves no partial component deduction.
- [ ] Component costs roll up to a cost-of-goods value on the parent (hook only; no report).
- [ ] BOM entities are owner-scoped (SEC-02) and behind the restaurant double-gate.
- [ ] Tests added and green: `test_bom_sale_depletes_components` (asserts component stock via `get_product_quantity`).
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `01-F055-order-ticket-line-items.md` (BOM-backed lines are ticket line items; depletion is exercised through the sale of those lines).
