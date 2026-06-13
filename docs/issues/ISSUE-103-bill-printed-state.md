# ISSUE-103 — Assign the `bill_printed` table state

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** U4.1 (solid-unit minor) · **Stories:** Further Notes

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The `bill_printed` table state is rendered/translated but never actually assigned (the table flips purely in the browser). Set the `bill_printed` state on the ticket/table when a bill is printed so it reflects real state. Minor fix to a solid unit.

## Acceptance criteria
- [ ] Printing a bill sets the `bill_printed` state on the ticket/table (server-side).
- [ ] The floor reflects the real state across sessions/devices.
- [ ] Covered by a test.

## Blocked by
- None - can start immediately
