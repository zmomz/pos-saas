# ISSUE-070 — Per-seat / partial settlement

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 restaurant · **Stories:** 53

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Extend settlement to support paying part of a ticket — by seat, by amount, or by item — each partial producing its own ZATCA-stamped sale through the canonical path, leaving the remainder open.

## Acceptance criteria
- [ ] A ticket can be partially settled by seat/amount/item; remainder stays open.
- [ ] Each partial settlement mints a valid sale/invoice via the canonical path.
- [ ] Fully settling the remainder closes the ticket and frees the table.
- [ ] Covered by a test.

## Blocked by
- None - can start immediately
