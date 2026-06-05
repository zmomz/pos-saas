# F-060 — Aggregator ingest (Deliverect-class middleware webhook)

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-060.

## What to build

Bring delivery-aggregator orders (Jahez / HungerStation) into the POS. Orders ingest via an **HMAC-verified Deliverect-class middleware webhook** — **not** direct aggregator APIs (the SRS explicitly forbids those; only a Deliverect / Delivery-Hero-POS-partner middleware adapter is in scope). An ingested order:

1. Materializes as an **order ticket fired to the KDS**, so the kitchen prepares it like any other order, and
2. **Books a ZATCA sale via the sale-core** (slice 06) that **decrements shared stock**, so aggregator revenue and inventory reconcile.

Ingest is **idempotent on `(provider, external_order_id, client_id)`** — webhook re-delivery never double-books a sale. Reuse the existing `channel_orders` idempotency mechanism; extend `channel_orders.provider` to include `deliverect` / `delivery_hero`. Aggregator orders are tableless (rely on the order-type work, slice 03).

Backend: an HMAC-verified inbound webhook route that verifies the signature, dedupes on the idempotency key, materializes an `order_ticket` (fires to KDS) and calls the sale-core to mint the ZATCA sale + stock decrement — all consistent with a normal sale. Owner-scoped to the target client.

## Acceptance criteria

- [ ] An HMAC-verified webhook accepts a Deliverect-class payload; an invalid signature is rejected.
- [ ] A valid order materializes as an order ticket fired to the KDS.
- [ ] The same order books a ZATCA sale via the sale-core that decrements shared stock — identical compliance to a POS sale.
- [ ] Ingest is idempotent on `(provider, external_order_id, client_id)`: re-delivering the same webhook does not create a second ticket or a second sale.
- [ ] `channel_orders.provider` includes `deliverect` / `delivery_hero`; idempotency reuses the existing channel-orders mechanism.
- [ ] No direct aggregator API calls are introduced (middleware adapter only).
- [ ] Tests added and green: `test_deliverect_webhook_creates_ticket_and_sale_idempotent`.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `03-F058-order-types.md` (aggregator orders are tableless takeaway/delivery).
- `06-sale-core-extraction.md` (ingest books the sale via the shared atomic-sale core).
- `08-F057-kds-kot.md` (ingested orders fire to the KDS).
