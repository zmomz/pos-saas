# F-061 — Service charge outside the VAT base

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-061.

## What to build

Let a restaurant add an **optional service-charge %** to a ticket, computed **outside the VAT base** and shown as its own line — so the ZATCA invoice is correct. This mirrors the already-shipped **tips-outside-VAT** treatment exactly: the charge is added on top of the total and excluded from the taxable base, and the tenders must cover invoice total + tip + service charge.

Backend: add a service-charge field/computation to the ticket (a percentage producing a separate, non-taxable line); fold it into the normalized cart the settle path will build, with the same outside-VAT handling as tips. Keep owner-scoping and the restaurant double-gate.

Frontend: a service-charge control on the ticket; the charge renders as its own line on the check and (via settle) on the ZATCA invoice. i18n `رسوم خدمة` / "service charge" across ar/en/hi/ur with RTL.

Prior art to mirror: the tips-outside-VAT behavior and its test `test_phase6_tips.py`.

## Acceptance criteria

- [ ] A manager can apply an optional service-charge % to a ticket.
- [ ] The service charge is computed outside the VAT base, as its own line — it does not change the taxable amount or VAT.
- [ ] The charge renders correctly as its own line on the (eventual) ZATCA invoice and on the check.
- [ ] Tender validation accounts for invoice total + tip + service charge.
- [ ] Tests added and green: `test_service_charge_excluded_from_vat_base_and_shown_on_invoice`.
- [ ] Service-charge control renders loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `01-F055-order-ticket-line-items.md` (service charge applies to a ticket with line items / a computed total).
