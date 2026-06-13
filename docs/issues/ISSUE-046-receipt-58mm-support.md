# ISSUE-046 — 58mm receipt paper support

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** H26 · **Stories:** 47

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Paper width is fixed at 576px/80mm. Add 58mm support so the renderer lays out correctly for narrow thermal printers, selectable per template/printer.

## Acceptance criteria
- [ ] A 58mm width option renders correctly (no clipping/overflow) for receipts and KOT.
- [ ] 80mm remains the default and is unchanged.
- [ ] Covered by a test exercising both widths.

## Blocked by
- ISSUE-045
