# PRD — Restaurant Vertical (RST core, F-055–F-062)

Ralph driver for the restaurant-vertical work. Each task below is one **tracer-bullet
vertical slice** (schema → API → UI → tests). The one-line task here is a pointer; the
**full spec, behavior, and acceptance criteria live in the linked slice file** under
`.scratch/restaurant-vertical/`. Source of truth for product behavior: `srs.md` v2.0 +
`INTENDED_BEHAVIOR.md` (when code and SRS disagree, the SRS wins). Parity bar: Foodics /
Rewaa / Marn, localized for Saudi.

## How to work this PRD (Ralph rules)

- Tasks are in **strict build order**. Always take the **topmost unchecked `- [ ]` task** —
  that ordering already respects every "Blocked by" dependency.
- **Before implementing:** open and read the linked slice file in
  `.scratch/restaurant-vertical/` for the full spec and the acceptance-criteria checklist.
  Implement **exactly** that slice — nothing from a later slice.
- **Build to the acceptance criteria**, including the named "catch-forever" tests. Drive
  tests through the real ASGI app over HTTP (`httpx.AsyncClient`) using the existing
  `backend/tests/conftest.py` fixtures (`make_client_account(business_type="restaurant")`,
  `add_product`, `get_product_quantity`, …).
- **Regression gate:** the full existing `backend/tests` suite must stay green. Run
  `pytest` (backend) and `pnpm run lint` / `pnpm run build` (frontend) as relevant.
- Every new screen renders loading / empty / error / permission / offline states, uses
  brand tokens (never hardcoded styling), is translated across all four languages
  (ar/en/hi/ur) with RTL verified. Every fiscal/kitchen printable renders in **Arabic
  regardless of UI language**.
- When a slice's acceptance criteria are all met and tests pass: **tick its box to `- [x]`**,
  append a line to `progress.txt` (what shipped + commit SHA), and **commit** with the
  finding tag, e.g. `feat(rst): F-055 — order-ticket line items [F-055]`.
- **ONLY WORK ON A SINGLE TASK per iteration.**
- When every box below is `- [x]`, output `<promise>COMPLETE</promise>`.

## Tasks

- [x] **01 · F-055 — Order-ticket line items** (add/qty/course/seat/note/void, fire, transfer, merge, split; ticket lifecycle) → `.scratch/restaurant-vertical/01-F055-order-ticket-line-items.md` · Blocked by: none
- [x] **02 · F-056 — Modifiers, modifier groups & combos** → `.scratch/restaurant-vertical/02-F056-modifiers-and-combos.md` · Blocked by: 01
- [x] **03 · F-058 — Order types drive behavior** (tableless takeaway/delivery, print routing) → `.scratch/restaurant-vertical/03-F058-order-types.md` · Blocked by: 01
- [x] **04 · F-061 — Service charge outside the VAT base** → `.scratch/restaurant-vertical/04-F061-service-charge.md` · Blocked by: 01
- [x] **05 · F-062 — Composite / recipe BOM depletion** → `.scratch/restaurant-vertical/05-F062-bom-depletion.md` · Blocked by: 01
- [x] **06 · Sale-core extraction** (one fiscal sale path; behavior-preserving refactor) → `.scratch/restaurant-vertical/06-sale-core-extraction.md` · Blocked by: 04, 05
- [x] **07 · F-059 — Check + settle-to-ZATCA** → `.scratch/restaurant-vertical/07-F059-check-and-settle.md` · Blocked by: 01, 04, 05, 06
- [x] **08 · F-057 — KDS / KOT + real-time kitchen channel** → `.scratch/restaurant-vertical/08-F057-kds-kot.md` · Blocked by: 01
- [x] **09 · F-060 — Aggregator ingest** (Deliverect-class webhook) → `.scratch/restaurant-vertical/09-F060-aggregator-ingest.md` · Blocked by: 03, 06, 08
