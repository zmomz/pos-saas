# ISSUE-017 — ZATCA: verify invoices against the Fatoora sandbox

**Status:** ready-for-agent · **Type:** HITL · **Sprint:** 1 · **Findings:** P0 ZATCA · **Stories:** 19

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Submit signed invoices to the live Fatoora **sandbox** and confirm clearance/reporting succeeds — the evidence that the signing path actually works before go-live. HITL: requires sandbox credentials and human review of gateway responses. Once green, the submission gate (ISSUE-016) can be flipped on for sandbox environments.

## Acceptance criteria
- [ ] At least one standard and one simplified invoice clear/report successfully against the Fatoora sandbox.
- [ ] PIH chaining across consecutive sandbox invoices validates gateway-side.
- [ ] Sandbox responses captured/documented; any field gaps fed back as follow-up issues.

## Blocked by
- ISSUE-015, ISSUE-016
