# ISSUE-071 — In-app thermal print of proforma/receipt

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 restaurant · **Stories:** 53

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Add in-app thermal printing of the non-fiscal proforma check (فاتورة مبدئية) and the final receipt from the restaurant flow, using the renderer (ISSUE-045) and printer routing (ISSUE-047). Printables render in Arabic regardless of UI language.

## Acceptance criteria
- [ ] A server can print a proforma check and a final receipt to a thermal printer from the ticket/settle flow.
- [ ] Both render in Arabic and honor the template.
- [ ] Covered by a test asserting the print payload content.

## Blocked by
- ISSUE-045
