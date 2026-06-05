# Restaurant Vertical — issue slices (F-055–F-062)

Tracer-bullet vertical slices broken out from `docs/prd/PRD-RST-restaurant-vertical.md`.
Issue tracker: **local markdown** (no git remote / `gh` configured). Filenames are the issue identifiers.
All slices are **AFK** (no human gate). Each cuts schema → API → UI → tests and is independently verifiable.

| # | Issue | Finding | Blocked by |
|---|-------|---------|-----------|
| 01 | [Order-ticket line items](01-F055-order-ticket-line-items.md) | F-055 | — |
| 02 | [Modifiers & combos](02-F056-modifiers-and-combos.md) | F-056 | 01 |
| 03 | [Order types](03-F058-order-types.md) | F-058 | 01 |
| 04 | [Service charge](04-F061-service-charge.md) | F-061 | 01 |
| 05 | [BOM depletion](05-F062-bom-depletion.md) | F-062 | 01 |
| 06 | [Sale-core extraction](06-sale-core-extraction.md) | (arch linchpin) | 04, 05 |
| 07 | [Check + settle-to-ZATCA](07-F059-check-and-settle.md) | F-059 | 01, 04, 05, 06 |
| 08 | [KDS / KOT](08-F057-kds-kot.md) | F-057 | 01 |
| 09 | [Aggregator ingest](09-F060-aggregator-ingest.md) | F-060 | 03, 06, 08 |

**Suggested build order** (respects all dependencies): 01 → {02, 03, 04, 05} → 06 → {07, 08} → 09.

Cross-cutting (stories 48–50) are acceptance criteria on **every** slice, not a separate issue:
loading/empty/error/permission/offline states, RTL + brand tokens, and Arabic-always fiscal/kitchen printables.
