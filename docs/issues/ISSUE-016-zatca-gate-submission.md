# ISSUE-016 — ZATCA: gate gateway submission until fiscal substance is valid

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** C2 (gating) · **Stories:** 21

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Until per-client PIH + signed UBL + C14N + persisted UUID are confirmed against a sandbox, gateway submission must be feature-flagged non-functional rather than silently emitting invalid invoices that a live Fatoora gateway rejects. Also remove the divergent duplicate signer `routers/zatca.py::sign_invoice` and the legacy in-router helpers `pos.py::generate_zatca_tlv`/`generate_zatca_hash` once the canonical `services.zatca_sale` path is authoritative.

## Acceptance criteria
- [ ] A config flag gates live submission; when off, the path returns a clear "submission not enabled" state (no silent invalid POST).
- [ ] `routers/zatca.py::sign_invoice` and the legacy `pos.py` TLV/hash helpers are removed; callers use `services.zatca_sale`.
- [ ] A test asserts submission is gated off by default and that no duplicate signer remains.

## Blocked by
- ISSUE-015
