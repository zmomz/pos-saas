# ISSUE-050 — Checkout terminal picker sets `terminal_id`

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** H16 · **Stories:** 48

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`POSTerminal` never sends `terminal_id`, so the integrated-terminal charge path is unreachable. Add a checkout terminal picker that sets `payments[].terminal_id`; `sale_core` already honors it and routes the charge to `/terminal/charge`.

## Acceptance criteria
- [ ] At checkout the cashier can pick a registered terminal; the payment carries `terminal_id`.
- [ ] A sale with a `terminal_id` routes the charge through the terminal gateway.
- [ ] Covered by a test (sale with terminal_id → terminal charge invoked).

## Blocked by
- ISSUE-049
