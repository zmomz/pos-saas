# ISSUE-014 — ZATCA: per-client PIH chain (kill the process-global singleton)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** C1 · **Stories:** 15

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The module-global `zatca_service` singleton holds `_previous_hash`, which `generate_xml_invoice` embeds into the UBL PIH element then overwrites — so the on-chain PIH is whatever the last call (any tenant, any concurrent request) left behind, bleeding across tenants and diverging from the recorded per-client chain. Pass the client's real `previous_hash` explicitly into `generate_xml_invoice`; never hold fiscal chain state in a process-global. The per-client chain in `creds.pih`/`doc.previous_hash` is the single source of truth.

## Acceptance criteria
- [ ] `generate_xml_invoice` accepts the client's `previous_hash` as an explicit parameter; no fiscal state lives on the module-global singleton.
- [ ] The PIH embedded in the UBL equals the invoking client's recorded chain head.
- [ ] A test issues invoices for two clients in interleaved order and asserts each PIH chains only against its own prior invoice (no bleed).
- [ ] Added to `tests/test_phase2_zatca_sale.py`.

## Blocked by
- None - can start immediately
