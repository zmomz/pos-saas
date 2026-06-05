# Sale-core extraction — one fiscal sale path, not three

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Architectural decision underpinning F-059 and F-060.

## What to build

The POS atomic sale path — tender capture → invoice counter → inventory deduction → shift accumulation → ECDSA sign / hash-chain / archive, **all committed together** — currently lives **inline in the POS create-transaction request handler**. Both restaurant settle-to-invoice (F-059) and aggregator ingest (F-060) need to mint an *identical* fiscal sale. Without a shared core, compliance-critical logic forks three ways.

**Extract the atomic-sale core into a reusable service-layer function** that takes a **normalized cart** — line items, tenders, customer/VAT, branch, tip, **service charge** (slice 04), and **BOM-backed components** (slice 05) — and performs the full atomic sequence, returning the persisted transaction + fiscal document. The POS handler, the restaurant settle route (F-059), and the aggregator webhook (F-060) all call it.

The extraction must be **behavior-preserving for the existing POS path** — this is a refactor, not a feature. The existing POS and ZATCA tests are the regression guard and must keep passing **unchanged**. This is the linchpin: do it first and prove it green before building settle or aggregator ingest on top.

## Acceptance criteria

- [ ] A single service-layer function accepts a normalized cart (lines, tenders, customer/VAT, branch, tip, service charge, BOM components) and performs the full atomic sequence: tender capture → invoice counter → inventory deduction (incl. BOM expansion) → shift accumulation → ECDSA sign / hash-chain / archive, committed atomically.
- [ ] It returns the persisted transaction and the fiscal document.
- [ ] The existing POS create-transaction handler is rewired to call this function.
- [ ] Behavior is preserved: `test_pos_atomic.py` and `test_phase2_zatca_sale.py` pass **unchanged** (no edits to those tests).
- [ ] On any failure within the sequence, nothing is committed (no orphan invoice, no partial stock deduction).
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `04-F061-service-charge.md` (the normalized-cart contract must carry the outside-VAT service charge).
- `05-F062-bom-depletion.md` (the sale core owns BOM expansion inside the atomic stock transaction).
