# F-059 — Check + settle-to-ZATCA

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-059.

## What to build

Close the loop a restaurant cannot today: turn an order ticket into money and a compliant invoice. Two steps:

1. **Check (non-fiscal):** `POST …/order-tickets/{id}/check` produces an 80mm **always-Arabic** printable marked *فاتورة مبدئية* (proforma) with **no QR and no stamp**, so the customer reviews the bill before paying and it can never be mistaken for a tax invoice.
2. **Settle (fiscal):** `POST …/order-tickets/{id}/settle` builds a **normalized cart** from the ticket — lines + modifiers + combos + service charge + BOM-backed components — and calls the **extracted atomic-sale core** (slice 06) to mint a real **ZATCA invoice** through the exact same path the POS uses (tender capture, inventory, shift, ECDSA stamp). On success it marks the ticket `settled` and **frees the table**.

Settlement is atomic: a **declined card rolls the whole thing back** — ticket stays `open`, table stays occupied, **no invoice is minted**. A restaurant sale must be byte-for-byte as compliant as a retail sale.

Frontend: replace the client-side-only "bill printed" table flip with a real check → settle flow calling the new endpoints; the settled invoice renders in Arabic regardless of UI language. Typed `api.ts` wrappers; i18n ×4 (*فاتورة مبدئية*, settle/check) with RTL.

## Acceptance criteria

- [ ] `…/check` returns an 80mm always-Arabic proforma marked *فاتورة مبدئية* with no QR and no stamp.
- [ ] `…/settle` builds a normalized cart (lines + modifiers + combos + service charge + BOM components) and mints a ZATCA invoice via the sale-core function — not a reimplementation.
- [ ] A successful settle marks the ticket `settled` and frees the table.
- [ ] A declined card at settlement rolls back entirely: ticket stays open, table stays occupied, no invoice exists.
- [ ] The settled invoice renders in Arabic regardless of UI language; service charge appears outside the VAT base.
- [ ] The browser-only "bill printed" flip is removed in favor of the real flow.
- [ ] Tests added and green: `test_check_is_non_fiscal_no_qr`, `test_settle_creates_zatca_invoice_and_frees_table`, and a settlement-rollback test (declined card → ticket still open, no invoice).
- [ ] Check/settle screens render loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `01-F055-order-ticket-line-items.md` (settle consumes ticket lines).
- `04-F061-service-charge.md` (settle carries the service charge into the cart).
- `05-F062-bom-depletion.md` (settle depletes BOM components).
- `06-sale-core-extraction.md` (settle calls the shared atomic-sale core — the linchpin).
